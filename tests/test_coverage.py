import pytest

from greatspectations.config import Config, Source
from greatspectations import formats
from greatspectations.coverage import (
    CoverageError,
    CoverageRecord,
    build_annotations,
    has_normative_keyword,
    load_coverage,
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

A reader MUST fail parsing if the file is too short.
A reader MUST also validate the signature before trusting any field.

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


def annotations_for(tmp_path, text, coverage_lines=(), doc_keys=None):
    """Write text as SPECIFICATION.md, write coverage_lines to a coverage
    file, and return (annotations for cmdata-spec, any_uncovered).
    """
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(text)
    config = cmdata_config(spec_path)

    coverage_path = tmp_path / "coverage.txt"
    coverage_path.write_text("".join(coverage_lines))

    by_doc, any_uncovered = build_annotations(
        config, str(coverage_path), doc_keys=doc_keys or [("cmdata-spec", None)]
    )
    return by_doc[("cmdata-spec", None)], any_uncovered


def test_build_annotations_marks_uncovered_requirement_as_gap(tmp_path):
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(SPEC_TEXT)
    config = cmdata_config(spec_path)

    doc = formats.load("markdown", str(spec_path))
    headers = [s.header for s in doc.sections]
    section = doc.sections[headers.index("### Reader Requirements")]
    covered_text = "A reader MUST fail parsing if the file is too short."
    start = section.text.index(covered_text)
    end = start + len(covered_text)

    coverage_path = tmp_path / "coverage.txt"
    coverage_path.write_text(
        "cmdata-spec - {} {} {} src.c 1\n".format(
            headers.index("### Reader Requirements"), start, end
        )
    )

    by_doc, any_uncovered = build_annotations(config, str(coverage_path))
    annotations = by_doc[("cmdata-spec", None)]
    assert any_uncovered is True

    by_status = {a.status for a in annotations}
    assert "covered" in by_status
    assert "gap" in by_status

    gap_lines = [a for a in annotations if a.status == "gap"]
    assert any("validate the signature" in a.text for a in gap_lines)
    covered_lines = [a for a in annotations if a.status == "covered"]
    assert any("fail parsing" in a.text for a in covered_lines)
    assert all(a.mentions >= 1 for a in covered_lines)

    # Rationale prose has no normative keyword, so it's neutral, not a
    # gap, even though nothing covers it.
    rationale = [a for a in annotations if "Uncovered rationale" in a.text]
    assert rationale and all(a.status == "neutral" for a in rationale)


def test_build_annotations_no_gap_when_fully_covered(tmp_path):
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(SPEC_TEXT)
    config = cmdata_config(spec_path)

    doc = formats.load("markdown", str(spec_path))
    headers = [s.header for s in doc.sections]
    si = headers.index("### Reader Requirements")
    section = doc.sections[si]

    coverage_path = tmp_path / "coverage.txt"
    coverage_path.write_text(
        "cmdata-spec - {} {} {} src.c 1\n".format(si, 0, len(section.text))
    )

    by_doc, any_uncovered = build_annotations(config, str(coverage_path))
    annotations = by_doc[("cmdata-spec", None)]
    assert any_uncovered is False
    assert not any(a.status == "gap" for a in annotations)


def test_build_annotations_counts_multiple_mentions(tmp_path):
    text = "# Spec\n\n## Body\n\nA server MUST validate the checksum.\n"
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(text)
    config = cmdata_config(spec_path)

    doc = formats.load("markdown", str(spec_path))
    si = [s.header for s in doc.sections].index("## Body")
    section = doc.sections[si]
    covered_text = "A server MUST validate the checksum."
    start = section.text.index(covered_text)
    end = start + len(covered_text)

    coverage_path = tmp_path / "coverage.txt"
    coverage_path.write_text(
        "cmdata-spec - {si} {start} {end} a.c 1\n"
        "cmdata-spec - {si} {start} {end} b.c 9\n".format(si=si, start=start, end=end)
    )

    by_doc, _ = build_annotations(config, str(coverage_path))
    annotations = by_doc[("cmdata-spec", None)]
    covered = [a for a in annotations if a.status == "covered"]
    assert len(covered) == 1
    assert covered[0].mentions == 2


RFC_STYLE_TEXT = """# Example Protocol

## Message Format

Implementations MUST validate the checksum field before processing the message.
This section explains the historical rationale for the checksum algorithm.
A receiver SHOULD log invalid checksums for diagnostic purposes.
"""


def test_build_annotations_uses_keywords_without_requirements_header(tmp_path):
    # RFCs rarely have a section literally titled "Requirements" (unlike
    # BOLT) -- normative keywords are what makes a line eligible.
    annotations, any_uncovered = annotations_for(tmp_path, RFC_STYLE_TEXT)
    assert any_uncovered is True

    by_text = {a.text: a.status for a in annotations}
    assert by_text["Implementations MUST validate the checksum field before processing the message."] == "gap"
    assert by_text["A receiver SHOULD log invalid checksums for diagnostic purposes."] == "gap"
    assert by_text["This section explains the historical rationale for the checksum algorithm."] == "neutral"


BIP_STYLE_TEXT = """# Example BIP

## Specification

Wallets must derive the address using the standard algorithm described
above, and clients should verify signatures before broadcasting a
transaction.
"""


def test_build_annotations_ignores_lowercase_prose(tmp_path):
    # BIPs rarely capitalize MUST/SHOULD the RFC 2119 way -- without
    # that signal there's nothing reliable to flag as a gap.
    annotations, any_uncovered = annotations_for(tmp_path, BIP_STYLE_TEXT)
    assert any_uncovered is False
    assert all(a.status == "neutral" for a in annotations if a.text.strip())


def test_build_annotations_skips_unresolvable_source(tmp_path, capsys):
    config = Config(sources={
        "bolt": Source(
            name="bolt", format="markdown", comment_marker="BOLT",
            dir=str(tmp_path / "nonexistent"), pattern="{id:02d}-*.md",
        )
    })
    coverage_path = tmp_path / "coverage.txt"
    coverage_path.write_text("bolt 11 0 0 5 src.c 1\n")

    by_doc, any_uncovered = build_annotations(config, str(coverage_path))
    assert by_doc == {}
    assert any_uncovered is False
    assert "cannot load" in capsys.readouterr().err
