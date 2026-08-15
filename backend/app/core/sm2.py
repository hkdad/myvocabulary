"""SM-2 spaced repetition algorithm."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

MIN_EASE_FACTOR = 1.3
DEFAULT_EASE_FACTOR = 2.5


@dataclass(frozen=True)
class SrsState:
    ease_factor: float
    interval_days: int
    repetitions: int
    state: str


@dataclass(frozen=True)
class SrsUpdate:
    ease_factor: float
    interval_days: int
    repetitions: int
    state: str
    due_at: datetime


def compute_ease_factor(current_ef: float, quality: int) -> float:
    """Update ease factor from SM-2 quality rating (0–5)."""
    q = max(0, min(5, quality))
    delta = 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
    return max(MIN_EASE_FACTOR, current_ef + delta)


def apply_review(state: SrsState, quality: int, *, now: datetime | None = None) -> SrsUpdate:
    """Apply one review and return updated scheduling fields."""
    if now is None:
        now = datetime.now(UTC)

    q = max(0, min(5, quality))
    new_ef = compute_ease_factor(state.ease_factor, q)

    if q < 3:
        return SrsUpdate(
            ease_factor=new_ef,
            interval_days=1,
            repetitions=0,
            state="relearning",
            due_at=now + timedelta(days=1),
        )

    new_reps = state.repetitions + 1
    if new_reps == 1:
        new_interval = 1
        new_state = "learning"
    elif new_reps == 2:
        new_interval = 6
        new_state = "review"
    else:
        base_interval = state.interval_days if state.interval_days > 0 else 6
        new_interval = max(1, round(base_interval * new_ef))
        new_state = "review"

    return SrsUpdate(
        ease_factor=new_ef,
        interval_days=new_interval,
        repetitions=new_reps,
        state=new_state,
        due_at=now + timedelta(days=new_interval),
    )
