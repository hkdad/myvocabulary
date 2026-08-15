import pytest

from app.services.loop_engine import level_matches


@pytest.mark.parametrize(
    ("item_level", "learner_level", "expected"),
    [
        ("A1", "A1", True),
        ("a1", "A1", True),
        ("A2", "A1", False),
        ("B1", "B2", False),
        ("Pre-A1", "Pre-A1", True),
        ("Pre-A1", "A1", False),
        ("Grade 3", "Grade 3", True),
        ("Grade 4", "Grade 3", False),
        ("Book 1", "A1", False),
    ],
)
def test_level_matches(item_level: str, learner_level: str, expected: bool) -> None:
    assert level_matches(item_level, learner_level) is expected


@pytest.mark.parametrize(
    ("item_level", "learner_level", "expected"),
    [
        ("A1", "A1", True),
        ("B1", "B2", True),
        ("A2", "A1", False),
    ],
)
def test_level_matches_at_or_below(item_level: str, learner_level: str, expected: bool) -> None:
    from app.services.loop_engine import level_matches_at_or_below

    assert level_matches_at_or_below(item_level, learner_level) is expected
