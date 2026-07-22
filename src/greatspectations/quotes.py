"""Gather '# MARKER #id/hint: quoted text' style comments out of source
files, generalizing CLN's '# BOLT #NN: "..."' convention to any source
configured in specquotes.toml.

Marker line syntax:  <MARKER>[-<commit>][ #<id>][/<section-hint>]:
  - <MARKER> is a configured source's comment_marker (default: the
    source name, uppercased) -- e.g. 'BOLT', 'BIP', 'CMDATA-SPEC'.
  - '-<commit>' is the CLN "draft BOLT" convention: only included when
    its prefix appears in --include-commit.
  - '#<id>' is required iff the source needs one (i.e. it's a
    directory-of-files source, not a single fixed file).
  - '/<section-hint>' is optional on any source: restricts matching to
    sections whose header contains this text.
"""

import re
import sys
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

from greatspectations.config import Config, IdType

_WHITESPACE_RE = re.compile(r"\s+")


def collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text)


@dataclass(frozen=True)
class Quote:
    source: str
    id: Optional[IdType]
    section_hint: Optional[str]
    filename: str
    line: int
    text: str


class QuoteSyntaxError(Exception):
    def __init__(self, filename: str, line: int, message: str) -> None:
        super().__init__("{}:{}: {}".format(filename, line, message))
        self.filename = filename
        self.line = line
        self.message = message


_MARKER_TAIL_RE = re.compile(
    r"^(?:-(?P<commit>\S+))?"
    r"(?:\s*#(?P<id>\S+?))?"
    r"(?:/(?P<hint>[^:]+?))?"
    r"\s*:(?P<rest>.*)$"
)

_MARKER_BOUNDARY = ("", "-", " ", "/", ":")


def _parse_marker_line(
    config: Config,
    line: str,
    comment_start: str,
    include_commit: Sequence[str],
    filename: str,
    linenum: int,
) -> Optional[Tuple[str, Optional[IdType], Optional[str], str]]:
    """If line opens a quote for a configured source, return
    (source_name, id, section_hint, quote_text_so_far).

    Returns None if line isn't a marker line at all, or if it's a
    '-<commit>' draft line whose commit isn't in include_commit. Raises
    QuoteSyntaxError for a recognized marker with malformed syntax.
    """
    if not line.startswith(comment_start):
        return None
    after_start = line[len(comment_start):]

    source_name = None
    tail = None
    for marker, name in sorted(
        config.marker_map().items(), key=lambda kv: -len(kv[0])
    ):
        if after_start.startswith(marker):
            candidate_tail = after_start[len(marker):]
            if candidate_tail[:1] in _MARKER_BOUNDARY:
                source_name, tail = name, candidate_tail
                break
    if source_name is None or tail is None:
        return None

    source = config[source_name]
    m = _MARKER_TAIL_RE.match(tail)
    if not m:
        raise QuoteSyntaxError(
            filename, linenum,
            "expected ':' after {} marker".format(source.comment_marker),
        )

    commit = m.group("commit")
    if commit is not None and not any(
        commit.startswith(inc) for inc in include_commit
    ):
        return None

    raw_id = m.group("id")
    id_value: Optional[IdType]
    if source.needs_id:
        if raw_id is None:
            raise QuoteSyntaxError(
                filename, linenum,
                "expected '#<id>' after {} marker".format(source.comment_marker),
            )
        try:
            id_value = int(raw_id)
        except ValueError:
            id_value = raw_id
    else:
        if raw_id is not None:
            raise QuoteSyntaxError(
                filename, linenum,
                "{} source takes no id, but got '#{}'".format(
                    source.comment_marker, raw_id
                ),
            )
        id_value = None

    hint = m.group("hint")
    return source_name, id_value, (hint.strip() if hint else None), m.group("rest")


def gather_quotes(
    config: Config,
    lines: Iterable[Tuple[str, int, str]],
    comment_start: str = "# ",
    comment_continue: str = "#",
    comment_end: Optional[str] = None,
    include_commit: Sequence[str] = (),
) -> List[Quote]:
    """Scan (filename, linenum, raw_line) triples for marker-quotes."""
    quotes: List[Quote] = []
    cur: Optional[dict] = None

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            quotes.append(
                Quote(
                    source=cur["source"],
                    id=cur["id"],
                    section_hint=cur["hint"],
                    filename=cur["filename"],
                    line=cur["line"],
                    text=collapse_whitespace(cur["text"].strip()),
                )
            )
        cur = None

    for filename, linenum, raw_line in lines:
        line = raw_line.strip()
        parsed = _parse_marker_line(
            config, line, comment_start, include_commit, filename, linenum
        )
        if parsed is not None:
            source_name, id_value, hint, text = parsed
            flush()
            cur = {
                "source": source_name,
                "id": id_value,
                "hint": hint,
                "filename": filename,
                "line": linenum,
                "text": text,
            }
            if comment_end is not None:
                stripped = cur["text"].rstrip()
                if stripped.endswith(comment_end):
                    cur["text"] = stripped[: -len(comment_end)]
                    flush()
        elif cur is not None:
            if (
                comment_end is None or not line.startswith(comment_end)
            ) and line.startswith(comment_continue):
                if comment_end is not None and line.endswith(comment_end):
                    cur["text"] += (
                        " " + line[len(comment_continue): -len(comment_end)]
                    )
                    flush()
                else:
                    cur["text"] += " " + line[len(comment_continue):]
            else:
                flush()

    flush()
    return quotes


def iter_lines(files: Sequence[str]) -> Iterator[Tuple[str, int, str]]:
    """Yield (filename, linenum, raw_line) for each file, or stdin if
    files is empty.
    """
    if not files:
        for lineno, line in enumerate(sys.stdin, 1):
            yield "<stdin>", lineno, line
        return
    for filename in files:
        with open(filename, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                yield filename, lineno, line
