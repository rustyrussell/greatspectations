import pytest

from greatspectations import formats


BOLT_STYLE = """# BOLT #11: Invoice Protocol

Some intro text.

## Requirements

A writer:
  - MUST set `payment_hash` to the SHA256 of `payment_preimage`.

## Rationale

Blah   blah    spans
multiple lines.
"""


def test_markdown_load_splits_on_headers(tmp_path):
    path = tmp_path / "11-payment-encoding.md"
    path.write_text(BOLT_STYLE)

    doc = formats.load("markdown", str(path))
    assert doc.path == str(path)
    # Preamble (before first '#') + 3 headers = 4 sections.
    assert len(doc.sections) == 4
    assert doc.sections[0].header == ""
    assert doc.sections[1].header == "# BOLT #11: Invoice Protocol"
    assert doc.sections[2].header == "## Requirements"
    assert doc.sections[3].header == "## Rationale"


def test_markdown_collapses_whitespace(tmp_path):
    path = tmp_path / "spec.md"
    path.write_text(BOLT_STYLE)

    doc = formats.load("markdown", str(path))
    rationale = doc.sections[3].text
    assert "  " not in rationale
    assert "Blah blah spans multiple lines." in rationale


def test_markdown_raw_is_uncollapsed(tmp_path):
    path = tmp_path / "spec.md"
    path.write_text(BOLT_STYLE)

    doc = formats.load("markdown", str(path))
    rationale = doc.sections[3]
    assert "Blah   blah    spans\nmultiple lines.\n" in rationale.raw
    assert len(rationale.raw) == len(rationale.raw_linemap)


def test_markdown_linemap_tracks_original_lines(tmp_path):
    path = tmp_path / "spec.md"
    path.write_text(BOLT_STYLE)

    doc = formats.load("markdown", str(path))
    requirements = doc.sections[2]
    idx = requirements.text.index("MUST set")
    original_lineno = requirements.linemap[idx]
    original_line = path.read_text().splitlines()[original_lineno - 1]
    assert "MUST set" in original_line


def test_markdown_empty_file(tmp_path):
    path = tmp_path / "empty.md"
    path.write_text("")

    doc = formats.load("markdown", str(path))
    assert len(doc.sections) == 1
    assert doc.sections[0].text == ""
    assert doc.sections[0].linemap == []


def test_markdown_no_headers(tmp_path):
    path = tmp_path / "no-headers.md"
    path.write_text("just some\nplain text\n")

    doc = formats.load("markdown", str(path))
    assert len(doc.sections) == 1
    assert doc.sections[0].header == ""
    assert doc.sections[0].text == "just some plain text "


def test_single_file_markdown_spec_works_same_as_bolt(tmp_path):
    # SPECIFICATION.md-style docs use the same '#' header structure.
    text = """# Century Metadata Format Specification

## Introduction

Some intro.

### Reader Requirements

A reader MUST fail parsing if the file is too short.

### Writer Requirements

A writer MUST fail parsing if the file is too short.
"""
    path = tmp_path / "SPECIFICATION.md"
    path.write_text(text)

    doc = formats.load("markdown", str(path))
    headers = [s.header for s in doc.sections]
    assert "### Reader Requirements" in headers
    assert "### Writer Requirements" in headers
    reader = doc.sections[headers.index("### Reader Requirements")]
    writer = doc.sections[headers.index("### Writer Requirements")]
    assert "reader MUST fail parsing" in reader.text
    assert "writer MUST fail parsing" in writer.text


def test_unknown_format_raises(tmp_path):
    path = tmp_path / "spec.md"
    path.write_text("# Hi\n")
    with pytest.raises(ValueError, match="unknown format"):
        formats.load("nonexistent-format", str(path))


BIP_STYLE = """<pre>
  BIP: 340
  Title: Schnorr Signatures
</pre>

==Abstract==

This document proposes a standard for 64-byte Schnorr signatures.

==Specification==

A signer MUST use a 32-byte private key.

==Rationale==

Blah   blah    spans
multiple lines.
"""


def test_mediawiki_load_splits_on_headers(tmp_path):
    path = tmp_path / "bip-0340.mediawiki"
    path.write_text(BIP_STYLE)

    doc = formats.load("mediawiki", str(path))
    headers = [s.header for s in doc.sections]
    assert headers[0] == ""  # preamble (the <pre> preface block)
    assert "==Abstract==" in headers
    assert "==Specification==" in headers
    assert "==Rationale==" in headers


def test_mediawiki_collapses_whitespace(tmp_path):
    path = tmp_path / "bip-0340.mediawiki"
    path.write_text(BIP_STYLE)

    doc = formats.load("mediawiki", str(path))
    headers = [s.header for s in doc.sections]
    rationale = doc.sections[headers.index("==Rationale==")].text
    assert "Blah blah spans multiple lines." in rationale


def test_mediawiki_linemap_tracks_original_lines(tmp_path):
    path = tmp_path / "bip-0340.mediawiki"
    path.write_text(BIP_STYLE)

    doc = formats.load("mediawiki", str(path))
    headers = [s.header for s in doc.sections]
    spec_section = doc.sections[headers.index("==Specification==")]
    idx = spec_section.text.index("MUST use")
    original_lineno = spec_section.linemap[idx]
    original_line = path.read_text().splitlines()[original_lineno - 1]
    assert "MUST use" in original_line


def test_mediawiki_does_not_match_markdown_headers(tmp_path):
    path = tmp_path / "bip.mediawiki"
    path.write_text("# not a mediawiki header\n\n==Real Header==\ntext\n")

    doc = formats.load("mediawiki", str(path))
    headers = [s.header for s in doc.sections]
    assert headers == ["", "==Real Header=="]
