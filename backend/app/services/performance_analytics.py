"""Performance analytics for learner level assessment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dictation import DictationAttempt, DictationSession
from app.models.srs import SrsCard, SrsReviewLog
from app.models.word_list import WordListItem
from app.services import loop_engine


async def current_level_released_cards(
    db: AsyncSession, learner, parent_id: int
) -> tuple[list[SrsCard], int]:
    """
    Released SRS cards whose bank entries match the learner's current CEFR.

    Returns ``(cards, bank_at_level_count)``. ``bank_at_level_count`` is the full
    family-bank size at the learner's level (coverage context); cards are only
    the released subset used for readiness scoring.
    """
    cards, bank_at_level = await loop_engine.released_cards_for_level(
        db,
        learner_id=learner.id,
        parent_id=parent_id,
        level=learner.english_level,
    )
    return cards, bank_at_level


async def calculate_consistency_score(
    db: AsyncSession,
    learner_id: int,
    days: int = 14,
    *,
    card_ids: set[int] | None = None,
) -> float:
    """
    Calculate consistency score based on variance in daily accuracy.
    Lower variance = more consistent performance.

    When ``card_ids`` is provided, only reviews for those cards count
    (current-level scope for readiness).

    Returns: 0.0-1.0 (1.0 = perfectly consistent)
    """
    since = datetime.now(UTC) - timedelta(days=days)

    filters = [
        SrsReviewLog.learner_id == learner_id,
        SrsReviewLog.reviewed_at >= since,
    ]
    if card_ids is not None:
        if not card_ids:
            return 0.5
        filters.append(SrsReviewLog.srs_card_id.in_(card_ids))

    result = await db.execute(
        select(
            func.date(SrsReviewLog.reviewed_at).label("review_date"),
            func.count(SrsReviewLog.id).label("total"),
            func.sum(case((SrsReviewLog.quality >= 3, 1), else_=0)).label("correct"),
        )
        .where(*filters)
        .group_by(func.date(SrsReviewLog.reviewed_at))
    )

    daily_accuracies = []
    for row in result.all():
        total = row.total
        correct = row.correct or 0
        if total > 0:
            accuracy = correct / total
            daily_accuracies.append(accuracy)

    if len(daily_accuracies) < 3:
        return 0.5

    mean = sum(daily_accuracies) / len(daily_accuracies)
    variance = sum((x - mean) ** 2 for x in daily_accuracies) / len(daily_accuracies)
    std_dev = variance**0.5

    consistency = max(0.0, 1.0 - (std_dev * 2.5))
    return round(consistency, 2)


async def calculate_retention_strength(
    db: AsyncSession,
    learner_id: int,
    *,
    cards: list[SrsCard] | None = None,
    days: int = 30,
) -> dict:
    """
    Calculate retention metrics: forgetting rate, relearning frequency.

    When ``cards`` is provided, only those cards are scored (current-level scope).
    Wrong reviews older than ``days`` are ignored so early mistakes do not linger forever.

    Returns:
    {
        "forgetting_rate": 0.0-1.0,  # % of cards that went to relearning
        "relearning_frequency": float,  # avg relearning events per card
        "score": 0.0-1.0  # composite retention strength
    }
    """
    if cards is None:
        cards_result = await db.execute(
            select(SrsCard).where(
                SrsCard.learner_id == learner_id,
                SrsCard.released_at.is_not(None),
            )
        )
        cards = list(cards_result.scalars().all())

    if not cards:
        return {"forgetting_rate": 0.0, "relearning_frequency": 0.0, "score": 0.5}

    card_ids = [card.id for card in cards if card.id is not None]
    if not card_ids:
        return {"forgetting_rate": 0.0, "relearning_frequency": 0.0, "score": 0.5}

    since = datetime.now(UTC) - timedelta(days=days)
    relearning_result = await db.execute(
        select(SrsReviewLog.srs_card_id, func.count(SrsReviewLog.id))
        .where(
            SrsReviewLog.srs_card_id.in_(card_ids),
            SrsReviewLog.quality < 3,
            SrsReviewLog.reviewed_at >= since,
        )
        .group_by(SrsReviewLog.srs_card_id)
    )

    relearning_by_card = dict(relearning_result.all())
    cards_with_relearning = len(relearning_by_card)
    total_relearning_events = sum(relearning_by_card.values())

    forgetting_rate = cards_with_relearning / len(cards)
    relearning_frequency = total_relearning_events / len(cards)

    retention_score = max(0.0, 1.0 - (forgetting_rate * 0.5 + min(relearning_frequency / 3, 0.5)))

    return {
        "forgetting_rate": round(forgetting_rate, 2),
        "relearning_frequency": round(relearning_frequency, 2),
        "score": round(retention_score, 2),
    }


async def analyze_mistake_patterns(db: AsyncSession, learner_id: int, days: int = 30) -> dict:
    """
    Analyze mistake patterns from dictation and review logs.

    Returns:
    {
        "repeat_offenders": [{"word": str, "mistakes": int}],  # top 10
        "total_mistakes": int,
        "unique_mistakes": int,
        "common_error_type": str  # "spelling" | "recall" | "mixed"
    }
    """
    since = datetime.now(UTC) - timedelta(days=days)

    dictation_mistakes_result = await db.execute(
        select(DictationAttempt.expected_word, func.count(DictationAttempt.id))
        .join(DictationSession, DictationAttempt.session_id == DictationSession.id)
        .where(
            DictationSession.learner_id == learner_id,
            DictationAttempt.is_correct.is_(False),
            DictationSession.completed_at.is_not(None),
            DictationSession.completed_at >= since,
        )
        .group_by(DictationAttempt.expected_word)
        .order_by(func.count(DictationAttempt.id).desc())
        .limit(10)
    )

    repeat_offenders = [
        {"word": word, "mistakes": count} for word, count in dictation_mistakes_result.all()
    ]

    review_mistakes_result = await db.execute(
        select(func.count(SrsReviewLog.id)).where(
            SrsReviewLog.learner_id == learner_id,
            SrsReviewLog.quality < 3,
            SrsReviewLog.reviewed_at >= since,
        )
    )
    review_mistakes = review_mistakes_result.scalar_one()

    dictation_total_result = await db.execute(
        select(func.count(DictationAttempt.id))
        .join(DictationSession, DictationAttempt.session_id == DictationSession.id)
        .where(
            DictationSession.learner_id == learner_id,
            DictationAttempt.is_correct.is_(False),
            DictationSession.completed_at.is_not(None),
            DictationSession.completed_at >= since,
        )
    )
    dictation_mistakes = dictation_total_result.scalar_one()

    total_mistakes = review_mistakes + dictation_mistakes
    unique_mistakes = len(repeat_offenders)

    error_type = "mixed"
    if dictation_mistakes > review_mistakes * 2:
        error_type = "spelling"
    elif review_mistakes > dictation_mistakes * 2:
        error_type = "recall"

    return {
        "repeat_offenders": repeat_offenders,
        "total_mistakes": total_mistakes,
        "unique_mistakes": unique_mistakes,
        "common_error_type": error_type,
    }


async def calculate_category_coverage(
    db: AsyncSession, learner, parent_id: int, *, level: str | None = None
) -> dict:
    """
    Calculate mastery percentage per category among **released** words at level.

    Denominator is released bank items at the CEFR band (not the full unreleased
    bank), matching vocabulary-breadth honesty.

    Returns:
    {
        "categories": {
            "Food": {"mastered": 12, "total": 20, "percentage": 0.60},
            ...
        },
        "score": 0.0-1.0  # lowest category percentage (weakest link)
    }
    """
    from app.services.word_bank_service import format_category_name, item_category_names

    target_level = (level or learner.english_level).strip()

    bank = await loop_engine.get_family_bank(db, parent_id)
    if bank is None:
        return {"categories": {}, "score": 0.5}

    released_cards, _bank_at_level = await loop_engine.released_cards_for_level(
        db,
        learner_id=learner.id,
        parent_id=parent_id,
        level=target_level,
    )
    if not released_cards:
        return {"categories": {}, "score": 0.5}

    released_entry_ids = {
        card.dictionary_entry_id for card in released_cards if card.dictionary_entry_id is not None
    }

    items_result = await db.execute(
        select(WordListItem)
        .options(selectinload(WordListItem.categories))
        .where(WordListItem.word_list_id == bank.id)
    )
    items = list(items_result.scalars().all())

    released_level_items = [
        item
        for item in items
        if loop_engine.level_matches(item.level, target_level)
        and item.dictionary_entry_id in released_entry_ids
    ]

    if not released_level_items:
        return {"categories": {}, "score": 0.5}

    card_ids = [card.id for card in released_cards if card.id is not None]
    distinct_days_map = await loop_engine.distinct_review_days_by_card(db, card_ids)

    mastered_entry_ids = {
        card.dictionary_entry_id
        for card in released_cards
        if card.id and distinct_days_map.get(card.id, 0) >= loop_engine.MASTERED_MIN_DISTINCT_DAYS
    }

    category_stats: dict[str, dict] = {}
    for item in released_level_items:
        categories = item_category_names(item) or ["General"]
        for raw_cat in categories:
            cat = format_category_name(raw_cat)
            if cat not in category_stats:
                category_stats[cat] = {"mastered": 0, "total": 0}
            category_stats[cat]["total"] += 1
            if item.dictionary_entry_id in mastered_entry_ids:
                category_stats[cat]["mastered"] += 1

    for cat, stats in category_stats.items():
        stats["percentage"] = (
            round(stats["mastered"] / stats["total"], 2) if stats["total"] > 0 else 0.0
        )

    lowest_percentage = min((stats["percentage"] for stats in category_stats.values()), default=0.5)

    return {
        "categories": category_stats,
        "score": lowest_percentage,
    }


async def calculate_vocabulary_breadth(
    db: AsyncSession, learner, parent_id: int, *, level: str | None = None
) -> dict:
    """
    Calculate Familiar+ percentage among **released** words at the given level.

    Denominator is released cards at the level (not the full bank).
    Also returns ``bank_at_level`` for coverage context.

    Returns:
    {
        "bank_at_level": int,
        "released_at_level": int,
        "total_at_level": int,  # alias of released_at_level (API stability)
        "familiar_or_mastered": int,
        "mastered": int,
        "percentage": 0.0-1.0,
        "score": 0.0-1.0
    }
    """
    target_level = (level or learner.english_level).strip()
    cards, bank_at_level = await loop_engine.released_cards_for_level(
        db,
        learner_id=learner.id,
        parent_id=parent_id,
        level=target_level,
    )
    released_at_level = len(cards)

    if bank_at_level == 0:
        return {
            "bank_at_level": 0,
            "released_at_level": 0,
            "total_at_level": 0,
            "familiar_or_mastered": 0,
            "mastered": 0,
            "percentage": 0.0,
            "score": 0.5,
        }

    if released_at_level == 0:
        return {
            "bank_at_level": bank_at_level,
            "released_at_level": 0,
            "total_at_level": 0,
            "familiar_or_mastered": 0,
            "mastered": 0,
            "percentage": 0.0,
            "score": 0.5,
        }

    card_ids = [card.id for card in cards if card.id is not None]
    distinct_days_map = await loop_engine.distinct_review_days_by_card(db, card_ids)

    familiar_or_mastered = 0
    mastered = 0
    for card in cards:
        if not card.id:
            continue
        days = distinct_days_map.get(card.id, 0)
        if days >= loop_engine.FAMILIAR_MIN_DISTINCT_DAYS:
            familiar_or_mastered += 1
        if days >= loop_engine.MASTERED_MIN_DISTINCT_DAYS:
            mastered += 1

    percentage = familiar_or_mastered / released_at_level

    return {
        "bank_at_level": bank_at_level,
        "released_at_level": released_at_level,
        "total_at_level": released_at_level,
        "familiar_or_mastered": familiar_or_mastered,
        "mastered": mastered,
        "percentage": round(percentage, 2),
        "score": round(percentage, 2),
    }


async def calculate_speed_metrics(db: AsyncSession, learner_id: int, days: int = 14) -> dict:
    """
    Calculate speed/fluency metrics.
    Note: Currently returns placeholder data since response_time_ms is not yet tracked.

    Returns:
    {
        "avg_response_time_ms": float | None,
        "trend": "improving" | "stable" | "declining" | None,
        "score": 0.0-1.0
    }
    """
    return {
        "avg_response_time_ms": None,
        "trend": None,
        "score": 0.5,
        "note": "Response time tracking not yet implemented",
    }


async def review_accuracy_for_cards(
    db: AsyncSession, learner_id: int, days: int, card_ids: set[int]
) -> tuple[float, int]:
    """Recognition accuracy over the window, limited to the given SRS card ids."""
    since = datetime.now(UTC) - timedelta(days=days)
    if not card_ids:
        return 0.0, 0

    result = await db.execute(
        select(SrsReviewLog.quality).where(
            SrsReviewLog.learner_id == learner_id,
            SrsReviewLog.reviewed_at >= since,
            SrsReviewLog.srs_card_id.in_(card_ids),
        )
    )
    qualities = result.scalars().all()
    total = len(qualities)
    if total == 0:
        return 0.0, 0
    correct = sum(1 for quality in qualities if quality >= 3)
    return round((correct / total) * 100, 1), total


async def get_performance_metrics(
    db: AsyncSession, learner, parent_id: int, days: int = 14, *, level: str | None = None
) -> dict:
    """
    Collect all performance metrics for a learner.

    Readiness dimensions that measure practice quality (accuracy, consistency,
    retention, vocabulary breadth) are scoped to released cards at the given
    CEFR level (defaults to learner's current level).
    """
    target_level = (level or learner.english_level).strip()
    level_cards, _bank_at_level = await loop_engine.released_cards_for_level(
        db,
        learner_id=learner.id,
        parent_id=parent_id,
        level=target_level,
    )
    level_card_ids = {card.id for card in level_cards if card.id is not None}

    consistency = await calculate_consistency_score(db, learner.id, days, card_ids=level_card_ids)
    retention = await calculate_retention_strength(db, learner.id, cards=level_cards)
    mistakes = await analyze_mistake_patterns(db, learner.id, days=30)
    category_coverage = await calculate_category_coverage(
        db, learner, parent_id, level=target_level
    )
    vocabulary_breadth = await calculate_vocabulary_breadth(
        db, learner, parent_id, level=target_level
    )
    speed = await calculate_speed_metrics(db, learner.id, days)

    from app.services import ai_level_service

    review_accuracy, review_samples = await review_accuracy_for_cards(
        db, learner.id, days, level_card_ids
    )
    # Dictation stays global (20% of accuracy) — attempts are not level-tagged.
    dictation_accuracy, _ = await ai_level_service._dictation_accuracy(db, learner.id, days=30)

    return {
        "consistency": {
            "score": consistency,
            "description": "Performance stability over time (current level)",
        },
        "retention": retention,
        "mistakes": mistakes,
        "category_coverage": category_coverage,
        "vocabulary_breadth": vocabulary_breadth,
        "speed": speed,
        "review_accuracy": review_accuracy,
        "review_samples": review_samples,
        "dictation_accuracy": dictation_accuracy,
    }
