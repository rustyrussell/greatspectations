"""Markdown format: splits a document into sections on '#'-prefixed
header lines. Used for BOLT spec files and single-file markdown specs
(e.g. SPECIFICATION.md) alike.
"""

from greatspectations.formats import Document, register
from greatspectations.formats._common import read_lines, split_on_headers


def load(path: str) -> Document:
    return split_on_headers(path, read_lines(path), lambda line: line.startswith("#"))


register("markdown", load)
