"""Parses 'normative' config entries: places or ranges in a spec
document that must be quoted by something, as a precise alternative (or
supplement) to coverage.py's RFC 2119/8174 keyword heuristic. Meant to
be authored once, by an LLM or by hand for simple documents.

Each entry is a string naming one place or range, 1-indexed and
inclusive on every bound given:

    place   := <line>[':' <linepos>]
    linepos := <col>'-'<col> | <col>'-' | '-'<col>
    entry   := place | place'-' | '-'place | place'-'place

A standalone place's colon-part is the full linepos grammar (a
mandatory dash, so a lone place can itself express a same-line column
range, e.g. '42:10-20' -- line 42, columns 10 through 20). A place used
as one endpoint of a two-place range instead takes a bare column (no
dash), since the range's own '-' already serves as the separator --
e.g. '42:10-50:20' means column 10 of line 42 through column 20 of line
50, not two nested same-line ranges (which would be ambiguous: linepos
already requires a dash, so a second dash-bearing linepos on each side
of a range separator can't be told apart from the separator itself).

A missing line bound (leading/trailing '-' with nothing after/before
it) means "start of file" / "end of file"; a missing column bound
within a given line means "start of that line" / "end of that line".

The standalone-place form is always tried first and matches greedily,
which has two consequences worth knowing:

  - 'N:C-' (colon, then a trailing dash) always parses as "line N,
    column C to the end of that line", never as "line N column C to
    the end of the file". To span from a precise column to end of
    file, name the end place explicitly (e.g. 'N:C-<last-line>').
  - 'N:C-M' (colon, then a bare trailing number with no second colon)
    always parses as "line N, columns C through M" (same line), never
    as "line N column C through line M". To cross lines, give the end
    place its own line number after a colon (e.g. 'N:C-M:1').
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

_PLACE_RE = re.compile(r"^(\d+)(?::(\d*)-(\d*))?$")
_BARE_PLACE_RE = re.compile(r"^(\d+)(?::(\d+))?$")


class PlaceSyntaxError(ValueError):
    pass


@dataclass(frozen=True)
class NormativeSpan:
    """A span of spec text that must be quoted, 1-indexed and inclusive.

    A None bound means unbounded in that direction: start_line=None is
    "from the start of the file", end_col=None is "through the end of
    that line", etc.
    """

    start_line: Optional[int]
    start_col: Optional[int]
    end_line: Optional[int]
    end_col: Optional[int]


def _bare_place(text: str) -> Optional[Tuple[int, Optional[int]]]:
    """Parse a range endpoint: line[:col], no dash allowed. None if
    text doesn't match, or line/col are out of 1-indexed range.
    """
    m = _BARE_PLACE_RE.match(text)
    if not m:
        return None
    line = int(m.group(1))
    col = int(m.group(2)) if m.group(2) else None
    if line < 1 or (col is not None and col < 1):
        return None
    return line, col


def _start_key(line: int, col: Optional[int]) -> Tuple[int, float]:
    return (line, col if col is not None else -1)


def _end_key(line: int, col: Optional[int]) -> Tuple[int, float]:
    return (line, col if col is not None else float("inf"))


def parse_place(spec: str) -> NormativeSpan:
    """Parse one 'normative' array entry into a NormativeSpan."""
    spec = spec.strip()

    m = _PLACE_RE.match(spec)
    if m:
        line = int(m.group(1))
        start_col = int(m.group(2)) if m.group(2) else None
        end_col = int(m.group(3)) if m.group(3) else None
        if line < 1 or (start_col is not None and start_col < 1) or (
            end_col is not None and end_col < 1
        ):
            raise PlaceSyntaxError(
                "invalid place {!r}: line/column numbers are 1-indexed".format(spec)
            )
        if start_col is not None and end_col is not None and end_col < start_col:
            raise PlaceSyntaxError(
                "invalid place {!r}: end column before start column".format(spec)
            )
        return NormativeSpan(line, start_col, line, end_col)

    if spec.startswith("-"):
        end = _bare_place(spec[1:])
        if end is not None:
            return NormativeSpan(None, None, end[0], end[1])

    elif spec.endswith("-"):
        start = _bare_place(spec[:-1])
        if start is not None:
            return NormativeSpan(start[0], start[1], None, None)

    else:
        parts = spec.split("-")
        if len(parts) == 2:
            start = _bare_place(parts[0])
            end = _bare_place(parts[1])
            if start is not None and end is not None:
                if _end_key(*end) < _start_key(*start):
                    raise PlaceSyntaxError(
                        "invalid place {!r}: end before start".format(spec)
                    )
                return NormativeSpan(start[0], start[1], end[0], end[1])

    raise PlaceSyntaxError("invalid place spec: {!r}".format(spec))


def parse_normative(specs: List[str]) -> List[NormativeSpan]:
    """Parse a list of place-spec strings (one 'normative' array)."""
    return [parse_place(s) for s in specs]
