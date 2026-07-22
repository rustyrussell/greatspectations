import glob
import os
import tomllib
from dataclasses import dataclass, field, replace
from typing import Dict, Optional, Union

IdType = Union[int, str]


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Source:
    """A single configured spec source (one [sources.NAME] table)."""

    name: str
    format: str
    comment_marker: str
    dir: Optional[str] = None
    file: Optional[str] = None
    pattern: Optional[str] = None

    @property
    def needs_id(self) -> bool:
        return self.dir is not None

    def resolve(self, id: Optional[IdType] = None) -> str:
        """Return the filesystem path to the document for this source."""
        if self.file is not None:
            if id is not None:
                raise ConfigError(
                    "source '{}' is a single-file source and takes no id "
                    "(got {!r})".format(self.name, id)
                )
            return self.file

        assert self.dir is not None and self.pattern is not None
        if id is None:
            raise ConfigError(
                "source '{}' requires an id (pattern {!r})".format(
                    self.name, self.pattern
                )
            )
        try:
            glob_pattern = self.pattern.format(id=id)
        except (ValueError, KeyError) as e:
            raise ConfigError(
                "source '{}': cannot format pattern {!r} with id={!r}: {}".format(
                    self.name, self.pattern, id, e
                )
            ) from e

        matches = sorted(glob.glob(os.path.join(self.dir, glob_pattern)))
        if len(matches) == 0:
            raise ConfigError(
                "source '{}': no file matching {!r} in {!r}".format(
                    self.name, glob_pattern, self.dir
                )
            )
        if len(matches) > 1:
            raise ConfigError(
                "source '{}': multiple files matching {!r} in {!r}: {}".format(
                    self.name, glob_pattern, self.dir, matches
                )
            )
        return matches[0]


@dataclass(frozen=True)
class Config:
    sources: Dict[str, Source] = field(default_factory=dict)
    base_dir: str = "."

    def __getitem__(self, name: str) -> Source:
        try:
            return self.sources[name]
        except KeyError:
            raise ConfigError(
                "no such source '{}' (known: {})".format(
                    name, ", ".join(sorted(self.sources)) or "<none>"
                )
            ) from None

    def __contains__(self, name: str) -> bool:
        return name in self.sources


def _build_source(name: str, table: Dict) -> Source:
    if "format" not in table:
        raise ConfigError("source '{}' is missing required 'format'".format(name))
    format_name = table["format"]

    has_dir = "dir" in table
    has_file = "file" in table
    if has_dir == has_file:
        raise ConfigError(
            "source '{}' must set exactly one of 'dir' or 'file'".format(name)
        )

    comment_marker = table.get("comment_marker", name.upper())

    if has_dir:
        if "pattern" not in table:
            raise ConfigError(
                "source '{}' sets 'dir' but is missing required 'pattern'".format(
                    name
                )
            )
        pattern = table["pattern"]
        if "{id" not in pattern:
            raise ConfigError(
                "source '{}' pattern {!r} must contain an '{{id}}' "
                "placeholder".format(name, pattern)
            )
        return Source(
            name=name,
            format=format_name,
            comment_marker=comment_marker,
            dir=table["dir"],
            pattern=pattern,
        )

    if "pattern" in table:
        raise ConfigError(
            "source '{}' sets 'file' so must not also set 'pattern'".format(name)
        )
    return Source(
        name=name,
        format=format_name,
        comment_marker=comment_marker,
        file=table["file"],
    )


def load(path: str) -> Config:
    """Load a specquotes.toml file into a Config.

    Relative 'dir'/'file' entries are resolved against the directory
    containing the config file (not the current working directory).
    """
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError("config file not found: {}".format(path)) from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError("{}: {}".format(path, e)) from e

    sources_table = data.get("sources", {})
    if not isinstance(sources_table, dict):
        raise ConfigError("{}: 'sources' must be a table".format(path))

    base_dir = os.path.dirname(os.path.abspath(path))
    sources: Dict[str, Source] = {}
    markers: Dict[str, str] = {}
    for name, table in sources_table.items():
        if not isinstance(table, dict):
            raise ConfigError("{}: source '{}' must be a table".format(path, name))
        source = _build_source(name, table)

        if source.dir is not None and not os.path.isabs(source.dir):
            source = replace(source, dir=os.path.join(base_dir, source.dir))
        if source.file is not None and not os.path.isabs(source.file):
            source = replace(source, file=os.path.join(base_dir, source.file))

        if source.comment_marker in markers:
            raise ConfigError(
                "{}: sources '{}' and '{}' both use comment_marker "
                "'{}'".format(
                    path, markers[source.comment_marker], name, source.comment_marker
                )
            )
        markers[source.comment_marker] = name
        sources[name] = source

    return Config(sources=sources, base_dir=base_dir)
