import pytest

from greatspectations.config import Config, Source
from greatspectations.quotes import QuoteSyntaxError, gather_quotes, iter_lines


def make_config(sources) -> Config:
    return Config(sources={s.name: s for s in sources})


def bolt_source(**overrides) -> Source:
    defaults = dict(
        name="bolt", format="markdown", comment_marker="BOLT",
        dir="/unused", pattern="{id:02d}-*.md",
    )
    defaults.update(overrides)
    return Source(**defaults)


def bip_source(**overrides) -> Source:
    defaults = dict(
        name="bip", format="mediawiki", comment_marker="BIP",
        dir="/unused", pattern="bip-{id:04d}.mediawiki",
    )
    defaults.update(overrides)
    return Source(**defaults)


def cmdata_source(**overrides) -> Source:
    defaults = dict(
        name="cmdata-spec", format="markdown", comment_marker="CMDATA-SPEC",
        file="/unused/SPECIFICATION.md",
    )
    defaults.update(overrides)
    return Source(**defaults)


def lines_from(text: str, filename: str = "test.c"):
    return [(filename, i, line + "\n") for i, line in enumerate(text.splitlines(), 1)]


def test_simple_bolt_quote():
    config = make_config([bolt_source()])
    text = "# BOLT #11: some text"
    quotes = gather_quotes(config, lines_from(text))
    assert len(quotes) == 1
    q = quotes[0]
    assert q.source == "bolt"
    assert q.id == 11
    assert q.section_hint is None
    assert q.text == "some text"
    assert q.line == 1


def test_continuation_lines_collapse_whitespace():
    config = make_config([bolt_source()])
    text = "\n".join([
        "# BOLT #11: A writer:",
        "#  - MUST set `payment_hash` to the SHA256",
        "#    of `payment_preimage`.",
        "int x = 1;",
    ])
    quotes = gather_quotes(config, lines_from(text))
    assert len(quotes) == 1
    assert quotes[0].text == (
        "A writer: - MUST set `payment_hash` to the SHA256 "
        "of `payment_preimage`."
    )


def test_two_quotes_same_source():
    config = make_config([bolt_source()])
    text = "\n".join([
        "# BOLT #11: first quote",
        "# BOLT #2: second quote",
    ])
    quotes = gather_quotes(config, lines_from(text))
    assert [q.id for q in quotes] == [11, 2]
    assert [q.text for q in quotes] == ["first quote", "second quote"]


def test_mixed_sources_in_one_file():
    config = make_config([bolt_source(), bip_source()])
    text = "\n".join([
        "# BOLT #11: bolt text",
        "# BIP #340: bip text",
    ])
    quotes = gather_quotes(config, lines_from(text))
    assert [(q.source, q.id) for q in quotes] == [("bolt", 11), ("bip", 340)]


def test_single_file_source_no_id():
    config = make_config([cmdata_source()])
    text = "# CMDATA-SPEC: A reader MUST fail parsing"
    quotes = gather_quotes(config, lines_from(text))
    assert len(quotes) == 1
    assert quotes[0].source == "cmdata-spec"
    assert quotes[0].id is None
    assert quotes[0].text == "A reader MUST fail parsing"


def test_single_file_source_rejects_id():
    config = make_config([cmdata_source()])
    text = "# CMDATA-SPEC #3: bogus"
    with pytest.raises(QuoteSyntaxError, match="takes no id"):
        gather_quotes(config, lines_from(text))


def test_dir_source_requires_id():
    config = make_config([bolt_source()])
    text = "# BOLT: missing id"
    with pytest.raises(QuoteSyntaxError, match="expected '#<id>'"):
        gather_quotes(config, lines_from(text))


def test_missing_colon_raises():
    config = make_config([bolt_source()])
    text = "# BOLT #11 no colon here"
    with pytest.raises(QuoteSyntaxError, match="expected ':'"):
        gather_quotes(config, lines_from(text))


def test_section_hint_parsed():
    config = make_config([bolt_source()])
    text = "# BOLT #11/Reader Requirements: quoted text"
    quotes = gather_quotes(config, lines_from(text))
    assert quotes[0].id == 11
    assert quotes[0].section_hint == "Reader Requirements"
    assert quotes[0].text == "quoted text"


def test_section_hint_on_single_file_source():
    config = make_config([cmdata_source()])
    text = "# CMDATA-SPEC/Writer Requirements: quoted text"
    quotes = gather_quotes(config, lines_from(text))
    assert quotes[0].section_hint == "Writer Requirements"
    assert quotes[0].text == "quoted text"


def test_plain_comment_is_ignored():
    config = make_config([bolt_source()])
    text = "# just a normal comment, not a marker"
    quotes = gather_quotes(config, lines_from(text))
    assert quotes == []


def test_marker_prefix_does_not_shadow_longer_word():
    # "BOLTX" should not be treated as source "bolt"'s marker "BOLT".
    config = make_config([bolt_source()])
    text = "# BOLTX #11: not a bolt marker"
    quotes = gather_quotes(config, lines_from(text))
    assert quotes == []


def test_draft_commit_included():
    config = make_config([bolt_source()])
    text = "# BOLT-abc123def #11: draft text"
    quotes = gather_quotes(
        config, lines_from(text), include_commit=["abc123"]
    )
    assert len(quotes) == 1
    assert quotes[0].id == 11
    assert quotes[0].text == "draft text"


def test_draft_commit_excluded():
    config = make_config([bolt_source()])
    text = "# BOLT-abc123def #11: draft text"
    quotes = gather_quotes(config, lines_from(text), include_commit=["other"])
    assert quotes == []


def test_c_style_inline_comment():
    config = make_config([bolt_source()])
    text = "/* BOLT #11: short text */"
    quotes = gather_quotes(
        config, lines_from(text),
        comment_start="/* ", comment_continue="*", comment_end="*/",
    )
    assert len(quotes) == 1
    assert quotes[0].text == "short text"


def test_c_style_block_comment():
    config = make_config([bolt_source()])
    text = "\n".join([
        "/* BOLT #11: A writer:",
        " * - MUST set foo.",
        " */",
    ])
    quotes = gather_quotes(
        config, lines_from(text),
        comment_start="/* ", comment_continue="*", comment_end="*/",
    )
    assert len(quotes) == 1
    assert quotes[0].text == "A writer: - MUST set foo."


def test_comment_aside_dropped_from_quote():
    config = make_config([bolt_source()])
    text = "\n".join([
        "# BOLT #11: A writer:",
        "#  - MUST set `payment_hash`.",
        "# Note: We did not implement this yet.",
        "#  - MUST set `payment_secret`.",
    ])
    quotes = gather_quotes(
        config, lines_from(text), comment_aside="# Note:",
    )
    assert len(quotes) == 1
    assert quotes[0].text == (
        "A writer: - MUST set `payment_hash`. - MUST set `payment_secret`."
    )


def test_comment_aside_without_flag_is_appended_normally():
    config = make_config([bolt_source()])
    text = "\n".join([
        "# BOLT #11: A writer:",
        "# Note: We did not implement this yet.",
    ])
    quotes = gather_quotes(config, lines_from(text))
    assert quotes[0].text == "A writer: Note: We did not implement this yet."


def test_comment_aside_closing_inline_comment_still_flushes():
    config = make_config([bolt_source()])
    text = "\n".join([
        "/* BOLT #2: A sending node:",
        " *  - MUST set foo.",
        " * Note: not implemented yet. */",
        "int x = 1;",
    ])
    quotes = gather_quotes(
        config, lines_from(text),
        comment_start="/* ", comment_continue="*", comment_end="*/",
        comment_aside="* Note:",
    )
    assert len(quotes) == 1
    assert quotes[0].text == "A sending node: - MUST set foo."


def test_iter_lines_reads_files(tmp_path):
    f1 = tmp_path / "a.c"
    f1.write_text("line one\nline two\n")
    result = list(iter_lines([str(f1)]))
    assert result == [
        (str(f1), 1, "line one\n"),
        (str(f1), 2, "line two\n"),
    ]
