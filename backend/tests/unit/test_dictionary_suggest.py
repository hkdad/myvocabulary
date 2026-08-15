from app.services.dictionary_service import levenshtein, max_edit_distance


def test_levenshtein_identical() -> None:
    assert levenshtein("elephant", "elephant") == 0


def test_levenshtein_typo() -> None:
    assert levenshtein("elefant", "elephant") == 2
    assert levenshtein("helo", "hello") == 1


def test_max_edit_distance_scales_with_length() -> None:
    assert max_edit_distance("cat") == 1
    assert max_edit_distance("elephant") == 3
    assert max_edit_distance("medium") == 2
