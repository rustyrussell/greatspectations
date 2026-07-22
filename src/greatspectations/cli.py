import sys
from argparse import ArgumentParser
from typing import List, Optional

from greatspectations import __version__


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="spectate",
        description="Check that spec quotes in source comments match the spec",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_subparsers(dest="command", metavar="COMMAND")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
