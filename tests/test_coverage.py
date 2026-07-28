import pytest

from greatspectations.config import Config, Source
from greatspectations import formats
from greatspectations.coverage import (
    CoverageError,
    CoverageRecord,
    adjacent_after,
    adjacent_before,
    find_gaps,
    has_normative_keyword,
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


def test_has_normative_keyword():
    assert has_normative_keyword("A server MUST close the connection.")
    assert has_normative_keyword("Nodes SHOULD NOT retry immediately.")
    assert has_normative_keyword("This field is OPTIONAL.")
    # RFC 8174: only the all-caps form is normative -- ordinary English
    # "must"/"should", and "May" as e.g. a month name, don't count.
    assert not has_normative_keyword("A server must close the connection.")
    assert not has_normative_keyword("This was fixed in May 2020.")
    assert not has_normative_keyword("Rationale and background only.")


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


RFC_STYLE_TEXT = """# Example Protocol

## Message Format

Implementations MUST validate the checksum field before processing the message. This section explains the historical rationale for the checksum algorithm, which is not itself a requirement. A receiver SHOULD log invalid checksums for diagnostic purposes.
"""


def test_find_gaps_uses_keywords_without_requirements_header(tmp_path):
    # RFCs rarely have a section literally titled "Requirements" (unlike
    # BOLT) -- normative keywords are what makes this section eligible.
    spec_path = tmp_path / "rfcstyle.md"
    spec_path.write_text(RFC_STYLE_TEXT)
    config = cmdata_config(spec_path)

    doc = formats.load("markdown", str(spec_path))
    headers = [s.header for s in doc.sections]
    si = headers.index("## Message Format")
    section = doc.sections[si]
    covered_text = (
        "Implementations MUST validate the checksum field before "
        "processing the message."
    )
    start = section.text.index(covered_text)
    end = start + len(covered_text)

    coverage_path = tmp_path / "coverage.txt"
    coverage_path.write_text("cmdata-spec - {} {} {} src.c 1\n".format(si, start, end))

    gap_lines, any_uncovered = find_gaps(config, str(coverage_path))
    assert any_uncovered is True
    texts = [g.text for g in gap_lines]
    assert any("SHOULD log invalid checksums" in t for t in texts)
    # Non-normative rationale prose between the two requirements is
    # uncovered too, but shouldn't be flagged as a gap.
    assert not any("historical rationale" in t for t in texts)


BIP_STYLE_TEXT = """# Example BIP

## Specification

Wallets must derive the address using the standard algorithm described
above, and clients should verify signatures before broadcasting a
transaction.
"""


def test_find_gaps_ignores_lowercase_prose_without_requirements_header(tmp_path):
    # BIPs rarely capitalize MUST/SHOULD the RFC 2119 way -- without
    # that signal or a "Requirements" header, there's nothing reliable
    # to flag, so the section is skipped rather than false-flagged.
    spec_path = tmp_path / "bipstyle.md"
    spec_path.write_text(BIP_STYLE_TEXT)
    config = cmdata_config(spec_path)

    coverage_path = tmp_path / "coverage.txt"
    coverage_path.write_text("")

    gap_lines, any_uncovered = find_gaps(
        config, str(coverage_path), doc_keys=[("cmdata-spec", None)]
    )
    assert gap_lines == []
    assert any_uncovered is False


BOLT_STYLE_TEXT = """# BOLT Example

### Requirements

A sending node:
  - MUST set `funding_satoshis` to the amount it wishes to fund.
  - MUST NOT send a negative `funding_satoshis`.
  - if it is the funder:
    - MUST set `channel_reserve_satoshis` greater than or equal to `dust_limit_satoshis`.
"""


def test_find_gaps_splits_bullets_into_separate_gap_lines(tmp_path):
    spec_path = tmp_path / "boltstyle.md"
    spec_path.write_text(BOLT_STYLE_TEXT)
    config = cmdata_config(spec_path)

    coverage_path = tmp_path / "coverage.txt"
    coverage_path.write_text("")

    gap_lines, any_uncovered = find_gaps(
        config, str(coverage_path), doc_keys=[("cmdata-spec", None)]
    )
    assert any_uncovered is True
    texts = [g.text for g in gap_lines]
    assert any("funding_satoshis` to the amount" in t for t in texts)
    assert any("MUST NOT send a negative" in t for t in texts)
    assert any("channel_reserve_satoshis" in t for t in texts)
    # Each requirement is its own gap line, not one merged blob.
    assert len(gap_lines) >= 3


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
