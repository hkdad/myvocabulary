from app.core.dictation_scoring import split_syllables


def test_split_syllables_environment() -> None:
    parts = split_syllables("environment")
    assert parts == ["en", "vi", "ron", "ment"]


def test_split_syllables_short_word() -> None:
    assert split_syllables("cat") == ["cat"]
