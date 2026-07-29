import pytest

from greatspectations.normative import NormativeSpan, PlaceSyntaxError, parse_place


def test_whole_line():
    assert parse_place("42") == NormativeSpan(42, None, 42, None)


def test_same_line_column_range():
    assert parse_place("42:10-20") == NormativeSpan(42, 10, 42, 20)


def test_same_line_open_start_column():
    assert parse_place("42:-20") == NormativeSpan(42, None, 42, 20)


def test_same_line_open_end_column():
    assert parse_place("42:10-") == NormativeSpan(42, 10, 42, None)


def test_line_range():
    assert parse_place("42-50") == NormativeSpan(42, None, 50, None)


def test_open_start_line():
    assert parse_place("-50") == NormativeSpan(None, None, 50, None)


def test_open_start_line_with_column():
    assert parse_place("-50:20") == NormativeSpan(None, None, 50, 20)


def test_open_end_line():
    assert parse_place("42-") == NormativeSpan(42, None, None, None)


def test_open_end_line_with_column():
    assert parse_place("42:10-") == NormativeSpan(42, 10, 42, None)
    # (this one really is same-line -- see the module docstring on why
    # 'N:C-' can't mean "column C of line N to end of file")


def test_cross_line_precise_span():
    assert parse_place("42:10-50:20") == NormativeSpan(42, 10, 50, 20)


def test_cross_line_bare_endpoint():
    assert parse_place("42-50:5") == NormativeSpan(42, None, 50, 5)


def test_place_with_column_and_trailing_number_is_same_line_not_cross_line():
    # "42:5-50" is ambiguous: same-line columns 5-50, or line 42 col 5
    # through line 50? The standalone-place form wins (same precedence
    # as the 'N:C-' case in the module docstring) since it's tried
    # first and matches the whole string.
    assert parse_place("42:5-50") == NormativeSpan(42, 5, 42, 50)


def test_whitespace_stripped():
    assert parse_place("  42-50  ") == NormativeSpan(42, None, 50, None)


@pytest.mark.parametrize("spec", [
    "",
    "abc",
    "0",
    "42:0-10",
    "42:10-0",
    "-",
    "42-50-60",
    "42:1-2:3-4",
])
def test_invalid_specs_raise(spec):
    with pytest.raises(PlaceSyntaxError):
        parse_place(spec)


def test_end_before_start_same_line_raises():
    with pytest.raises(PlaceSyntaxError, match="end column before start"):
        parse_place("42:20-10")


def test_end_before_start_range_raises():
    with pytest.raises(PlaceSyntaxError, match="end before start"):
        parse_place("50-42")


def test_end_before_start_range_with_columns_raises():
    with pytest.raises(PlaceSyntaxError, match="end before start"):
        parse_place("42:20-42:10")
