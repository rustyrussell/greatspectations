"""Markdown format: splits a document into sections on '#'-prefixed
header lines. Used for BOLT spec files and single-file markdown specs
(e.g. SPECIFICATION.md) alike.
"""

import re
from typing import List, Tuple

from greatspectations.formats import Document, Section, register

_WHITESPACE_RE = re.compile(r"\s+")


def _collapse_with_linemap(raw_lines: List[Tuple[int, str]]) -> Tuple[str, List[int]]:
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


def load(path: str) -> Document:
    with open(path, encoding="utf-8") as f:
        raw = list(enumerate(f.readlines(), 1))

    # Split into sections on lines that start with '#'; the header line
    # itself belongs to the section it introduces.
    raw_sections: List[List[Tuple[int, str]]] = []
    headers: List[str] = []
    cur: List[Tuple[int, str]] = []
    cur_header = ""
    for lineno, line in raw:
        if line.startswith("#"):
            raw_sections.append(cur)
            headers.append(cur_header)
            cur = []
            cur_header = line.strip()
        cur.append((lineno, line))
    raw_sections.append(cur)
    headers.append(cur_header)

    sections = []
    for header, raw_section in zip(headers, raw_sections):
        text, linemap = _collapse_with_linemap(raw_section)
        sections.append(Section(header=header, text=text, linemap=linemap))

    return Document(path=path, sections=sections)


register("markdown", load)
