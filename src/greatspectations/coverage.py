"""Record and report which spec text is quoted by no source comment.

write_coverage() ports check_quotes.py's write_coverage() (one record
per successfully-matched quote, appended atomically so parallel
`spectate check` invocations don't interleave partial lines).

build_annotations() replaces bolt-coverage.py's Requirements-section-only
gap report with a full-document line annotation: every physical line of
every considered document gets a status --

  - "covered": at least one coverage record's matched range touches this
    line (mentions counts how many distinct quotes do).
  - "gap": no record touches it, but it contains an RFC 2119/8174
    normative keyword (MUST/SHOULD/MAY/...), so it looks like a
    requirement that nothing quotes.
  - "neutral": neither -- ordinary prose, headers, examples, rationale.

The keyword check is deliberately case-sensitive: RFC 8174 limits
normative force to the all-caps form, which BOLT and most modern RFCs
follow -- and it's also what keeps this quiet on plain English
"must"/"should" in pre-2119 RFCs and most BIPs, neither of which
reliably use the convention (see README).

Status is decided per physical line, not per sentence: a line is
"covered" if *any* part of it is touched by a matched quote. In the rare
case where two different requirements are hard-wrapped onto the same
physical line and only one of them is quoted, the other's keyword can
be masked and the line reported covered anyway -- a deliberate
precision/simplicity tradeoff so each line gets exactly one status.

Coverage record: '{source} {id} {section_idx} {start} {end} {src_file}
{src_line}' -- id is '-' for single-file sources.
"""

import itertools
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from greatspectations import formats
from greatspectations.config import Config, ConfigError, IdType
from greatspectations.formats import Section
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
class LineAnnotation:
    """One physical line of a spec document, with its coverage status.

    status is "covered" (mentions counts the distinct quotes touching
    this line), "gap" (a normative keyword, but no quote touches it), or
    "neutral" (neither).
    """

    file: str
    line: int
    text: str
    status: str
    mentions: int = 0


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


# RFC 2119/8174 keywords. See module docstring for why this is
# case-sensitive.
_NORMATIVE_KEYWORD_RE = re.compile(
    r"\b(?:MUST|SHALL|SHOULD|REQUIRED|RECOMMENDED|OPTIONAL|MAY)\b"
)


def has_normative_keyword(text: str) -> bool:
    """True if text contains an RFC 2119/8174 normative keyword."""
    return bool(_NORMATIVE_KEYWORD_RE.search(text))


def _physical_lines(section: Section) -> Iterator[Tuple[int, str]]:
    """Reconstruct (lineno, line_text) pairs from a section's raw text,
    grouping raw/raw_linemap by original line number. line_text has its
    trailing newline stripped.
    """
    for lineno, group in itertools.groupby(
        zip(section.raw_linemap, section.raw), key=lambda pair: pair[0]
    ):
        yield lineno, "".join(ch for _, ch in group).rstrip("\n")


def _record_line_range(record: CoverageRecord, linemap: List[int]) -> Tuple[int, int]:
    """The inclusive (first_line, last_line) a matched quote's range
    touches, per linemap (mode-specific: see section_linemap()).
    """
    if not linemap:
        return (1, 1)
    start_idx = min(record.start, len(linemap) - 1)
    end_idx = min(max(record.end - 1, record.start), len(linemap) - 1)
    first, last = linemap[start_idx], linemap[end_idx]
    return (first, last) if first <= last else (last, first)


def _annotate_section(
    doc_path: str, section: Section, records: Sequence[CoverageRecord], mode: str,
) -> List[LineAnnotation]:
    linemap = section_linemap(section, mode)
    mentions_by_line: Dict[int, int] = defaultdict(int)
    for r in records:
        first, last = _record_line_range(r, linemap)
        for lineno in range(first, last + 1):
            mentions_by_line[lineno] += 1

    annotations = []
    for lineno, text in _physical_lines(section):
        mentions = mentions_by_line.get(lineno, 0)
        if mentions:
            status = "covered"
        elif has_normative_keyword(text):
            status = "gap"
        else:
            status = "neutral"
        annotations.append(LineAnnotation(doc_path, lineno, text, status, mentions))
    return annotations


def build_annotations(
    config: Config,
    coverage_path: str,
    doc_keys: Optional[Sequence[DocKey]] = None,
    mode: str = "normalized",
) -> Tuple[Dict[DocKey, List[LineAnnotation]], bool]:
    """Annotate every line of the given (source, id) documents (default:
    every document with coverage records) with its coverage status.
    Returns ({(source, id): [LineAnnotation, ...]}, any_uncovered).
    """
    coverage = load_coverage(coverage_path)
    keys = (
        list(doc_keys) if doc_keys is not None
        else sorted(coverage.keys(), key=lambda k: (k[0], str(k[1])))
    )

    by_doc: Dict[DocKey, List[LineAnnotation]] = {}
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

        annotations: List[LineAnnotation] = []
        for si, section in enumerate(doc.sections):
            annotations.extend(
                _annotate_section(doc.path, section, by_section.get(si, []), mode)
            )

        by_doc[(source_name, id_value)] = annotations
        if any(a.status == "gap" for a in annotations):
            any_uncovered = True

    return by_doc, any_uncovered
