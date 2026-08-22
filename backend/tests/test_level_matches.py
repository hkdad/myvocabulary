import pytest

from app.services.loop_engine import (
    filter_study_ids_by_level,
    level_matches,
    level_matches_at_or_above,
    level_matches_at_or_below,
)


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
    assert level_matches_at_or_below(item_level, learner_level) is expected


@pytest.mark.parametrize(
    ("item_level", "learner_level", "expected"),
    [
        ("A1", "A1", True),
        ("A2", "A1", True),
        ("B1", "A2", True),
        ("A1", "A2", False),
        ("Pre-A1", "A1", False),
        ("a2", "A2", True),
        ("Grade 3", "Grade 3", True),
        ("Grade 4", "Grade 3", False),
        ("Book 1", "A1", False),
        (None, "A1", False),
        ("", "A1", False),
    ],
)
def test_level_matches_at_or_above(item_level: str | None, learner_level: str, expected: bool) -> None:
    assert level_matches_at_or_above(item_level, learner_level) is expected


def test_filter_study_ids_by_level_at_or_above_keeps_unbanked() -> None:
    entry_ids = {1, 2, 3, 4}
    level_map = {1: "A1", 2: "A2", 3: "B1", 4: None}
    kept = filter_study_ids_by_level(entry_ids, level_map, "A2", mode="at_or_above")
    assert kept == {2, 3, 4}


def test_filter_study_ids_by_level_exact() -> None:
    entry_ids = {1, 2, 3, 4}
    level_map = {1: "A1", 2: "A2", 3: "B1", 4: None}
    kept = filter_study_ids_by_level(entry_ids, level_map, "A2", mode="exact")
    assert kept == {2, 4}
