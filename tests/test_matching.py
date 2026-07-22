import pytest

from greatspectations import formats
from greatspectations.config import Config, Source
from greatspectations.matching import (
    Match,
    MatchingError,
    check_quotes,
    find_quote,
    find_quote_immediate,
    sections_matching_hint,
)
from greatspectations.quotes import Quote


def load_doc(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return formats.load("markdown", str(path))


SPEC_TEXT = """# Spec

## Requirements

A writer MUST set the length field before writing data.

## Rationale

Some rationale text here, spanning
multiple lines for testing.
"""


def test_find_quote_simple_match(tmp_path):
    doc = load_doc(tmp_path, "spec.md", SPEC_TEXT)
    headers = [s.header for s in doc.sections]
    requirements_idx = headers.index("## Requirements")

    # Restrict the start section explicitly: sections preceding the
    # match (here, the empty preamble and the '# Spec' title section)
    # don't contain the text, so find_quote's cross-section fallback
    # would otherwise credit start=0 in the *found* section rather than
    # the text's true offset -- this is the same "start credited as 0
    # for a cross-section match" behavior check_quotes.py's find_quote
    # documents, ported unchanged; it's why section-hint restriction is
    # useful beyond just avoiding false positives.
    m = find_quote(
        "A writer MUST set the length field", doc.sections,
        candidate_indices=[requirements_idx],
    )
    assert m is not None
    assert doc.sections[m.section_idx].text[m.start:m.end] == (
        "A writer MUST set the length field"
    )


def test_find_quote_wildcard_within_section(tmp_path):
    doc = load_doc(tmp_path, "spec.md", SPEC_TEXT)
    m = find_quote("A writer MUST...before writing data.", doc.sections)
    assert m is not None
    assert "MUST" in doc.sections[m.section_idx].text[m.start:m.end]
    assert doc.sections[m.section_idx].text[m.start:m.end].endswith(
        "before writing data."
    )


def test_find_quote_no_match_returns_none(tmp_path):
    doc = load_doc(tmp_path, "spec.md", SPEC_TEXT)
    assert find_quote("this text does not appear", doc.sections) is None


def test_find_quote_wildcard_crosses_section(tmp_path):
    doc = load_doc(tmp_path, "spec.md", SPEC_TEXT)
    # Starts in Requirements, ends in Rationale.
    m = find_quote("length field...Some rationale text", doc.sections)
    assert m is not None


def test_find_quote_candidate_indices_restricts_search(tmp_path):
    doc = load_doc(tmp_path, "spec.md", SPEC_TEXT)
    headers = [s.header for s in doc.sections]
    rationale_idx = headers.index("## Rationale")
    requirements_idx = headers.index("## Requirements")

    # Text only exists in Requirements; restricting candidates to just
    # Rationale should fail to find it even though it exists elsewhere.
    assert find_quote(
        "A writer MUST set", doc.sections, candidate_indices=[rationale_idx]
    ) is None
    assert find_quote(
        "A writer MUST set", doc.sections, candidate_indices=[requirements_idx]
    ) is not None


def test_sections_matching_hint(tmp_path):
    doc = load_doc(tmp_path, "spec.md", SPEC_TEXT)
    assert sections_matching_hint(doc.sections, "Rationale") == [
        i for i, s in enumerate(doc.sections) if "Rationale" in s.header
    ]
    assert sections_matching_hint(doc.sections, "rationale") == sections_matching_hint(
        doc.sections, "Rationale"
    )  # case-insensitive
    assert sections_matching_hint(doc.sections, None) == list(range(len(doc.sections)))
    assert sections_matching_hint(doc.sections, "NoSuchHeader") == []


def test_find_quote_immediate_success(tmp_path):
    doc = load_doc(tmp_path, "spec.md", SPEC_TEXT)
    headers = [s.header for s in doc.sections]
    section = doc.sections[headers.index("## Requirements")]
    first = find_quote("A writer MUST set the length field", [section])
    assert first is not None
    following = find_quote_immediate(
        "...before writing data.", section.text, first.end
    )
    assert following is not None


def test_find_quote_immediate_failure_when_not_adjacent(tmp_path):
    doc = load_doc(tmp_path, "spec.md", SPEC_TEXT)
    headers = [s.header for s in doc.sections]
    section = doc.sections[headers.index("## Requirements")]
    result = find_quote_immediate("Some rationale", section.text, 0)
    assert result is None


EXACT_TEXT = """# Spec

## Requirements

A writer   MUST    set
the length field.
"""


def test_exact_mode_requires_literal_whitespace(tmp_path):
    doc = load_doc(tmp_path, "spec.md", EXACT_TEXT)
    headers = [s.header for s in doc.sections]
    section = doc.sections[headers.index("## Requirements")]

    # Normalized mode collapses the irregular spacing, so this matches.
    assert find_quote(
        "A writer MUST set the length field.", doc.sections, mode="normalized",
        candidate_indices=[headers.index("## Requirements")],
    ) is not None

    # Exact mode requires the literal (uncollapsed) spacing.
    assert find_quote(
        "A writer MUST set the length field.", doc.sections, mode="exact",
        candidate_indices=[headers.index("## Requirements")],
    ) is None
    assert find_quote(
        "A writer   MUST    set\nthe length field.", doc.sections, mode="exact",
        candidate_indices=[headers.index("## Requirements")],
    ) is not None


def make_config(sources) -> Config:
    return Config(sources={s.name: s for s in sources})


def cmdata_source(tmp_path, spec_path) -> Source:
    return Source(
        name="cmdata-spec", format="markdown", comment_marker="CMDATA-SPEC",
        file=str(spec_path),
    )


DUPLICATE_WORDING_SPEC = """# Century Metadata Format Specification

### Reader Requirements

A reader MUST fail parsing if the length is wrong.

### Writer Requirements

A writer MUST fail parsing if the length is wrong.
"""


def test_check_quotes_section_hint_avoids_false_positive(tmp_path):
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(DUPLICATE_WORDING_SPEC)
    config = make_config([cmdata_source(tmp_path, spec_path)])

    reader_quote = Quote(
        source="cmdata-spec", id=None, section_hint="Reader Requirements",
        filename="reader.c", line=1,
        text="A reader MUST fail parsing if the length is wrong.",
    )
    writer_quote = Quote(
        source="cmdata-spec", id=None, section_hint="Writer Requirements",
        filename="writer.c", line=1,
        text="A writer MUST fail parsing if the length is wrong.",
    )
    results = check_quotes(config, [reader_quote, writer_quote])
    assert all(r.ok for r in results)

    doc = formats.load("markdown", str(spec_path))
    headers = [s.header for s in doc.sections]
    reader_result, writer_result = results
    assert reader_result.match is not None
    assert writer_result.match is not None
    assert headers[reader_result.match.section_idx] == "### Reader Requirements"
    assert headers[writer_result.match.section_idx] == "### Writer Requirements"


def test_check_quotes_wrong_hint_fails(tmp_path):
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(DUPLICATE_WORDING_SPEC)
    config = make_config([cmdata_source(tmp_path, spec_path)])

    quote = Quote(
        source="cmdata-spec", id=None, section_hint="Nonexistent Section",
        filename="x.c", line=1, text="A reader MUST fail parsing",
    )
    results = check_quotes(config, [quote])
    assert len(results) == 1
    assert not results[0].ok
    assert "no section header matching hint" in results[0].error


def test_check_quotes_dotdotdot_immediate_followup(tmp_path):
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(SPEC_TEXT)
    config = make_config([cmdata_source(tmp_path, spec_path)])

    first = Quote(
        source="cmdata-spec", id=None, section_hint=None,
        filename="x.c", line=1, text="A writer MUST set the length field",
    )
    second = Quote(
        source="cmdata-spec", id=None, section_hint=None,
        filename="x.c", line=2, text="... before writing data.",
    )
    results = check_quotes(config, [first, second])
    assert all(r.ok for r in results)


def test_check_quotes_dotdotdot_without_previous_fails(tmp_path):
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(SPEC_TEXT)
    config = make_config([cmdata_source(tmp_path, spec_path)])

    quote = Quote(
        source="cmdata-spec", id=None, section_hint=None,
        filename="x.c", line=1, text="...before writing data.",
    )
    results = check_quotes(config, [quote])
    assert not results[0].ok
    assert "no previous" in results[0].error


def test_check_quotes_unresolvable_source_reports_failure(tmp_path):
    config = make_config([
        Source(
            name="bolt", format="markdown", comment_marker="BOLT",
            dir=str(tmp_path / "nonexistent"), pattern="{id:02d}-*.md",
        )
    ])
    quote = Quote(
        source="bolt", id=11, section_hint=None,
        filename="x.c", line=1, text="anything",
    )
    results = check_quotes(config, [quote])
    assert len(results) == 1
    assert not results[0].ok
    assert results[0].error is not None


def test_check_quotes_unknown_mode_raises(tmp_path):
    spec_path = tmp_path / "SPECIFICATION.md"
    spec_path.write_text(SPEC_TEXT)
    config = make_config([cmdata_source(tmp_path, spec_path)])
    quote = Quote(
        source="cmdata-spec", id=None, section_hint=None,
        filename="x.c", line=1, text="anything",
    )
    with pytest.raises(MatchingError):
        check_quotes(config, [quote], mode="bogus-mode")
