from dataclasses import dataclass
from typing import Callable, Dict, List


@dataclass(frozen=True)
class Section:
    """One section of a spec document (header text plus its body).

    text is the section's content with all runs of whitespace collapsed
    to a single space (so quote matching can ignore line wrapping);
    linemap[i] is the original source line number for text[i].
    header is the raw (uncollapsed, stripped) header line, or "" for a
    document's preamble before its first header.
    """

    header: str
    text: str
    linemap: List[int]


@dataclass(frozen=True)
class Document:
    path: str
    sections: List[Section]


Loader = Callable[[str], Document]

_REGISTRY: Dict[str, Loader] = {}


def register(name: str, loader: Loader) -> None:
    _REGISTRY[name] = loader


def load(format_name: str, path: str) -> Document:
    try:
        loader = _REGISTRY[format_name]
    except KeyError:
        raise ValueError(
            "unknown format {!r} (known: {})".format(
                format_name, ", ".join(sorted(_REGISTRY)) or "<none>"
            )
        ) from None
    return loader(path)


# Importing submodules registers their loaders.
from greatspectations.formats import markdown  # noqa: E402,F401
from greatspectations.formats import mediawiki  # noqa: E402,F401
