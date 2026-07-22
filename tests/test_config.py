import pytest

from greatspectations.config import ConfigError, load


VALID_TOML = """
[sources.bolt]
format = "markdown"
dir = "lightning-rfc"
pattern = "{id:02d}-*.md"

[sources.cmdata-spec]
format = "markdown"
file = "SPECIFICATION.md"

[sources.bip]
format = "mediawiki"
dir = "bips"
pattern = "bip-{id:04d}.mediawiki"
comment_marker = "BIP"
"""


def write_config(tmp_path, text):
    path = tmp_path / "specquotes.toml"
    path.write_text(text)
    return str(path)


def test_load_valid_config(tmp_path):
    path = write_config(tmp_path, VALID_TOML)
    config = load(path)

    bolt = config["bolt"]
    assert bolt.format == "markdown"
    assert bolt.comment_marker == "BOLT"  # default: name.upper()
    assert bolt.needs_id is True
    assert bolt.dir == str(tmp_path / "lightning-rfc")

    spec = config["cmdata-spec"]
    assert spec.comment_marker == "CMDATA-SPEC"
    assert spec.needs_id is False
    assert spec.file == str(tmp_path / "SPECIFICATION.md")

    bip = config["bip"]
    assert bip.comment_marker == "BIP"  # explicit override


def test_missing_source_raises(tmp_path):
    path = write_config(tmp_path, VALID_TOML)
    config = load(path)
    with pytest.raises(ConfigError, match="no such source"):
        config["nonexistent"]


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load(str(tmp_path / "does-not-exist.toml"))


def test_malformed_toml(tmp_path):
    path = write_config(tmp_path, "this is not [valid toml")
    with pytest.raises(ConfigError):
        load(path)


def test_dir_and_file_both_set(tmp_path):
    path = write_config(
        tmp_path,
        """
        [sources.bad]
        format = "markdown"
        dir = "somedir"
        file = "somefile.md"
        pattern = "{id}-*.md"
        """,
    )
    with pytest.raises(ConfigError, match="exactly one of 'dir' or 'file'"):
        load(path)


def test_dir_and_file_neither_set(tmp_path):
    path = write_config(
        tmp_path,
        """
        [sources.bad]
        format = "markdown"
        """,
    )
    with pytest.raises(ConfigError, match="exactly one of 'dir' or 'file'"):
        load(path)


def test_dir_without_pattern(tmp_path):
    path = write_config(
        tmp_path,
        """
        [sources.bad]
        format = "markdown"
        dir = "somedir"
        """,
    )
    with pytest.raises(ConfigError, match="missing required 'pattern'"):
        load(path)


def test_file_with_pattern(tmp_path):
    path = write_config(
        tmp_path,
        """
        [sources.bad]
        format = "markdown"
        file = "somefile.md"
        pattern = "{id}-*.md"
        """,
    )
    with pytest.raises(ConfigError, match="must not also set 'pattern'"):
        load(path)


def test_pattern_without_id_placeholder(tmp_path):
    path = write_config(
        tmp_path,
        """
        [sources.bad]
        format = "markdown"
        dir = "somedir"
        pattern = "*.md"
        """,
    )
    with pytest.raises(ConfigError, match="must contain an '{id}' placeholder"):
        load(path)


def test_duplicate_comment_marker(tmp_path):
    path = write_config(
        tmp_path,
        """
        [sources.foo]
        format = "markdown"
        file = "foo.md"
        comment_marker = "SPEC"

        [sources.bar]
        format = "markdown"
        file = "bar.md"
        comment_marker = "SPEC"
        """,
    )
    with pytest.raises(ConfigError, match="both use comment_marker"):
        load(path)


def test_resolve_single_file_source(tmp_path):
    spec_file = tmp_path / "SPECIFICATION.md"
    spec_file.write_text("# Spec\n")
    path = write_config(
        tmp_path,
        """
        [sources.cmdata-spec]
        format = "markdown"
        file = "SPECIFICATION.md"
        """,
    )
    config = load(path)
    assert config["cmdata-spec"].resolve() == str(spec_file)


def test_resolve_single_file_source_rejects_id(tmp_path):
    (tmp_path / "SPECIFICATION.md").write_text("# Spec\n")
    path = write_config(
        tmp_path,
        """
        [sources.cmdata-spec]
        format = "markdown"
        file = "SPECIFICATION.md"
        """,
    )
    config = load(path)
    with pytest.raises(ConfigError, match="takes no id"):
        config["cmdata-spec"].resolve(11)


def test_resolve_dir_source_by_id(tmp_path):
    boltdir = tmp_path / "lightning-rfc"
    boltdir.mkdir()
    (boltdir / "11-payment-encoding.md").write_text("# Payment\n")
    (boltdir / "02-peer-protocol.md").write_text("# Peer\n")
    path = write_config(
        tmp_path,
        """
        [sources.bolt]
        format = "markdown"
        dir = "lightning-rfc"
        pattern = "{id:02d}-*.md"
        """,
    )
    config = load(path)
    assert config["bolt"].resolve(11) == str(boltdir / "11-payment-encoding.md")
    assert config["bolt"].resolve(2) == str(boltdir / "02-peer-protocol.md")


def test_resolve_dir_source_recursive_pattern(tmp_path):
    # Mirrors doc-rfc-std's layout: RFCs split across category
    # subdirectories under one top-level dir.
    rfcdir = tmp_path / "RFC"
    (rfcdir / "standard").mkdir(parents=True)
    (rfcdir / "draft-standard").mkdir(parents=True)
    (rfcdir / "standard" / "rfc1002.txt.gz").write_text("standard")
    (rfcdir / "draft-standard" / "rfc5322.txt.gz").write_text("draft")

    path = write_config(
        tmp_path,
        """
        [sources.rfc]
        format = "markdown"
        dir = "RFC"
        pattern = "**/rfc{id}.txt.gz"
        """,
    )
    config = load(path)
    assert config["rfc"].resolve(1002) == str(rfcdir / "standard" / "rfc1002.txt.gz")
    assert config["rfc"].resolve(5322) == str(
        rfcdir / "draft-standard" / "rfc5322.txt.gz"
    )


def test_resolve_dir_source_requires_id(tmp_path):
    boltdir = tmp_path / "lightning-rfc"
    boltdir.mkdir()
    path = write_config(
        tmp_path,
        """
        [sources.bolt]
        format = "markdown"
        dir = "lightning-rfc"
        pattern = "{id:02d}-*.md"
        """,
    )
    config = load(path)
    with pytest.raises(ConfigError, match="requires an id"):
        config["bolt"].resolve()


def test_resolve_dir_source_no_match(tmp_path):
    boltdir = tmp_path / "lightning-rfc"
    boltdir.mkdir()
    path = write_config(
        tmp_path,
        """
        [sources.bolt]
        format = "markdown"
        dir = "lightning-rfc"
        pattern = "{id:02d}-*.md"
        """,
    )
    config = load(path)
    with pytest.raises(ConfigError, match="no file matching"):
        config["bolt"].resolve(99)


def test_resolve_dir_source_multiple_matches(tmp_path):
    boltdir = tmp_path / "lightning-rfc"
    boltdir.mkdir()
    (boltdir / "11-a.md").write_text("a")
    (boltdir / "11-b.md").write_text("b")
    path = write_config(
        tmp_path,
        """
        [sources.bolt]
        format = "markdown"
        dir = "lightning-rfc"
        pattern = "{id:02d}-*.md"
        """,
    )
    config = load(path)
    with pytest.raises(ConfigError, match="multiple files matching"):
        config["bolt"].resolve(11)
