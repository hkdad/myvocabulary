import pytest

from app.services.word_bank_service import (
    _normalize_categories,
    _normalize_level,
    _resolve_column_map,
    format_category_name,
    parse_categories,
)


def test_parse_categories_splits_on_separators() -> None:
    assert parse_categories("Food and Animals") == ["Food", "Animals"]
    assert parse_categories("Sports; leisure") == ["Sports", "leisure"]
    assert parse_categories("Food AND Animals") == ["Food", "Animals"]
    assert parse_categories("Health, medicine") == ["Health", "medicine"]
    assert parse_categories("Places - town") == ["Places", "town"]
    assert parse_categories("School") == ["School"]
    assert parse_categories("") == ["General"]


def test_parse_categories_keeps_hyphenated_token() -> None:
    assert parse_categories("pre-school") == ["pre-school"]


def test_normalize_level_preserves_submitted_value() -> None:
    assert _normalize_level("a1") == "a1"
    assert _normalize_level(" A2 ") == "A2"
    assert _normalize_level("Grade 3") == "Grade 3"
    assert _normalize_level("Book 1") == "Book 1"


def test_normalize_level_rejects_blank_or_too_long() -> None:
    assert _normalize_level("") is None
    assert _normalize_level("   ") is None
    assert _normalize_level("x" * 33) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Food", ["Food"]),
        ("Food and Animals", ["Food", "Animals"]),
        ("animals", ["Animals"]),
        ("the home", ["Home"]),
        ("Home and The home", ["Home"]),
        ("SPORTS", ["Sports"]),
        ("sport", ["Sports"]),
        ("communications", ["Communication"]),
        ("Health, medicine", ["Health", "Medicine"]),
        ("Places - town", ["Places", "Town"]),
        ("", ["General"]),
    ],
)
def test_normalize_categories(raw: str, expected: list[str]) -> None:
    categories, error = _normalize_categories(raw)
    assert error is None
    assert categories == expected


def test_format_category_name_capitalizes_and_strips_articles() -> None:
    assert format_category_name("animals") == "Animals"
    assert format_category_name("THE HOME") == "Home"
    assert format_category_name("a City") == "City"
    assert format_category_name("An Opinion") == "Opinion"
    assert format_category_name("  the   face ") == "Face"


def test_format_category_name_applies_aliases() -> None:
    assert format_category_name("Sport") == "Sports"
    assert format_category_name("Communications") == "Communication"


def test_normalize_categories_deduplicates_case_insensitive() -> None:
    categories, error = _normalize_categories("Food and food")
    assert error is None
    assert categories == ["Food"]


def test_normalize_categories_deduplicates_after_capitalization() -> None:
    categories, error = _normalize_categories("friends; Friends")
    assert error is None
    assert categories == ["Friends"]


def test_normalize_categories_rejects_too_long() -> None:
    categories, error = _normalize_categories("x" * 65)
    assert categories is None
    assert error is not None


def test_resolve_column_map_aliases() -> None:
    mapping = _resolve_column_map(["Vocabulary", "CEFR", "Categories", "Meaning"])
    assert mapping["word"] == "vocabulary"
    assert mapping["level"] == "cefr"
    assert mapping["category"] == "categories"
    assert mapping["definition"] == "meaning"


def test_resolve_column_map_prefers_categories_header() -> None:
    mapping = _resolve_column_map(["word", "level", "categories", "category"])
    assert mapping["category"] == "categories"
