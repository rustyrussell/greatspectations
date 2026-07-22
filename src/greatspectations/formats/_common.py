"""Shared helpers for formats that split a document into sections on
single header lines (markdown '#...', mediawiki '==...==', etc).
"""

import re
from typing import Callable, List, Tuple

from greatspectations.formats import Document, Section

_WHITESPACE_RE = re.compile(r"\s+")


def collapse_with_linemap(raw_lines: List[Tuple[int, str]]) -> Tuple[str, List[int]]:
    """Collapse whitespace across a list of (lineno, text) pairs.

    Returns (collapsed_text, linemap) where linemap[i] is the original
    line number for character i in collapsed_text.
    """
    result: List[str] = []
    linemap: List[int] = []
    in_ws = False
    ws_lineno = 1

    for lineno, line in raw_lines:
        for ch in line:
            if _WHITESPACE_RE.match(ch):
                if not in_ws:
                    in_ws = True
                    ws_lineno = lineno
            else:
                if in_ws:
                    result.append(" ")
                    linemap.append(ws_lineno)
                    in_ws = False
                result.append(ch)
                linemap.append(lineno)

    if in_ws:
        result.append(" ")
        linemap.append(ws_lineno)

    return "".join(result), linemap


def raw_with_linemap(raw_lines: List[Tuple[int, str]]) -> Tuple[str, List[int]]:
    """Concatenate a list of (lineno, text) pairs without collapsing
    whitespace. Returns (text, linemap) as per collapse_with_linemap.
    """
    chunks: List[str] = []
    linemap: List[int] = []
    for lineno, line in raw_lines:
        chunks.append(line)
        linemap.extend([lineno] * len(line))
    return "".join(chunks), linemap


def split_on_headers(path: str, is_header: Callable[[str], bool]) -> Document:
    """Load path and split it into sections wherever is_header(line) is
    true; the header line itself belongs to the section it introduces.
    """
    with open(path, encoding="utf-8") as f:
        raw = list(enumerate(f.readlines(), 1))

    raw_sections: List[List[Tuple[int, str]]] = []
    headers: List[str] = []
    cur: List[Tuple[int, str]] = []
    cur_header = ""
    for lineno, line in raw:
        if is_header(line):
            raw_sections.append(cur)
            headers.append(cur_header)
            cur = []
            cur_header = line.strip()
        cur.append((lineno, line))
    raw_sections.append(cur)
    headers.append(cur_header)

    sections = []
    for header, raw_section in zip(headers, raw_sections):
        text, linemap = collapse_with_linemap(raw_section)
        raw_text, raw_linemap = raw_with_linemap(raw_section)
        sections.append(
            Section(
                header=header, text=text, linemap=linemap,
                raw=raw_text, raw_linemap=raw_linemap,
            )
        )

    return Document(path=path, sections=sections)
