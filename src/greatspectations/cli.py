import argparse
import json
import os
import sys
from typing import List, Optional, Sequence, Tuple

from greatspectations import __version__
from greatspectations.config import Config, ConfigError, IdType
from greatspectations.config import load as load_config
from greatspectations.coverage import CoverageError, build_annotations
from greatspectations.coverage import write_coverage as append_coverage
from greatspectations.matching import MatchingError, check_quotes
from greatspectations.quotes import QuoteSyntaxError, gather_quotes, iter_lines
from greatspectations.report import html_filename, render_html, render_json, render_text


def _load_config_or_die(path: str) -> Config:
    try:
        return load_config(path)
    except ConfigError as e:
        print("error: {}".format(e), file=sys.stderr)
        sys.exit(1)


def _parse_source_spec(spec: str) -> Tuple[str, Optional[IdType]]:
    """Parse a --source argument: 'NAME' or 'NAME:ID'."""
    name, sep, raw_id = spec.partition(":")
    if not sep:
        return name, None
    try:
        return name, int(raw_id)
    except ValueError:
        return name, raw_id


def cmd_check(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)

    try:
        quotes = gather_quotes(
            config,
            iter_lines(args.files),
            comment_start=args.comment_start,
            comment_continue=args.comment_continue,
            comment_end=args.comment_end,
            comment_aside=args.comment_aside,
            include_commit=args.include_commit,
        )
    except QuoteSyntaxError as e:
        print(str(e), file=sys.stderr)
        return 1
    except OSError as e:
        print("error: {}".format(e), file=sys.stderr)
        return 1

    try:
        results = check_quotes(config, quotes, mode=args.mode)
    except MatchingError as e:
        print("error: {}".format(e), file=sys.stderr)
        return 1

    if args.coverage:
        append_coverage(args.coverage, results)

    failed = [r for r in results if not r.ok]

    if args.format == "json":
        payload = {
            "results": [
                {
                    "file": r.quote.filename,
                    "line": r.quote.line,
                    "source": r.quote.source,
                    "id": r.quote.id,
                    "ok": r.ok,
                    "error": r.error,
                    "suggestion": (
                        {
                            "file": r.suggestion.file, "line": r.suggestion.line,
                            "ratio": r.suggestion.ratio, "snippet": r.suggestion.snippet,
                        }
                        if r.suggestion else None
                    ),
                }
                for r in results
            ],
            "summary": {"total": len(results), "failed": len(failed)},
        }
        print(json.dumps(payload, indent=2))
    else:
        for r in results:
            if not r.ok:
                print(
                    "{}:{}:{}".format(r.quote.filename, r.quote.line, r.error),
                    file=sys.stderr,
                )
                if r.suggestion is not None:
                    print(
                        "{}:{}: note: closest match ({:.0%}): {!r}".format(
                            r.suggestion.file, r.suggestion.line,
                            r.suggestion.ratio, r.suggestion.snippet,
                        ),
                        file=sys.stderr,
                    )
                if not args.keep_going:
                    break
            elif args.verbose:
                print(
                    "{}:{}:Matched {!r}".format(
                        r.quote.filename, r.quote.line, r.quote.text
                    )
                )

    return 1 if failed else 0


def cmd_coverage(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)

    doc_keys: Optional[List[Tuple[str, Optional[IdType]]]] = None
    if args.source:
        doc_keys = [_parse_source_spec(s) for s in args.source]

    try:
        by_doc, any_uncovered = build_annotations(
            config, args.coverage, doc_keys=doc_keys, mode=args.mode,
        )
    except CoverageError as e:
        print("error: {}".format(e), file=sys.stderr)
        return 1

    if args.format == "html":
        if not args.output_dir:
            print("error: --format html requires --output-dir", file=sys.stderr)
            return 1
        os.makedirs(args.output_dir, exist_ok=True)
        for doc_key, annotations in by_doc.items():
            path = annotations[0].file if annotations else ""
            page = render_html(doc_key, path, annotations)
            out_path = os.path.join(args.output_dir, html_filename(*doc_key))
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(page)
    elif args.format == "json":
        print(json.dumps(render_json(by_doc, any_uncovered), indent=2))
    else:
        for line in render_text(by_doc):
            print(line)

    return 1 if any_uncovered else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="greatspectate",
        description="Check that spec quotes in source comments match the spec",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    check_parser = subparsers.add_parser(
        "check", help="Check quotes in source files against their spec sources"
    )
    check_parser.add_argument(
        "--config", default="specquotes.toml",
        help="Path to specquotes.toml (default: %(default)s)",
    )
    check_parser.add_argument("-v", "--verbose", action="store_true")
    check_parser.add_argument(
        "-k", "--keep-going", action="store_true",
        help="Report all errors instead of stopping at the first",
    )
    check_parser.add_argument(
        "--mode", choices=("normalized", "exact"), default="normalized",
        help="Matching mode (default: %(default)s)",
    )
    check_parser.add_argument(
        "--coverage", metavar="FILE", help="Append coverage records to FILE"
    )
    check_parser.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="Output format (default: %(default)s)",
    )
    check_parser.add_argument(
        "--comment-start", default="# ",
        help='marker prefix, e.g. "# " (default) or "/* " for C',
    )
    check_parser.add_argument(
        "--comment-continue", default="#",
        help='continuation-line prefix (default: "#")',
    )
    check_parser.add_argument(
        "--comment-end",
        help='marker for end of an inline comment, e.g. "*/" for C',
    )
    check_parser.add_argument(
        "--comment-aside",
        help="lines starting with this prefix are dropped from the quote "
        'instead of appended, e.g. "# Note:" for commentary inside a '
        "quote block",
    )
    check_parser.add_argument(
        "--include-commit", action="append", default=[],
        help="Also parse '-<commit>' draft marker lines with this commit "
        "prefix (may be repeated)",
    )
    check_parser.add_argument(
        "files", nargs="*", help="Files to read (default: stdin)"
    )
    check_parser.set_defaults(func=cmd_check)

    coverage_parser = subparsers.add_parser(
        "coverage", help="Report spec text not quoted by any source comment"
    )
    coverage_parser.add_argument(
        "--config", default="specquotes.toml",
        help="Path to specquotes.toml (default: %(default)s)",
    )
    coverage_parser.add_argument(
        "--coverage", required=True, metavar="FILE",
        help="Coverage file produced by 'greatspectate check --coverage=FILE'",
    )
    coverage_parser.add_argument(
        "--source", action="append", metavar="NAME[:ID]",
        help="Restrict to this source (may be repeated; default: every "
        "source/id found in the coverage file)",
    )
    coverage_parser.add_argument(
        "--mode", choices=("normalized", "exact"), default="normalized",
        help="Must match the mode used when the coverage file was written "
        "(default: %(default)s)",
    )
    coverage_parser.add_argument(
        "--format", choices=("text", "json", "html"), default="text",
        help="Output format (default: %(default)s)",
    )
    coverage_parser.add_argument(
        "--output-dir", metavar="DIR",
        help="Directory to write one HTML file per document into "
        "(required, and only used, with --format html)",
    )
    coverage_parser.set_defaults(func=cmd_coverage)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
