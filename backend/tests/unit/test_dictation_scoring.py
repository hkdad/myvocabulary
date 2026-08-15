from app.core.dictation_scoring import (
    generate_choices,
    hint_for_word,
    normalize_answer,
    score_answer,
)


def test_normalize_answer_strips_and_lowercases() -> None:
    assert normalize_answer("  Hello  ") == "hello"


def test_score_answer_case_insensitive() -> None:
    assert score_answer("Elephant", "elephant") is True
    assert score_answer("elephant", "Elephant") is True


def test_score_answer_mismatch() -> None:
    assert score_answer("cat", "dog") is False
    assert score_answer("cat", "catty") is False


def test_score_answer_whitespace() -> None:
    assert score_answer("hello", "  hello ") is True


def test_generate_choices_includes_correct_word() -> None:
    pool = ["apple", "banana", "cherry", "date", "elderberry"]
    choices = generate_choices("banana", pool)
    assert len(choices) == 4
    assert "banana" in choices


def test_generate_choices_unique() -> None:
    pool = ["apple", "banana", "cherry", "date"]
    choices = generate_choices("apple", pool)
    assert len(set(choice.lower() for choice in choices)) == len(choices)


def test_hint_for_word() -> None:
    assert hint_for_word("breakfast") == "Starts with: B"
