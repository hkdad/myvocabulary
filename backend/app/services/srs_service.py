from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.sm2 import DEFAULT_EASE_FACTOR, SrsState, apply_review
from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.srs import SrsCard, SrsReviewLog
from app.models.word_list import MistakeLog, WordListItem
from app.services import dictionary_service, loop_engine, word_list_service

MISTAKE_CHALLENGE_WORD_LIMIT = 5
PRACTICE_ALL_MAX_CARDS = 200


async def _mistake_challenge_entry_ids(
    db: AsyncSession, *, learner_id: int, limit: int = MISTAKE_CHALLENGE_WORD_LIMIT
) -> list[int]:
    """Most recent unresolved mistake words, capped for one challenge session."""
    result = await db.execute(
        select(MistakeLog.dictionary_entry_id)
        .where(
            MistakeLog.learner_id == learner_id,
            MistakeLog.resolved_at.is_(None),
        )
        .order_by(MistakeLog.occurred_at.desc())
    )
    seen: set[int] = set()
    entry_ids: list[int] = []
    for entry_id in result.scalars().all():
        if entry_id in seen:
            continue
        seen.add(entry_id)
        entry_ids.append(entry_id)
        if len(entry_ids) >= limit:
            break
    return entry_ids


def _entry_summary(entry: DictionaryEntry) -> dict:
    return word_list_service.entry_summary(entry)


def card_to_dict(card: SrsCard) -> dict:
    return {
        "id": card.id,
        "dictionary_entry": _entry_summary(card.dictionary_entry),
        "ease_factor": card.ease_factor,
        "interval_days": card.interval_days,
        "repetitions": card.repetitions,
        "due_at": card.due_at,
        "last_reviewed_at": card.last_reviewed_at,
        "last_quality": card.last_quality,
        "state": card.state,
        "word_list_id": card.word_list_id,
    }


async def enrich_cards_zh_hant(
    db: AsyncSession, cards: list[SrsCard], *, live_translate: bool = False
) -> None:
    """Attach Traditional Chinese glosses when already cached.

    Live OpenAI translation is opt-in — daily challenge / due loads must stay fast.
    Dictionary lookup still translates on demand.
    """
    if not live_translate:
        return
    seen: set[int] = set()
    for card in cards:
        entry = card.dictionary_entry
        if entry is None or entry.id in seen:
            continue
        seen.add(entry.id)
        if entry.definition_zh_hant and entry.definition_zh_hant.strip():
            continue
        await dictionary_service.ensure_zh_hant(db, entry)


async def _get_card_for_learner(db: AsyncSession, card_id: int, learner_id: int) -> SrsCard:
    result = await db.execute(
        select(SrsCard)
        .options(selectinload(SrsCard.dictionary_entry))
        .where(SrsCard.id == card_id, SrsCard.learner_id == learner_id)
    )
    card = result.scalar_one_or_none()
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return card


async def initialize_from_word_list(
    db: AsyncSession, *, learner_id: int, word_list_id: int
) -> dict[str, int]:
    word_list = await word_list_service.get_word_list_for_learner(db, word_list_id, learner_id)

    items_result = await db.execute(
        select(WordListItem).where(WordListItem.word_list_id == word_list_id)
    )
    items = items_result.scalars().all()
    if not items:
        return {"created_count": 0, "skipped_count": 0, "total_cards": 0}

    entry_ids = [item.dictionary_entry_id for item in items]
    existing_result = await db.execute(
        select(SrsCard).where(
            SrsCard.learner_id == learner_id,
            SrsCard.dictionary_entry_id.in_(entry_ids),
        )
    )
    existing_cards = existing_result.scalars().all()
    existing_ids = {card.dictionary_entry_id for card in existing_cards}
    now = datetime.now(UTC)
    far_future = now + timedelta(days=loop_engine.FAR_FUTURE_DAYS)

    learner_result = await db.execute(select(Learner).where(Learner.id == learner_id))
    learner = learner_result.scalar_one()
    is_bank = word_list.source == "bank"
    is_school_list = word_list.source == "learner"
    release_immediately = not is_bank and (
        is_school_list
        or len(items) <= (learner.daily_new_word_goal or loop_engine.default_new_goal(learner))
    )

    for card in existing_cards:
        card.word_list_id = word_list_id
        if is_bank:
            if card.released_at is None:
                card.due_at = far_future
        elif release_immediately:
            card.due_at = now
            card.released_at = card.released_at or now
        else:
            if card.released_at is None:
                card.due_at = far_future

    created = 0
    for item in items:
        if item.dictionary_entry_id in existing_ids:
            continue
        if is_bank or not release_immediately:
            db.add(
                SrsCard(
                    learner_id=learner_id,
                    dictionary_entry_id=item.dictionary_entry_id,
                    word_list_id=word_list_id,
                    ease_factor=DEFAULT_EASE_FACTOR,
                    interval_days=0,
                    repetitions=0,
                    due_at=far_future,
                    state="new",
                    released_at=None,
                )
            )
        else:
            db.add(
                SrsCard(
                    learner_id=learner_id,
                    dictionary_entry_id=item.dictionary_entry_id,
                    word_list_id=word_list_id,
                    ease_factor=DEFAULT_EASE_FACTOR,
                    interval_days=0,
                    repetitions=0,
                    due_at=now,
                    state="new",
                    released_at=now,
                )
            )
        created += 1

    await db.commit()

    total_result = await db.execute(
        select(func.count(SrsCard.id)).where(SrsCard.learner_id == learner_id)
    )
    total_cards = total_result.scalar_one()
    return {
        "created_count": created,
        "skipped_count": len(entry_ids) - created,
        "total_cards": total_cards,
    }


async def get_due_cards(
    db: AsyncSession,
    *,
    learner_id: int,
    daily_goal: int,
    limit: int | None = None,
    word_list_id: int | None = None,
    mistakes_only: bool = False,
    practice_all: bool = False,
) -> dict:
    now = datetime.now(UTC)

    if practice_all:
        if word_list_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="practice_all requires word_list_id",
            )
        await word_list_service.get_learner_owned_word_list(db, word_list_id, learner_id)
        items_result = await db.execute(
            select(
                WordListItem.dictionary_entry_id,
                WordListItem.sort_order,
                WordListItem.id,
            )
            .where(WordListItem.word_list_id == word_list_id)
            .order_by(WordListItem.sort_order, WordListItem.id)
        )
        item_rows = items_result.all()
        list_entry_ids = [entry_id for entry_id, _, _ in item_rows]
        sort_key = {entry_id: (sort_order, item_id) for entry_id, sort_order, item_id in item_rows}
        filters = [
            SrsCard.learner_id == learner_id,
            SrsCard.released_at.is_not(None),
            SrsCard.dictionary_entry_id.in_(list_entry_ids or [-1]),
        ]
        max_cards = limit if limit is not None else min(len(list_entry_ids), PRACTICE_ALL_MAX_CARDS)
        if limit is not None:
            max_cards = min(max_cards, limit)

        due_count_result = await db.execute(select(func.count(SrsCard.id)).where(*filters))
        due_count = due_count_result.scalar_one()

        result = await db.execute(
            select(SrsCard).options(selectinload(SrsCard.dictionary_entry)).where(*filters)
        )
        cards = list(result.scalars().all())
        cards.sort(key=lambda card: sort_key.get(card.dictionary_entry_id, (9999, 9999)))
        cards = cards[:max_cards]
        await enrich_cards_zh_hant(db, cards)
        return {
            "cards": [card_to_dict(card) for card in cards],
            "due_count": due_count,
            "daily_goal": daily_goal,
        }

    max_cards = limit if limit is not None else daily_goal

    filters = [
        SrsCard.learner_id == learner_id,
        SrsCard.due_at <= now,
        SrsCard.released_at.is_not(None),
    ]
    if word_list_id is not None:
        await word_list_service.get_word_list_for_learner(db, word_list_id, learner_id)
        list_entry_ids = (
            (
                await db.execute(
                    select(WordListItem.dictionary_entry_id).where(
                        WordListItem.word_list_id == word_list_id
                    )
                )
            )
            .scalars()
            .all()
        )
        filters.append(SrsCard.dictionary_entry_id.in_(list(list_entry_ids) or [-1]))
    if mistakes_only:
        challenge_entry_ids = await _mistake_challenge_entry_ids(db, learner_id=learner_id)
        if not challenge_entry_ids:
            return {"cards": [], "due_count": 0, "daily_goal": daily_goal}
        filters.append(SrsCard.dictionary_entry_id.in_(challenge_entry_ids))
        max_cards = min(len(challenge_entry_ids), MISTAKE_CHALLENGE_WORD_LIMIT)
        if limit is not None:
            max_cards = min(max_cards, limit)

    due_count_result = await db.execute(select(func.count(SrsCard.id)).where(*filters))
    due_count = due_count_result.scalar_one()

    result = await db.execute(
        select(SrsCard)
        .options(selectinload(SrsCard.dictionary_entry))
        .where(*filters)
        .order_by(SrsCard.due_at)
        .limit(max_cards)
    )
    cards = list(result.scalars().all())
    await enrich_cards_zh_hant(db, cards)
    return {
        "cards": [card_to_dict(card) for card in cards],
        "due_count": due_count,
        "daily_goal": daily_goal,
    }


async def get_review_stats(db: AsyncSession, *, learner_id: int, daily_goal: int) -> dict:
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    reviewed_result = await db.execute(
        select(func.count(SrsReviewLog.id)).where(
            SrsReviewLog.learner_id == learner_id,
            SrsReviewLog.reviewed_at >= start_of_day,
        )
    )
    reviewed_today = reviewed_result.scalar_one()

    due_count_result = await db.execute(
        select(func.count(SrsCard.id)).where(
            SrsCard.learner_id == learner_id,
            SrsCard.due_at <= now,
            SrsCard.released_at.is_not(None),
        )
    )
    due_count = due_count_result.scalar_one()

    total_result = await db.execute(
        select(func.count(SrsCard.id)).where(SrsCard.learner_id == learner_id)
    )
    total_cards = total_result.scalar_one()

    return {
        "reviewed_today": reviewed_today,
        "due_count": due_count,
        "daily_goal": daily_goal,
        "total_cards": total_cards,
    }


async def answer_card(db: AsyncSession, *, learner_id: int, card_id: int, quality: int) -> dict:
    card = await _get_card_for_learner(db, card_id, learner_id)
    now = datetime.now(UTC)

    state = SrsState(
        ease_factor=card.ease_factor,
        interval_days=card.interval_days,
        repetitions=card.repetitions,
        state=card.state,
    )
    update = apply_review(state, quality, now=now)

    log = SrsReviewLog(
        srs_card_id=card.id,
        learner_id=learner_id,
        quality=quality,
        ease_factor_before=card.ease_factor,
        ease_factor_after=update.ease_factor,
        interval_before=card.interval_days,
        interval_after=update.interval_days,
        reviewed_at=now,
    )
    db.add(log)

    card.ease_factor = update.ease_factor
    card.interval_days = update.interval_days
    card.repetitions = update.repetitions
    card.state = update.state
    card.due_at = update.due_at
    card.last_reviewed_at = now
    card.last_quality = quality

    if quality < 3:
        db.add(
            MistakeLog(
                learner_id=learner_id,
                dictionary_entry_id=card.dictionary_entry_id,
                context="review",
                wrong_answer=None,
            )
        )

    await db.commit()
    learner_result = await db.execute(select(Learner).where(Learner.id == learner_id))
    learner = learner_result.scalar_one_or_none()
    if learner is not None:
        from app.services import achievement_service

        parent_id = await loop_engine.get_learner_parent_id(db, learner)
        await achievement_service.sync_achievements(db, learner=learner, parent_id=parent_id)
    await db.refresh(card)
    result = await db.execute(
        select(SrsCard).options(selectinload(SrsCard.dictionary_entry)).where(SrsCard.id == card.id)
    )
    refreshed = result.scalar_one()
    return {"card": card_to_dict(refreshed)}


async def get_mistake_cards(db: AsyncSession, *, learner_id: int) -> list[dict]:
    result = await db.execute(
        select(MistakeLog, DictionaryEntry)
        .join(DictionaryEntry, MistakeLog.dictionary_entry_id == DictionaryEntry.id)
        .where(
            MistakeLog.learner_id == learner_id,
            MistakeLog.resolved_at.is_(None),
        )
        .order_by(MistakeLog.occurred_at.desc())
        .limit(50)
    )
    rows = result.all()
    seen_entry_ids: set[int] = set()
    cards: list[dict] = []
    for mistake, entry in rows:
        if entry.id in seen_entry_ids:
            continue
        seen_entry_ids.add(entry.id)
        cards.append(
            {
                "id": mistake.id,
                "dictionary_entry": _entry_summary(entry),
                "context": mistake.context,
                "occurred_at": mistake.occurred_at,
            }
        )
    return cards


async def complete_mistake_challenge(
    db: AsyncSession, *, learner_id: int, dictionary_entry_ids: list[int]
) -> dict[str, int]:
    if len(dictionary_entry_ids) > MISTAKE_CHALLENGE_WORD_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mistake challenge allows up to {MISTAKE_CHALLENGE_WORD_LIMIT} words",
        )
    unique_ids = list(dict.fromkeys(dictionary_entry_ids))
    if not unique_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No words to clear",
        )

    now = datetime.now(UTC)
    result = await db.execute(
        select(MistakeLog).where(
            MistakeLog.learner_id == learner_id,
            MistakeLog.dictionary_entry_id.in_(unique_ids),
            MistakeLog.resolved_at.is_(None),
        )
    )
    logs = list(result.scalars().all())
    for log in logs:
        log.resolved_at = now
    await db.commit()
    return {"resolved_count": len(logs), "entry_count": len(unique_ids)}


async def initialize_mistake_reviews(db: AsyncSession, *, learner_id: int) -> dict[str, int]:
    entry_ids = await _mistake_challenge_entry_ids(db, learner_id=learner_id)
    created = 0
    for entry_id in entry_ids:
        existing = await db.execute(
            select(SrsCard).where(
                SrsCard.learner_id == learner_id,
                SrsCard.dictionary_entry_id == entry_id,
            )
        )
        card = existing.scalar_one_or_none()
        if card is None:
            await ensure_review_card_for_entry(
                db, learner_id=learner_id, dictionary_entry_id=entry_id
            )
            created += 1
        else:
            card.due_at = datetime.now(UTC)
            card.released_at = card.released_at or datetime.now(UTC)
    await db.commit()
    return {"created_count": created, "mistake_count": len(entry_ids)}


async def ensure_review_card_for_entry(
    db: AsyncSession,
    *,
    learner_id: int,
    dictionary_entry_id: int,
    word_list_id: int | None = None,
) -> None:
    """Ensure a mistake word appears in the learner's SRS review queue."""
    from app.core.sm2 import DEFAULT_EASE_FACTOR

    now = datetime.now(UTC)
    result = await db.execute(
        select(SrsCard).where(
            SrsCard.learner_id == learner_id,
            SrsCard.dictionary_entry_id == dictionary_entry_id,
        )
    )
    card = result.scalar_one_or_none()
    if card is None:
        db.add(
            SrsCard(
                learner_id=learner_id,
                dictionary_entry_id=dictionary_entry_id,
                word_list_id=word_list_id,
                ease_factor=DEFAULT_EASE_FACTOR,
                interval_days=0,
                repetitions=0,
                due_at=now,
                state="new",
                released_at=now,
            )
        )
    else:
        card.due_at = now
        card.released_at = card.released_at or now
