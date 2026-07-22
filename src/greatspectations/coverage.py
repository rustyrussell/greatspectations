"""Record and report which spec text is quoted by no source comment.

write_coverage() ports check_quotes.py's write_coverage() (one record
per successfully-matched quote, appended atomically so parallel
`spectate check` invocations don't interleave partial lines); the rest
ports bolt-coverage.py's gap-reporting (by default restricted to
"Requirements" sections, as before). Both are generalized with a source
name column so coverage from multiple sources can share one file.

Coverage record: '{source} {id} {section_idx} {start} {end} {src_file}
{src_line}' -- id is '-' for single-file sources.
"""

import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from greatspectations import formats
from greatspectations.config import Config, ConfigError, IdType
from greatspectations.matching import CheckResult, section_linemap, section_text

DocKey = Tuple[str, Optional[IdType]]


class CoverageError(Exception):
    pass


@dataclass(frozen=True)
class CoverageRecord:
    source: str
    id: Optional[IdType]
    section_idx: int
    start: int
    end: int
    src_file: str
    src_line: int


@dataclass(frozen=True)
class GapLine:
    file: str
    line: int
    text: str


def _format_id(id_value: Optional[IdType]) -> str:
    return "-" if id_value is None else str(id_value)


def _parse_id(raw: str) -> Optional[IdType]:
    if raw == "-":
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


def write_coverage(path: str, results: Sequence[CheckResult]) -> None:
    """Append one coverage record per successfully-matched result."""
    for r in results:
        if not r.ok or r.match is None:
            continue
        record = "{} {} {} {} {} {} {}\n".format(
            r.quote.source, _format_id(r.quote.id), r.match.section_idx,
            r.match.start, r.match.end, r.quote.filename, r.quote.line,
        ).encode()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
        try:
            os.write(fd, record)
        finally:
            os.close(fd)


def load_coverage(path: str) -> Dict[DocKey, List[CoverageRecord]]:
    """Return {(source, id): [CoverageRecord, ...]} from a coverage file."""
    coverage: Dict[DocKey, List[CoverageRecord]] = defaultdict(list)
    try:
        f = open(path, encoding="utf-8")
    except FileNotFoundError:
        raise CoverageError("coverage file not found: {}".format(path)) from None

    with f:
        for lineno, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 7:
                print(
                    "{}:{}: bad coverage record (expected 7 fields): "
                    "{!r}".format(path, lineno, line),
                    file=sys.stderr,
                )
                continue
            source, raw_id, si, start, end, src_file, src_line = parts
            id_value = _parse_id(raw_id)
            record = CoverageRecord(
                source=source, id=id_value, section_idx=int(si),
                start=int(start), end=int(end),
                src_file=src_file, src_line=int(src_line),
            )
            coverage[(source, id_value)].append(record)
    return coverage


def merge_intervals(intervals: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Merge overlapping/adjacent [start, end) intervals."""
    merged: List[List[int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def adjacent_before(
    records: Sequence[CoverageRecord], gap_start: int
) -> List[CoverageRecord]:
    """Records whose covered range ends closest to (but not after) gap_start."""
    candidates = [r for r in records if r.end <= gap_start]
    if not candidates:
        return []
    max_end = max(r.end for r in candidates)
    return [r for r in candidates if r.end == max_end]


def adjacent_after(
    records: Sequence[CoverageRecord], gap_end: int
) -> List[CoverageRecord]:
    """Records whose covered range starts closest to (but not before) gap_end."""
    candidates = [r for r in records if r.start >= gap_end]
    if not candidates:
        return []
    min_start = min(r.start for r in candidates)
    return [r for r in candidates if r.start == min_start]


def snippet(text: str, start: int, end: int, tail: bool = False, maxlen: int = 60) -> str:
    """Return a short excerpt of text[start:end], from the tail or head."""
    s = text[start:end].strip()
    if tail:
        return ("..." + s[-maxlen:]) if len(s) > maxlen else ("..." + s)
    return (s[:maxlen] + "...") if len(s) > maxlen else (s + "...")


_HEADER_CONTENT_RE = re.compile(r"(#+\s+\S+\s+)")


def section_content_start(text: str) -> int:
    """Offset past a leading '### SectionTitle ' style header."""
    m = _HEADER_CONTENT_RE.match(text.lstrip())
    return m.end() if m else 0


_REQUIREMENTS_RE = re.compile(r"\brequirements\b", re.IGNORECASE)


def is_requirements_section(header: str) -> bool:
    """True if the section's header names a Requirements section (e.g.
    BOLT's '### Requirements' or SPECIFICATION.md's '### Reader
    Requirements').
    """
    return bool(_REQUIREMENTS_RE.search(header))


def _gaps_in_section(
    doc_path: str,
    text: str,
    linemap: List[int],
    section_records: Sequence[CoverageRecord],
) -> List[GapLine]:
    lines: List[GapLine] = []
    content_start = section_content_start(text)
    merged = merge_intervals([(r.start, r.end) for r in section_records])

    pos = content_start
    for m_start, m_end in merged:
        if m_start > pos:
            gap_text = text[pos:m_start].strip()
            if not gap_text:
                pos = max(pos, m_end)
                continue

            gap_lineno = linemap[pos] if pos < len(linemap) else 1
            before = adjacent_before(section_records, pos)
            after = adjacent_after(section_records, m_start)

            for r in before:
                lines.append(
                    GapLine(r.src_file, r.src_line, snippet(text, r.start, r.end, tail=True))
                )
            lines.append(GapLine(doc_path, gap_lineno, gap_text[:120]))
            for r in after:
                lines.append(
                    GapLine(r.src_file, r.src_line, snippet(text, r.start, r.end, tail=False))
                )

        pos = max(pos, m_end)

    if pos < len(text):
        gap_text = text[pos:].strip()
        if gap_text:
            gap_lineno = linemap[pos] if pos < len(linemap) else 1
            before = adjacent_before(section_records, pos)
            for r in before:
                lines.append(
                    GapLine(r.src_file, r.src_line, snippet(text, r.start, r.end, tail=True))
                )
            lines.append(GapLine(doc_path, gap_lineno, gap_text[:120]))

    return lines


def find_gaps(
    config: Config,
    coverage_path: str,
    doc_keys: Optional[Sequence[DocKey]] = None,
    all_sections: bool = False,
    mode: str = "normalized",
) -> Tuple[List[GapLine], bool]:
    """Report spec text not covered by any quote, for the given
    (source, id) documents (default: every document with coverage
    records). Returns (gap_lines, any_uncovered).
    """
    coverage = load_coverage(coverage_path)
    keys = (
        list(doc_keys) if doc_keys is not None
        else sorted(coverage.keys(), key=lambda k: (k[0], str(k[1])))
    )

    all_lines: List[GapLine] = []
    any_uncovered = False
    for source_name, id_value in keys:
        try:
            source = config[source_name]
            path = source.resolve(id_value)
            doc = formats.load(source.format, path)
        except (ConfigError, ValueError, OSError) as e:
            print(
                "cannot load {} {}: {}".format(source_name, _format_id(id_value), e),
                file=sys.stderr,
            )
            continue

        by_section: Dict[int, List[CoverageRecord]] = defaultdict(list)
        for rec in coverage.get((source_name, id_value), []):
            if 0 <= rec.section_idx < len(doc.sections):
                by_section[rec.section_idx].append(rec)

        for si, section in enumerate(doc.sections):
            text = section_text(section, mode)
            if not text.strip():
                continue
            if not all_sections and not is_requirements_section(section.header):
                continue

            records = by_section.get(si, [])
            lines = _gaps_in_section(doc.path, text, section_linemap(section, mode), records)
            if lines:
                any_uncovered = True
                all_lines.extend(lines)

    return all_lines, any_uncovered
