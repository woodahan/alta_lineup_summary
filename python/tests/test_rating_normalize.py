from alta_tool.rating_normalize import normalize_rating


def test_normalize_rating_parses_numeric_values() -> None:
    assert normalize_rating("4.0") == 4.0
    assert normalize_rating("NTRP 3.5C") == 3.5
    assert normalize_rating("2.5 singles") == 2.5
    assert normalize_rating("3.75") == 3.75
    assert normalize_rating("3.5-") == 3.25
    assert normalize_rating("rated 4.0- doubles") == 3.75


def test_normalize_rating_rejects_invalid_values() -> None:
    assert normalize_rating("") is None
    assert normalize_rating("unrated") is None
    assert normalize_rating("9.5") is None
