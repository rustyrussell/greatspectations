import gzip
import io
import os

import pytest

from greatspectations import formats

# Mirrors the real structure of classic RFC-editor plaintext (as shipped
# by Debian's doc-rfc-std): a title page, a table of contents whose
# entries look like "N.  TITLE" plus a right-aligned page number, a
# form-feed page break preceded by a "...[Page N]" footer and followed
# by a "RFC NNNN ... Month Year" page header, and real "N.  TITLE"
# section headers (no trailing page number) at column 0 while body text
# is indented.
RFC_TEXT = (
    "Network Working Group\n"
    "Request for Comments: 9999                         March, 2020\n"
    "\n"
    "\n"
    "             EXAMPLE PROTOCOL SPECIFICATION\n"
    "\n"
    "\n"
    "                        TABLE OF CONTENTS\n"
    "\n"
    "\n"
    "1.  STATUS OF THIS MEMO                                              2\n"
    "\n"
    "2.  REQUIREMENTS                                                     2\n"
    "\n"
    "\n"
    "\n"
    "Example Org                                                     [Page 1]\n"
    "\x0c\n"
    "RFC 9999                                                      March 2020\n"
    "\n"
    "\n"
    "1.  STATUS OF THIS MEMO\n"
    "\n"
    "   This is a status paragraph.\n"
    "\n"
    "2.  REQUIREMENTS\n"
    "\n"
    "   A writer MUST set the length field before writing data.\n"
    "   A reader MUST validate the checksum.\n"
    "\n"
    "\n"
    "\n"
    "Example Org                                                     [Page 2]\n"
)


def write_rfc(tmp_path, name, text, gzipped):
    path = tmp_path / name
    if gzipped:
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(text)
    else:
        path.write_text(text)
    return str(path)


def test_rfc_text_splits_on_real_headers_only(tmp_path):
    path = write_rfc(tmp_path, "rfc9999.txt.gz", RFC_TEXT, gzipped=True)
    doc = formats.load("rfc-text", path)
    headers = [s.header for s in doc.sections]

    # Real section headers are present...
    assert "1.  STATUS OF THIS MEMO" in headers
    assert "2.  REQUIREMENTS" in headers
    # ...but the identically-shaped table-of-contents lines (which end
    # in a right-aligned page number) are not treated as headers.
    assert "1.  STATUS OF THIS MEMO                                              2" not in headers
    assert sum(1 for h in headers if "STATUS OF THIS MEMO" in h) == 1
    assert sum(1 for h in headers if "REQUIREMENTS" in h) == 1


DOTLEADER_TOC_TEXT = (
    "Example Org                                                Jane Doe\n"
    "Request for Comments: 8888                          January 2024\n"
    "\n"
    "                  Example Protocol Specification\n"
    "\n"
    "Table of Contents\n"
    "\n"
    "   1.  Introduction ......................................... 2\n"
    "   2.  Requirements ......................................... 2\n"
    "\n"
    "\n"
    "Example Org                                                 [Page 1]\n"
    "\x0c\n"
    "RFC 8888                Example Protocol             January 2024\n"
    "\n"
    "\n"
    "1.  Introduction\n"
    "\n"
    "   This is an example.\n"
    "\n"
    "2.  Requirements\n"
    "\n"
    "   A verifier MUST reject a packet whose checksum does not match.\n"
    "\n"
    "\n"
    "Example Org                                                 [Page 2]\n"
)


def test_rfc_text_ignores_dot_leader_toc(tmp_path):
    path = write_rfc(tmp_path, "rfc8888.txt.gz", DOTLEADER_TOC_TEXT, gzipped=True)
    doc = formats.load("rfc-text", path)
    headers = [s.header for s in doc.sections]

    assert "1.  Introduction" in headers
    assert "2.  Requirements" in headers
    assert sum(1 for h in headers if "Introduction" in h) == 1
    assert sum(1 for h in headers if "Requirements" in h) == 1


def test_rfc_text_strips_page_header_and_footer(tmp_path):
    path = write_rfc(tmp_path, "rfc9999.txt.gz", RFC_TEXT, gzipped=True)
    doc = formats.load("rfc-text", path)
    full_text = " ".join(s.text for s in doc.sections)

    assert "[Page" not in full_text
    assert "RFC 9999" not in full_text
    assert "\x0c" not in full_text


def test_rfc_text_requirements_section_content(tmp_path):
    path = write_rfc(tmp_path, "rfc9999.txt.gz", RFC_TEXT, gzipped=True)
    doc = formats.load("rfc-text", path)
    headers = [s.header for s in doc.sections]
    section = doc.sections[headers.index("2.  REQUIREMENTS")]

    assert "A writer MUST set the length field before writing data." in section.text
    assert "A reader MUST validate the checksum." in section.text


def test_rfc_text_linemap_survives_page_stripping(tmp_path):
    path = write_rfc(tmp_path, "rfc9999.txt.gz", RFC_TEXT, gzipped=True)
    doc = formats.load("rfc-text", path)
    headers = [s.header for s in doc.sections]
    section = doc.sections[headers.index("2.  REQUIREMENTS")]

    idx = section.text.index("MUST validate")
    original_lineno = section.linemap[idx]
    # Line numbers are assigned the same way the loader assigns them
    # (readlines(), which -- unlike str.splitlines() -- does not treat a
    # lone '\x0c' as its own line boundary).
    raw_lines = io.StringIO(RFC_TEXT).readlines()
    original_line = raw_lines[original_lineno - 1]
    assert "MUST validate" in original_line


def test_rfc_text_uncompressed_txt_also_works(tmp_path):
    path = write_rfc(tmp_path, "rfc9999.txt", RFC_TEXT, gzipped=False)
    doc = formats.load("rfc-text", path)
    headers = [s.header for s in doc.sections]
    assert "2.  REQUIREMENTS" in headers


def test_rfc_text_gzip_and_plain_produce_identical_sections(tmp_path):
    gz_path = write_rfc(tmp_path, "rfc9999.txt.gz", RFC_TEXT, gzipped=True)
    plain_path = write_rfc(tmp_path, "rfc9999-plain.txt", RFC_TEXT, gzipped=False)

    gz_doc = formats.load("rfc-text", gz_path)
    plain_doc = formats.load("rfc-text", plain_path)

    assert [s.header for s in gz_doc.sections] == [s.header for s in plain_doc.sections]
    assert [s.text for s in gz_doc.sections] == [s.text for s in plain_doc.sections]


_REAL_RFC1002 = "/usr/share/doc/RFC/standard/rfc1002.txt.gz"


@pytest.mark.skipif(
    not os.path.exists(_REAL_RFC1002),
    reason="doc-rfc-std package not installed",
)
def test_rfc_text_against_real_doc_rfc_std_package():
    doc = formats.load("rfc-text", _REAL_RFC1002)
    headers = [s.header for s in doc.sections]

    # The real ToC lists these same titles with trailing page numbers;
    # only the real (non-ToC) headers should show up as section headers.
    assert "1.  STATUS OF THIS MEMO" in headers
    assert headers.count("1.  STATUS OF THIS MEMO") == 1
    assert "4.1.  NAME FORMAT" in headers

    full_text = " ".join(s.text for s in doc.sections)
    assert "[Page" not in full_text
    assert "\x0c" not in full_text

    name_format = doc.sections[headers.index("4.1.  NAME FORMAT")]
    assert "NetBIOS name representation" in name_format.text
