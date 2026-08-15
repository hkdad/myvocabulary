from datetime import UTC, datetime

import pytest

from app.core.sm2 import (
    DEFAULT_EASE_FACTOR,
    MIN_EASE_FACTOR,
    SrsState,
    apply_review,
    compute_ease_factor,
)


def test_compute_ease_factor_perfect_recall() -> None:
    assert compute_ease_factor(2.5, 5) == 2.6


def test_compute_ease_factor_failed_recall() -> None:
    assert compute_ease_factor(2.5, 0) == pytest.approx(1.7)


def test_compute_ease_factor_clamps_minimum() -> None:
    assert compute_ease_factor(1.3, 0) == MIN_EASE_FACTOR


def test_first_successful_review() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    state = SrsState(
        ease_factor=DEFAULT_EASE_FACTOR,
        interval_days=0,
        repetitions=0,
        state="new",
    )
    update = apply_review(state, 4, now=now)
    assert update.repetitions == 1
    assert update.interval_days == 1
    assert update.state == "learning"
    assert update.due_at == now.replace(day=2)


def test_second_successful_review() -> None:
    now = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    state = SrsState(
        ease_factor=2.6,
        interval_days=1,
        repetitions=1,
        state="learning",
    )
    update = apply_review(state, 4, now=now)
    assert update.repetitions == 2
    assert update.interval_days == 6
    assert update.state == "review"


def test_third_successful_review_uses_ease_factor() -> None:
    now = datetime(2026, 1, 8, 12, 0, tzinfo=UTC)
    state = SrsState(
        ease_factor=2.5,
        interval_days=6,
        repetitions=2,
        state="review",
    )
    update = apply_review(state, 4, now=now)
    assert update.repetitions == 3
    assert update.interval_days == 15  # round(6 * 2.5)
    assert update.state == "review"


def test_failed_review_resets_progress() -> None:
    now = datetime(2026, 1, 8, 12, 0, tzinfo=UTC)
    state = SrsState(
        ease_factor=2.5,
        interval_days=15,
        repetitions=5,
        state="review",
    )
    update = apply_review(state, 1, now=now)
    assert update.repetitions == 0
    assert update.interval_days == 1
    assert update.state == "relearning"


def test_quality_boundary_pass() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    state = SrsState(DEFAULT_EASE_FACTOR, 0, 0, "new")
    update = apply_review(state, 3, now=now)
    assert update.repetitions == 1


def test_quality_boundary_fail() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    state = SrsState(DEFAULT_EASE_FACTOR, 6, 2, "review")
    update = apply_review(state, 2, now=now)
    assert update.state == "relearning"
    assert update.repetitions == 0
