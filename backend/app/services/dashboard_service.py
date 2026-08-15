from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.daily_challenge import DailyChallengeLog
from app.models.dictation import DictationSession
from app.models.learner import Learner
from app.models.srs import SrsCard, SrsReviewLog
from app.models.user import User
from app.models.word_list import MistakeLog, WordListAssignment
from app.services import loop_engine
from app.services.learner_profile import resolve_learner_emoji


def _accuracy_percent(correct: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round((correct / total) * 100, 1)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _distinct_days_from_reviews(reviews: list[SrsReviewLog]) -> int:
    return len({_as_utc(review.reviewed_at).date().isoformat() for review in reviews})


def _strength_for_card_as_of(reviews: list[SrsReviewLog]) -> str | None:
    """Derive strength bucket from review history up to a cutoff."""
    if not reviews:
        return None
    return loop_engine.derive_strength(distinct_review_days=_distinct_days_from_reviews(reviews))


def _strength_counts_as_of(
    released_cards: list[SrsCard],
    reviews_by_card: dict[int, list[SrsReviewLog]],
    cutoff: datetime,
) -> tuple[int, int, int]:
    learning = familiar = mastered = 0
    for card in released_cards:
        released_at = card.released_at
        if released_at is None or _as_utc(released_at) >= cutoff:
            continue
        card_reviews = [
            review
            for review in reviews_by_card.get(card.id, [])
            if _as_utc(review.reviewed_at) < cutoff
        ]
        strength = _strength_for_card_as_of(card_reviews)
        if strength == "familiar":
            familiar += 1
        elif strength == "mastered":
            mastered += 1
        elif strength == "learning":
            learning += 1
    return learning, familiar, mastered


async def _review_streak_days(db: AsyncSession, learner_id: int) -> int:
    since = datetime.now(UTC) - timedelta(days=60)
    result = await db.execute(
        select(func.date(SrsReviewLog.reviewed_at))
        .where(SrsReviewLog.learner_id == learner_id, SrsReviewLog.reviewed_at >= since)
        .group_by(func.date(SrsReviewLog.reviewed_at))
    )
    day_strings = {str(row[0]) for row in result.all()}
    streak = 0
    day = datetime.now(UTC).date()
    while day.isoformat() in day_strings:
        streak += 1
        day -= timedelta(days=1)
    return streak


async def _learner_summary(db: AsyncSession, learner: Learner) -> dict:
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since_30_days = now - timedelta(days=30)

    due_result = await db.execute(
        select(func.count(SrsCard.id)).where(
            SrsCard.learner_id == learner.id,
            SrsCard.due_at <= now,
            SrsCard.released_at.is_not(None),
        )
    )
    due_count = due_result.scalar_one()

    reviewed_result = await db.execute(
        select(func.count(SrsReviewLog.id)).where(
            SrsReviewLog.learner_id == learner.id,
            SrsReviewLog.reviewed_at >= start_of_day,
        )
    )
    reviewed_today = reviewed_result.scalar_one()

    review_stats = await db.execute(
        select(SrsReviewLog.quality).where(
            SrsReviewLog.learner_id == learner.id,
            SrsReviewLog.reviewed_at >= since_30_days,
        )
    )
    qualities = review_stats.scalars().all()
    review_total = len(qualities)
    review_correct = sum(1 for quality in qualities if quality >= 3)

    dictation_result = await db.execute(
        select(func.count(DictationSession.id)).where(
            DictationSession.learner_id == learner.id,
            DictationSession.completed_at.is_not(None),
            DictationSession.completed_at >= since_30_days,
        )
    )
    dictation_sessions = dictation_result.scalar_one()

    mistakes_result = await db.execute(
        select(func.count(func.distinct(MistakeLog.dictionary_entry_id))).where(
            MistakeLog.learner_id == learner.id,
            MistakeLog.resolved_at.is_(None),
        )
    )
    unresolved_mistakes = mistakes_result.scalar_one()

    lists_result = await db.execute(
        select(func.count(WordListAssignment.id)).where(
            WordListAssignment.learner_id == learner.id,
            WordListAssignment.is_active.is_(True),
        )
    )
    assigned_lists = lists_result.scalar_one()

    loop_progress = await loop_engine.progress_summary(db, learner_id=learner.id, now=now)

    user = learner.user
    return {
        "learner_id": learner.id,
        "display_name": learner.display_name,
        "username": user.username if user else "",
        "english_level": learner.english_level,
        "ui_mode": learner.ui_mode,
        "emoji": resolve_learner_emoji(learner.emoji, learner.display_name),
        "due_count": due_count,
        "reviewed_today": reviewed_today,
        "daily_practice_goal": loop_engine.daily_practice_goal(learner),
        "daily_new_word_goal": loop_engine.daily_new_goal(learner),
        "daily_learning_retention_goal": loop_engine.daily_learning_retention_goal(learner),
        "daily_mastered_retention_goal": loop_engine.daily_mastered_retention_goal(learner),
        "daily_retention_goal": loop_engine.daily_retention_goal(learner),
        "review_accuracy_percent": _accuracy_percent(review_correct, review_total),
        "streak_days": await _review_streak_days(db, learner.id),
        "dictation_sessions_completed": dictation_sessions,
        "unresolved_mistakes": unresolved_mistakes,
        "assigned_lists": assigned_lists,
        "learning_count": loop_progress["learning_count"],
        "familiar_count": loop_progress["familiar_count"],
        "mastered_count": loop_progress["mastered_count"],
        "new_released_today": loop_progress["new_released_today"],
        "new_remaining_today": loop_progress["new_remaining_today"],
        "daily_challenge_completed": loop_progress["daily_challenge_completed"],
        "bank_at_level": loop_progress["bank_at_level"],
        "due_overloaded": due_count > loop_engine.daily_practice_goal(learner) * 2,
    }


async def _parent_learners(db: AsyncSession, parent_id: int) -> list[Learner]:
    result = await db.execute(
        select(Learner)
        .join(User, Learner.user_id == User.id)
        .options(selectinload(Learner.user))
        .where(User.parent_id == parent_id)
        .order_by(Learner.display_name)
    )
    return list(result.scalars().all())


async def get_overview(db: AsyncSession, *, parent_id: int) -> dict:
    learners = await _parent_learners(db, parent_id)
    return {"learners": [await _learner_summary(db, learner) for learner in learners]}


async def get_learner_detail(db: AsyncSession, *, parent_id: int, learner_id: int) -> dict:
    result = await db.execute(
        select(Learner)
        .join(User, Learner.user_id == User.id)
        .options(selectinload(Learner.user))
        .where(Learner.id == learner_id, User.parent_id == parent_id)
    )
    learner = result.scalar_one_or_none()
    if learner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learner not found")

    activity = await get_activity(db, parent_id=parent_id, learner_id=learner_id, limit=10)
    return {**await _learner_summary(db, learner), "recent_activity": activity}


async def get_activity(
    db: AsyncSession, *, parent_id: int, learner_id: int, limit: int = 20
) -> list[dict]:
    result = await db.execute(
        select(Learner)
        .join(User, Learner.user_id == User.id)
        .where(Learner.id == learner_id, User.parent_id == parent_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learner not found")

    items: list[dict] = []

    reviews = await db.execute(
        select(SrsReviewLog)
        .where(SrsReviewLog.learner_id == learner_id)
        .order_by(SrsReviewLog.reviewed_at.desc())
        .limit(limit)
    )
    for review in reviews.scalars().all():
        items.append(
            {
                "type": "review",
                "description": f"Review rated {review.quality}/5",
                "occurred_at": review.reviewed_at,
            }
        )

    sessions = await db.execute(
        select(DictationSession)
        .where(
            DictationSession.learner_id == learner_id,
            DictationSession.completed_at.is_not(None),
        )
        .order_by(DictationSession.completed_at.desc())
        .limit(limit)
    )
    for session in sessions.scalars().all():
        score = 0.0
        if session.total_words > 0:
            score = round((session.correct_count / session.total_words) * 100)
        items.append(
            {
                "type": "dictation",
                "description": f"Dictation session — {score:.0f}% correct",
                "occurred_at": session.completed_at or session.started_at,
            }
        )

    items.sort(key=lambda row: row["occurred_at"], reverse=True)
    return items[:limit]


def _date_window(days: int, *, now: datetime | None = None) -> list[date]:
    if now is None:
        now = datetime.now(UTC)
    today = now.date()
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


async def _learner_trend_days(
    db: AsyncSession, *, learner: Learner, day_list: list[date]
) -> list[dict]:
    if not day_list:
        return []

    start = datetime.combine(day_list[0], datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(day_list[-1] + timedelta(days=1), datetime.min.time(), tzinfo=UTC)

    review_rows = await db.execute(
        select(
            func.date(SrsReviewLog.reviewed_at),
            func.count(SrsReviewLog.id),
            func.sum(case((SrsReviewLog.quality >= 3, 1), else_=0)),
        )
        .where(
            SrsReviewLog.learner_id == learner.id,
            SrsReviewLog.reviewed_at >= start,
            SrsReviewLog.reviewed_at < end,
        )
        .group_by(func.date(SrsReviewLog.reviewed_at))
    )
    reviews_by_day: dict[str, tuple[int, int]] = {}
    for day_value, total, correct in review_rows.all():
        reviews_by_day[str(day_value)] = (int(total or 0), int(correct or 0))

    released_rows = await db.execute(
        select(func.date(SrsCard.released_at), func.count(SrsCard.id))
        .where(
            SrsCard.learner_id == learner.id,
            SrsCard.released_at.is_not(None),
            SrsCard.released_at >= start,
            SrsCard.released_at < end,
        )
        .group_by(func.date(SrsCard.released_at))
    )
    released_by_day = {str(day_value): int(count) for day_value, count in released_rows.all()}

    challenge_rows = await db.execute(
        select(DailyChallengeLog.challenge_date, DailyChallengeLog.completed_at).where(
            DailyChallengeLog.learner_id == learner.id,
            DailyChallengeLog.challenge_date >= day_list[0],
            DailyChallengeLog.challenge_date <= day_list[-1],
        )
    )
    challenge_by_day = {
        day_value.isoformat() if hasattr(day_value, "isoformat") else str(day_value): (
            completed_at is not None
        )
        for day_value, completed_at in challenge_rows.all()
    }

    window_end = datetime.combine(day_list[-1] + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    cards_result = await db.execute(
        select(SrsCard).where(
            SrsCard.learner_id == learner.id,
            SrsCard.released_at.is_not(None),
            SrsCard.released_at < window_end,
        )
    )
    released_cards = list(cards_result.scalars().all())

    reviews_result = await db.execute(
        select(SrsReviewLog)
        .where(
            SrsReviewLog.learner_id == learner.id,
            SrsReviewLog.reviewed_at < window_end,
        )
        .order_by(SrsReviewLog.reviewed_at.asc(), SrsReviewLog.id.asc())
    )
    reviews_by_card: dict[int, list[SrsReviewLog]] = {}
    for review in reviews_result.scalars().all():
        reviews_by_card.setdefault(review.srs_card_id, []).append(review)

    points: list[dict] = []
    for day in day_list:
        key = day.isoformat()
        reviews, correct = reviews_by_day.get(key, (0, 0))
        cutoff = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        learning, familiar, mastered = _strength_counts_as_of(
            released_cards, reviews_by_card, cutoff
        )
        points.append(
            {
                "date": day,
                "reviews": reviews,
                "correct_reviews": correct,
                "accuracy_percent": _accuracy_percent(correct, reviews),
                "new_words": released_by_day.get(key, 0),
                "challenge_completed": challenge_by_day.get(key, False),
                "learning_count": learning,
                "familiar_count": familiar,
                "mastered_count": mastered,
            }
        )
    return points


async def get_family_trends(
    db: AsyncSession, *, parent_id: int, days: int = 14, now: datetime | None = None
) -> dict:
    clamped = max(7, min(30, days))
    day_list = _date_window(clamped, now=now)
    learners = await _parent_learners(db, parent_id)
    series: list[dict] = []
    for learner in learners:
        series.append(
            {
                "learner_id": learner.id,
                "display_name": learner.display_name,
                "emoji": resolve_learner_emoji(learner.emoji, learner.display_name),
                "days": await _learner_trend_days(db, learner=learner, day_list=day_list),
            }
        )
    return {"days": clamped, "learners": series}


async def get_learner_me_stats(db: AsyncSession, *, learner_id: int) -> dict:
    result = await db.execute(
        select(Learner).options(selectinload(Learner.user)).where(Learner.id == learner_id)
    )
    learner = result.scalar_one_or_none()
    if learner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learner not found")
    summary = await _learner_summary(db, learner)
    loop_progress = await loop_engine.progress_summary(db, learner_id=learner_id)
    return {
        "english_level": summary["english_level"],
        "display_name": summary["display_name"],
        "due_count": summary["due_count"],
        "reviewed_today": summary["reviewed_today"],
        "daily_practice_goal": summary["daily_practice_goal"],
        "daily_new_word_goal": summary["daily_new_word_goal"],
        "daily_learning_retention_goal": summary["daily_learning_retention_goal"],
        "daily_mastered_retention_goal": summary["daily_mastered_retention_goal"],
        "daily_retention_goal": summary["daily_retention_goal"],
        "review_accuracy_percent": summary["review_accuracy_percent"],
        "streak_days": summary["streak_days"],
        "dictation_sessions_completed": summary["dictation_sessions_completed"],
        "unresolved_mistakes": summary["unresolved_mistakes"],
        "learning_count": loop_progress["learning_count"],
        "familiar_count": loop_progress["familiar_count"],
        "mastered_count": loop_progress["mastered_count"],
        "new_released_today": loop_progress["new_released_today"],
        "new_remaining_today": loop_progress["new_remaining_today"],
        "new_released_this_week": loop_progress["new_released_this_week"],
        "weekly_new_target": loop_progress["weekly_new_target"],
        "daily_challenge_completed": loop_progress["daily_challenge_completed"],
        "daily_challenge_srs_completed": loop_progress["daily_challenge_srs_completed"],
        "daily_challenge_dictation_completed": loop_progress["daily_challenge_dictation_completed"],
    }
