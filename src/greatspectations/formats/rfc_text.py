"""RFC plaintext format: the classic RFC-editor .txt layout, as shipped
by Debian's doc-rfc-std package (/usr/share/doc/RFC/<category>/rfcNNNN.txt.gz).

Files are transparently gunzipped, page headers/footers and form-feed
page breaks are stripped (so a requirement split across a page boundary
still reads as one contiguous section), and the document is split into
sections on column-0 numbered headers ('N.', 'N.N.', ...) -- while
ignoring the table of contents, whose entries have the same numbered
shape but end in a right-aligned page number, which a real section
header never does.
"""

import gzip
import re
from typing import List, Tuple

from greatspectations.formats import Document, register
from greatspectations.formats._common import split_on_headers

_FOOTER_RE = re.compile(r"\[Page\s+\d+\]\s*$")
_HEADER_LINE_RE = re.compile(r"^(\d+(?:\.\d+)*\.?)[ \t]+\S")
# A right-aligned page number, padded with spaces or (older RFCs) dot
# leaders, e.g. "...   4" or "....................... 4".
_TOC_TRAILING_PAGENUM_RE = re.compile(r"[ \t.]{2,}\d+[ \t]*$")


def _is_section_header(line: str) -> bool:
    stripped = line.rstrip("\n")
    if not _HEADER_LINE_RE.match(stripped):
        return False
    # A table-of-contents entry has the same 'N. Title' shape as a real
    # header, but ends with a right-aligned page number; a real header
    # never does.
    return not _TOC_TRAILING_PAGENUM_RE.search(stripped)


def _read_lines(path: str) -> List[str]:
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:  # type: ignore[operator]
        return f.readlines()


def _strip_pages(numbered_lines: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    """Drop form-feed page breaks, the footer line before each one (e.g.
    'Some Corp                                            [Page 4]'),
    and the page-header block after each one (blank lines, then a run
    of non-blank lines -- typically 'RFC NNNN ... Month Year' and
    sometimes a second title line).

    Original line numbers are preserved on every retained line (some
    numbers are simply skipped over) so linemaps still point at real
    lines in the source file.
    """
    result: List[Tuple[int, str]] = []
    i = 0
    n = len(numbered_lines)
    while i < n:
        lineno, line = numbered_lines[i]
        if "\x0c" in line:
            if result and _FOOTER_RE.search(result[-1][1]):
                result.pop()
            i += 1
            while i < n and numbered_lines[i][1].strip() == "":
                i += 1
            while i < n and numbered_lines[i][1].strip() != "":
                i += 1
            continue
        result.append((lineno, line))
        i += 1

    # The last page has no following form feed to trigger the footer
    # check above; drop its trailing footer line too, if present.
    if result and _FOOTER_RE.search(result[-1][1]):
        result.pop()

    return result


def load(path: str) -> Document:
    raw_lines = _read_lines(path)
    numbered = _strip_pages(list(enumerate(raw_lines, 1)))
    return split_on_headers(path, numbered, _is_section_header)


register("rfc-text", load)
