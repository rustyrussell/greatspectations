import pytest

from greatspectations.config import Config, Source
from greatspectations import formats
from greatspectations.coverage import (
    CoverageError,
    CoverageRecord,
    adjacent_after,
    adjacent_before,
    find_gaps,
    is_requirements_section,
    load_coverage,
    merge_intervals,
    section_content_start,
    snippet,
    write_coverage,
)
from greatspectations.matching import CheckResult, Match
from greatspectations.quotes import Quote


def make_result(source, id, filename, line, section_idx, start, end, ok=True):
    q = Quote(source=source, id=id, section_hint=None, filename=filename, line=line, text="x")
    match = Match(section_idx=section_idx, start=start, end=end) if ok else None
    return CheckResult(q, ok, match=match)


def test_write_coverage_skips_failures(tmp_path):
    path = tmp_path / "coverage.txt"
    results = [
        make_result("bolt", 11, "a.c", 5, 0, 10, 20),
        make_result("bolt", 11, "a.c", 6, 0, 20, 30, ok=False),
    ]
    write_coverage(str(path), results)
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    assert lines[0] == "bolt 11 0 10 20 a.c 5"


def test_write_coverage_single_file_source_uses_dash(tmp_path):
    path = tmp_path / "coverage.txt"
    results = [make_result("cmdata-spec", None, "a.c", 1, 2, 0, 5)]
    write_coverage(str(path), results)
    assert path.read_text().strip() == "cmdata-spec - 2 0 5 a.c 1"


def test_load_coverage_roundtrip(tmp_path):
    path = tmp_path / "coverage.txt"
    results = [
        make_result("bolt", 11, "a.c", 5, 0, 10, 20),
        make_result("bolt", 11, "b.c", 7, 0, 25, 30),
        make_result("cmdata-spec", None, "c.c", 1, 2, 0, 5),
    ]
    write_coverage(str(path), results)
    coverage = load_coverage(str(path))

    assert set(coverage.keys()) == {("bolt", 11), ("cmdata-spec", None)}
    assert coverage[("bolt", 11)] == [
        CoverageRecord("bolt", 11, 0, 10, 20, "a.c", 5),
        CoverageRecord("bolt", 11, 0, 25, 30, "b.c", 7),
    ]
    assert coverage[("cmdata-spec", None)] == [
        CoverageRecord("cmdata-spec", None, 2, 0, 5, "c.c", 1),
    ]


def test_load_coverage_missing_file_raises(tmp_path):
    with pytest.raises(CoverageError, match="not found"):
        load_coverage(str(tmp_path / "nope.txt"))


def test_load_coverage_warns_on_malformed_line(tmp_path, capsys):
    path = tmp_path / "coverage.txt"
    path.write_text("bolt 11 0 10 20 a.c 5\nnot enough fields\n")
    coverage = load_coverage(str(path))
    assert len(coverage[("bolt", 11)]) == 1
    err = capsys.readouterr().err
    assert "bad coverage record" in err


def test_merge_intervals():
    assert merge_intervals([(0, 5), (5, 10)]) == [(0, 10)]
    assert merge_intervals([(0, 5), (7, 10)]) == [(0, 5), (7, 10)]
    assert merge_intervals([(7, 10), (0, 5), (2, 8)]) == [(0, 10)]
    assert merge_intervals([]) == []


def test_adjacent_before_and_after():
    records = [
        CoverageRecord("bolt", 11, 0, 0, 5, "a.c", 1),
        CoverageRecord("bolt", 11, 0, 10, 15, "b.c", 2),
        CoverageRecord("bolt", 11, 0, 20, 25, "c.c", 3),
    ]
    assert adjacent_before(records, 10) == [records[0]]
    assert adjacent_after(records, 15) == [records[2]]
    assert adjacent_before(records, 0) == []
    assert adjacent_after(records, 100) == []


def test_snippet_truncates():
    text = "x" * 100
    assert snippet(text, 0, 100, tail=False).startswith(text[:60])
    assert snippet(text, 0, 100, tail=False).endswith("...")
    assert snippet(text, 0, 100, tail=True).startswith("...")


def test_section_content_start():
    assert section_content_start("### Reader Requirements A reader MUST x") > 0
    assert section_content_start("no header here") == 0


def test_is_requirements_section():
    assert is_requirements_section("### Reader Requirements")
    assert is_requirements_section("### Requirements")
    assert is_requirements_section("## requirements")
    assert not is_requirements_section("### Rationale")


SPEC_TEXT = """# Century Metadata Format Specification

### Reader Requirements

A reader MUST fail parsing if the file is too short. A reader MUST also
validate the signature before trusting any field.

### Rationale

Uncovered rationale text that should never be reported as a gap.
"""


def cmdata_config(spec_path) -> Config:
    return Config(sources={
        "cmdata-spec": Source(
            name="cmdata-spec", format="markdown", comment_marker="CMDATA-SPEC",
            file=str(spec_path),
        )
    })


def test_find_gaps_reports_uncovered_requirements_text(tmp_path):
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(SPEC_TEXT)
    config = cmdata_config(spec_path)

    coverage_path = tmp_path / "coverage.txt"
    # Cover only the first sentence.
    covered_text = "A reader MUST fail parsing if the file is too short."
    doc = formats.load("markdown", str(spec_path))
    headers = [s.header for s in doc.sections]
    section = doc.sections[headers.index("### Reader Requirements")]
    start = section.text.index(covered_text)
    end = start + len(covered_text)
    coverage_path.write_text(
        "cmdata-spec - {} {} {} src.c 1\n".format(
            headers.index("### Reader Requirements"), start, end
        )
    )

    gap_lines, any_uncovered = find_gaps(config, str(coverage_path))
    assert any_uncovered is True
    assert any("validate the signature" in g.text for g in gap_lines)
    # Rationale section is not a Requirements section, so it's ignored
    # by default even though nothing covers it.
    assert not any("Uncovered rationale" in g.text for g in gap_lines)


def test_find_gaps_no_gap_when_fully_covered(tmp_path):
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(SPEC_TEXT)
    config = cmdata_config(spec_path)

    doc = formats.load("markdown", str(spec_path))
    headers = [s.header for s in doc.sections]
    si = headers.index("### Reader Requirements")
    section = doc.sections[si]
    content_start_offset = section_content_start(section.text)

    coverage_path = tmp_path / "coverage.txt"
    coverage_path.write_text(
        "cmdata-spec - {} {} {} src.c 1\n".format(
            si, content_start_offset, len(section.text)
        )
    )

    gap_lines, any_uncovered = find_gaps(config, str(coverage_path))
    assert any_uncovered is False
    assert gap_lines == []


def test_find_gaps_all_sections_includes_rationale(tmp_path):
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(SPEC_TEXT)
    config = cmdata_config(spec_path)

    coverage_path = tmp_path / "coverage.txt"
    coverage_path.write_text("")

    gap_lines, any_uncovered = find_gaps(
        config, str(coverage_path), doc_keys=[("cmdata-spec", None)], all_sections=True
    )
    assert any_uncovered is True
    assert any("Uncovered rationale" in g.text for g in gap_lines)


def test_find_gaps_skips_unresolvable_source(tmp_path, capsys):
    config = Config(sources={
        "bolt": Source(
            name="bolt", format="markdown", comment_marker="BOLT",
            dir=str(tmp_path / "nonexistent"), pattern="{id:02d}-*.md",
        )
    })
    coverage_path = tmp_path / "coverage.txt"
    coverage_path.write_text("bolt 11 0 0 5 src.c 1\n")

    gap_lines, any_uncovered = find_gaps(config, str(coverage_path))
    assert gap_lines == []
    assert any_uncovered is False
    assert "cannot load" in capsys.readouterr().err
