"""MediaWiki format: splits a document into sections on '==Header=='
style lines, as used by the bitcoin/bips repository.
"""

import re

from greatspectations.formats import Document, register
from greatspectations.formats._common import split_on_headers

_HEADER_RE = re.compile(r"^(=+)\s*.+?\s*\1\s*$")


def _is_header(line: str) -> bool:
    return bool(_HEADER_RE.match(line.rstrip("\n")))


def load(path: str) -> Document:
    return split_on_headers(path, _is_header)


register("mediawiki", load)
