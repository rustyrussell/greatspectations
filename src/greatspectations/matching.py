"""Match gathered Quotes against the spec sections they claim to quote.

Ports find_quote()/find_quote_immediate() from check_quotes.py, plus the
per-quote/per-file bookkeeping from its main() loop (tracking the last
matched section so a quote starting with '...' can require it
immediately follow the previous one). Two additions over the original:

  - mode="exact" matches against each section's raw (uncollapsed) text
    instead of the whitespace-normalized text, for specs where literal
    byte matching matters.
  - A quote's section_hint (see quotes.py) restricts the search to
    sections whose header contains that text, so near-identical wording
    repeated across sections (e.g. Reader/Writer Requirements) can't
    silently cross-match.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from greatspectations import formats
from greatspectations.config import Config, ConfigError, IdType
from greatspectations.formats import Document, Section
from greatspectations.quotes import Quote

MODES = ("normalized", "exact")


class MatchingError(Exception):
    pass


@dataclass(frozen=True)
class Match:
    section_idx: int
    start: int
    end: int


@dataclass(frozen=True)
class CheckResult:
    quote: Quote
    ok: bool
    error: Optional[str] = None
    match: Optional[Match] = None


def section_text(section: Section, mode: str) -> str:
    return section.text if mode == "normalized" else section.raw


def section_linemap(section: Section, mode: str) -> List[int]:
    return section.linemap if mode == "normalized" else section.raw_linemap


def sections_matching_hint(
    sections: Sequence[Section], hint: Optional[str]
) -> List[int]:
    """Indices of sections whose header contains hint (case-insensitive).

    With hint=None, every section index is returned.
    """
    if hint is None:
        return list(range(len(sections)))
    needle = hint.lower()
    return [i for i, s in enumerate(sections) if needle in s.header.lower()]


def find_quote(
    text: str,
    sections: Sequence[Section],
    mode: str = "normalized",
    candidate_indices: Optional[Sequence[int]] = None,
) -> Optional[Match]:
    """Search for text (with '...' wildcards) across sections.

    candidate_indices restricts both the set of allowed start sections
    and the sections a '...' may cross into (in index order); defaults
    to all sections. Returns None on failure.
    """
    if candidate_indices is None:
        candidate_indices = list(range(len(sections)))
    textparts = text.split("...")

    for start_pos, start_si in enumerate(candidate_indices):
        cur_pos = start_pos
        cur_si = start_si
        cur_text = section_text(sections[start_si], mode)
        off = 0
        match_start = -1
        success = True
        for i, part in enumerate(textparts):
            new_off = cur_text.find(part, off)
            if new_off == -1:
                search_part = part.lstrip() if mode == "normalized" else part
                found = False
                for next_pos in range(cur_pos + 1, len(candidate_indices)):
                    next_si = candidate_indices[next_pos]
                    next_text = section_text(sections[next_si], mode)
                    new_off = next_text.find(search_part, 0)
                    if new_off != -1:
                        cur_pos = next_pos
                        cur_si = next_si
                        cur_text = next_text
                        if i == 0 and match_start < 0:
                            match_start = new_off
                        off = new_off + len(search_part)
                        found = True
                        break
                if not found:
                    success = False
                    break
            else:
                if i == 0 and match_start < 0:
                    match_start = new_off
                off = new_off + len(part)
        if success:
            return Match(
                section_idx=cur_si,
                start=(match_start if match_start >= 0 else 0),
                end=off,
            )
    return None


def find_quote_immediate(
    text: str, section_text: str, start: int, mode: str = "normalized"
) -> Optional[Tuple[int, int]]:
    """Find text in section_text starting immediately at position start.

    Allows a single space separator in normalized mode (whitespace is
    already collapsed to single spaces there); exact mode requires a
    literal immediate match. text may still contain '...' wildcards for
    its own internal matching. Returns (match_start, end) or None.
    """
    textparts = text.split("...")
    off = start
    if mode == "normalized":
        if off < len(section_text) and section_text[off] == " ":
            off += 1
        first_part = textparts[0].lstrip(" ")
    else:
        first_part = textparts[0]

    match_start = off
    if not section_text[off:].startswith(first_part):
        return None
    off += len(first_part)
    for part in textparts[1:]:
        new_off = section_text.find(part, off)
        if new_off == -1:
            return None
        off = new_off + len(part)
    return match_start, off


def check_quotes(
    config: Config, quotes: Sequence[Quote], mode: str = "normalized"
) -> List[CheckResult]:
    """Check every quote against its source document.

    Always processes every quote (never stops at the first failure) so
    callers get a complete result set for reporting or CI output.
    """
    if mode not in MODES:
        raise MatchingError(
            "unknown mode {!r} (known: {})".format(mode, ", ".join(MODES))
        )

    results: List[CheckResult] = []
    doc_cache: Dict[Tuple[str, Optional[IdType]], Document] = {}
    # Tracks, per (source, id, filename), the (section_idx, end) of the
    # last successfully matched quote -- for a following '...' quote.
    last: Dict[Tuple[str, Optional[IdType], str], Tuple[int, int]] = {}

    for q in quotes:
        doc_key = (q.source, q.id)
        if doc_key not in doc_cache:
            try:
                source = config[q.source]
                path = source.resolve(q.id)
                doc_cache[doc_key] = formats.load(source.format, path)
            except (ConfigError, ValueError, OSError) as e:
                results.append(CheckResult(q, False, error=str(e)))
                continue
        doc = doc_cache[doc_key]
        track_key = (q.source, q.id, q.filename)

        if q.text.startswith("..."):
            if track_key not in last:
                results.append(
                    CheckResult(
                        q, False,
                        error="'...' at start of quote but no previous "
                        "matched quote for this source in this file",
                    )
                )
                continue
            last_si, last_end = last[track_key]
            sect_text = section_text(doc.sections[last_si], mode)
            found = find_quote_immediate(q.text[3:], sect_text, last_end, mode)
            if found is None:
                results.append(
                    CheckResult(
                        q, False,
                        error="cannot find match (must immediately follow "
                        "previous quote)",
                    )
                )
                continue
            start, end = found
            match: Optional[Match] = Match(section_idx=last_si, start=start, end=end)
        else:
            if q.section_hint is not None:
                candidates = sections_matching_hint(doc.sections, q.section_hint)
                if not candidates:
                    results.append(
                        CheckResult(
                            q, False,
                            error="no section header matching hint "
                            "'{}'".format(q.section_hint),
                        )
                    )
                    continue
            else:
                candidates = None
            match = find_quote(q.text, doc.sections, mode=mode, candidate_indices=candidates)
            if match is None:
                results.append(CheckResult(q, False, error="cannot find match"))
                continue

        assert match is not None
        results.append(CheckResult(q, True, match=match))
        last[track_key] = (match.section_idx, match.end)

    return results
