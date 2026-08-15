from app.core.cefr import CEFR_LEVELS, next_level, previous_level


def test_cefr_levels_include_pre_a1_and_advanced() -> None:
    assert CEFR_LEVELS == ("PRE-A1", "A1", "A2", "B1", "B2", "C1", "C2")


def test_next_and_previous_level() -> None:
    assert next_level("PRE-A1") == "A1"
    assert next_level("B2") == "C1"
    assert next_level("C2") is None
    assert previous_level("A1") == "PRE-A1"
    assert previous_level("PRE-A1") is None
