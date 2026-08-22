"""Phase 2 Loop Engine — daily mix, drip, and strength derivation."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cefr import CEFR_LEVELS, level_index, normalize_level_label
from app.core.sm2 import DEFAULT_EASE_FACTOR
from app.models.daily_challenge import DailyChallengeLog
from app.models.learner import Learner
from app.models.srs import SrsCard, SrsReviewLog
from app.models.user import User
from app.models.word_list import WordList, WordListItem
from app.services import srs_service

PLACEHOLDER_DEFINITION = "Definition pending — added from family word bank."
_UNSET = object()

FAMILIAR_MIN_DISTINCT_DAYS = 2  # 2 distinct review days
MASTERED_MIN_DISTINCT_DAYS = 3  # 3+ distinct review days
CORRECT_QUALITY_THRESHOLD = 3
SOFT_DAILY_PASS_THRESHOLD = 0.8  # same bar as Level-up exam pass

FAR_FUTURE_DAYS = 365


def level_matches(item_level: str | None, learner_level: str) -> bool:
    """True when a bank word is at the learner's working level (exact CEFR or custom label)."""
    if not item_level or not item_level.strip():
        return False
    if not learner_level or not learner_level.strip():
        return False

    item = item_level.strip()
    learner = learner_level.strip()
    if item.lower() == learner.lower():
        return True

    item_cefr = normalize_level_label(item)
    learner_cefr = normalize_level_label(learner)
    if item_cefr in CEFR_LEVELS and learner_cefr in CEFR_LEVELS:
        return item_cefr == learner_cefr
    return False


def level_matches_at_or_below(item_level: str | None, learner_level: str) -> bool:
    """True when a bank word is at or below the learner CEFR band (legacy helper)."""
    if not item_level or not item_level.strip():
        return False
    if not learner_level or not learner_level.strip():
        return False

    item = item_level.strip()
    learner = learner_level.strip()
    if item.lower() == learner.lower():
        return True

    item_cefr = normalize_level_label(item)
    learner_cefr = normalize_level_label(learner)
    if item_cefr in CEFR_LEVELS and learner_cefr in CEFR_LEVELS:
        return CEFR_LEVELS.index(item_cefr) <= CEFR_LEVELS.index(learner_cefr)
    return False


def derive_strength(*, distinct_review_days: int) -> str:
    """Bucket a released card by distinct UTC days with at least one correct review."""
    if distinct_review_days >= MASTERED_MIN_DISTINCT_DAYS:
        return "mastered"
    if distinct_review_days >= FAMILIAR_MIN_DISTINCT_DAYS:
        return "familiar"
    if distinct_review_days >= 1:
        return "learning"
    return "learning"


async def distinct_review_days_by_card(
    db: AsyncSession,
    card_ids: list[int],
    *,
    before: datetime | None = None,
) -> dict[int, int]:
    """Return card_id → distinct UTC days with ≥1 correct review (quality ≥ threshold)."""
    if not card_ids:
        return {}

    stmt = (
        select(
            SrsReviewLog.srs_card_id,
            func.count(func.distinct(func.date(SrsReviewLog.reviewed_at))),
        )
        .where(
            SrsReviewLog.srs_card_id.in_(card_ids),
            SrsReviewLog.quality >= CORRECT_QUALITY_THRESHOLD,
        )
        .group_by(SrsReviewLog.srs_card_id)
    )
    if before is not None:
        stmt = stmt.where(SrsReviewLog.reviewed_at < before)

    result = await db.execute(stmt)
    return {card_id: int(day_count) for card_id, day_count in result.all()}


def strength_for_card(card: SrsCard, distinct_days_map: dict[int, int]) -> str | None:
    """Return strength bucket, or None when the card has no reviews yet."""
    if card.id is None:
        return None
    days = distinct_days_map.get(card.id, 0)
    if days <= 0:
        return None
    return derive_strength(distinct_review_days=days)


def _empty_strength_counts() -> dict[str, int]:
    return {
        "bank_total": 0,
        "released": 0,
        "learning": 0,
        "familiar": 0,
        "mastered": 0,
    }


def _bucket_strength_counts(
    cards: list[SrsCard], distinct_days_map: dict[int, int]
) -> dict[str, int]:
    counts = {"released": 0, "learning": 0, "familiar": 0, "mastered": 0}
    for card in cards:
        counts["released"] += 1
        strength = strength_for_card(card, distinct_days_map)
        if strength is not None:
            counts[strength] += 1
    return counts


async def bank_level_labels(db: AsyncSession, parent_id: int) -> list[str]:
    """Distinct non-empty level tags in the family bank, CEFR-ordered then alpha."""
    bank = await get_family_bank(db, parent_id)
    if bank is None:
        return []

    result = await db.execute(
        select(WordListItem.level).where(WordListItem.word_list_id == bank.id).distinct()
    )
    labels = sorted(
        {(level or "").strip() for (level,) in result.all() if level and level.strip()},
        key=lambda label: (level_index(label), label.lower()),
    )
    return labels


async def released_cards_for_level(
    db: AsyncSession,
    *,
    learner_id: int,
    parent_id: int | None,
    level: str,
) -> tuple[list[SrsCard], int]:
    if parent_id is None:
        return [], 0

    bank = await get_family_bank(db, parent_id)
    if bank is None:
        return [], 0

    items_result = await db.execute(
        select(WordListItem.dictionary_entry_id, WordListItem.level).where(
            WordListItem.word_list_id == bank.id,
        )
    )
    entry_ids = [
        entry_id for entry_id, item_level in items_result.all() if level_matches(item_level, level)
    ]
    bank_total = len(entry_ids)
    if not entry_ids:
        return [], 0

    cards_result = await db.execute(
        select(SrsCard).where(
            SrsCard.learner_id == learner_id,
            SrsCard.dictionary_entry_id.in_(entry_ids),
            SrsCard.released_at.is_not(None),
        )
    )
    return list(cards_result.scalars().all()), bank_total


async def strength_counts_for_level(
    db: AsyncSession,
    *,
    learner_id: int,
    parent_id: int | None,
    level: str,
) -> dict[str, int]:
    cards, bank_total = await released_cards_for_level(
        db, learner_id=learner_id, parent_id=parent_id, level=level
    )
    if not cards:
        counts = _empty_strength_counts()
        counts["bank_total"] = bank_total
        return counts

    distinct_days_map = await distinct_review_days_by_card(
        db, [card.id for card in cards if card.id is not None]
    )
    buckets = _bucket_strength_counts(cards, distinct_days_map)
    return {"bank_total": bank_total, **buckets}


async def strength_counts_overall(
    db: AsyncSession,
    *,
    learner_id: int,
    parent_id: int | None,
) -> dict[str, int]:
    if parent_id is None:
        return _empty_strength_counts()

    bank = await get_family_bank(db, parent_id)
    if bank is None:
        return _empty_strength_counts()

    items_result = await db.execute(
        select(WordListItem.dictionary_entry_id).where(WordListItem.word_list_id == bank.id)
    )
    entry_ids = [entry_id for (entry_id,) in items_result.all()]
    bank_total = len(entry_ids)
    if not entry_ids:
        counts = _empty_strength_counts()
        counts["bank_total"] = 0
        return counts

    cards_result = await db.execute(
        select(SrsCard).where(
            SrsCard.learner_id == learner_id,
            SrsCard.dictionary_entry_id.in_(entry_ids),
            SrsCard.released_at.is_not(None),
        )
    )
    cards = list(cards_result.scalars().all())
    if not cards:
        counts = _empty_strength_counts()
        counts["bank_total"] = bank_total
        return counts

    distinct_days_map = await distinct_review_days_by_card(
        db, [card.id for card in cards if card.id is not None]
    )
    buckets = _bucket_strength_counts(cards, distinct_days_map)
    return {"bank_total": bank_total, **buckets}


def default_new_goal(learner: Learner) -> int:
    return 8 if learner.ui_mode == "teen" else 5


def daily_new_goal(learner: Learner) -> int:
    return learner.daily_new_word_goal or default_new_goal(learner)


def default_learning_retention_mix(learner: Learner) -> int:
    if learner.daily_learning_retention_mix is None:
        return 1
    return learner.daily_learning_retention_mix


def default_mastered_retention_mix(learner: Learner) -> int:
    if learner.daily_mastered_retention_mix is None:
        return 1
    return learner.daily_mastered_retention_mix


def daily_learning_retention_goal(learner: Learner) -> int:
    return default_learning_retention_mix(learner)


def daily_mastered_retention_goal(learner: Learner) -> int:
    return default_mastered_retention_mix(learner)


def daily_retention_goal(learner: Learner) -> int:
    return daily_learning_retention_goal(learner) + daily_mastered_retention_goal(learner)


def daily_practice_goal(learner: Learner) -> int:
    return daily_new_goal(learner) + daily_retention_goal(learner)


def _daily_shuffle_seed(learner_id: int, challenge_date: date) -> int:
    digest = hashlib.sha256(f"{learner_id}:{challenge_date.isoformat()}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _start_of_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _far_future(now: datetime) -> datetime:
    return now + timedelta(days=FAR_FUTURE_DAYS)


async def get_family_bank(db: AsyncSession, parent_id: int) -> WordList | None:
    result = await db.execute(
        select(WordList).where(WordList.parent_id == parent_id, WordList.source == "bank")
    )
    return result.scalar_one_or_none()


async def count_released_today(db: AsyncSession, learner_id: int, now: datetime) -> int:
    start = _start_of_day(now)
    result = await db.execute(
        select(func.count(SrsCard.id)).where(
            SrsCard.learner_id == learner_id,
            SrsCard.released_at.is_not(None),
            SrsCard.released_at >= start,
        )
    )
    return result.scalar_one()


async def _entry_ids_at_learner_level(
    db: AsyncSession, *, learner: Learner, parent_id: int
) -> set[int]:
    """Family-bank dictionary entry IDs at the learner's current CEFR."""
    bank = await get_family_bank(db, parent_id)
    if bank is None:
        return set()

    result = await db.execute(
        select(WordListItem.dictionary_entry_id, WordListItem.level).where(
            WordListItem.word_list_id == bank.id
        )
    )
    return {
        entry_id
        for entry_id, item_level in result.all()
        if level_matches(item_level, learner.english_level)
    }


async def _bank_items_for_learner(
    db: AsyncSession, learner: Learner, parent_id: int
) -> list[WordListItem]:
    bank = await get_family_bank(db, parent_id)
    if bank is None:
        return []

    result = await db.execute(
        select(WordListItem)
        .options(selectinload(WordListItem.dictionary_entry))
        .where(WordListItem.word_list_id == bank.id)
        .order_by(WordListItem.sort_order, WordListItem.id)
    )
    return [
        item for item in result.scalars().all() if level_matches(item.level, learner.english_level)
    ]


async def _ensure_unreleased_card(
    db: AsyncSession,
    *,
    learner_id: int,
    entry_id: int,
    word_list_id: int,
    now: datetime,
) -> SrsCard:
    result = await db.execute(
        select(SrsCard).where(
            SrsCard.learner_id == learner_id,
            SrsCard.dictionary_entry_id == entry_id,
        )
    )
    card = result.scalar_one_or_none()
    if card is None:
        card = SrsCard(
            learner_id=learner_id,
            dictionary_entry_id=entry_id,
            word_list_id=word_list_id,
            ease_factor=DEFAULT_EASE_FACTOR,
            interval_days=0,
            repetitions=0,
            due_at=_far_future(now),
            state="new",
            released_at=None,
        )
        db.add(card)
    elif card.released_at is None:
        card.due_at = _far_future(now)
        card.word_list_id = word_list_id
    return card


async def seed_bank_cards_for_learner(
    db: AsyncSession, *, learner: Learner, parent_id: int, now: datetime | None = None
) -> int:
    """Create unreleased SRS placeholders for all eligible bank words."""
    if now is None:
        now = datetime.now(UTC)
    items = await _bank_items_for_learner(db, learner, parent_id)
    bank = await get_family_bank(db, parent_id)
    if bank is None:
        return 0

    created = 0
    for item in items:
        result = await db.execute(
            select(SrsCard).where(
                SrsCard.learner_id == learner.id,
                SrsCard.dictionary_entry_id == item.dictionary_entry_id,
            )
        )
        if result.scalar_one_or_none() is None:
            await _ensure_unreleased_card(
                db,
                learner_id=learner.id,
                entry_id=item.dictionary_entry_id,
                word_list_id=bank.id,
                now=now,
            )
            created += 1
    return created


async def reconcile_mismatched_bank_cards(
    db: AsyncSession, *, learner: Learner, parent_id: int, now: datetime | None = None
) -> int:
    """Unrelease bank cards that were dripped at the wrong level and never reviewed."""
    if now is None:
        now = datetime.now(UTC)

    bank = await get_family_bank(db, parent_id)
    if bank is None:
        return 0

    items_result = await db.execute(
        select(WordListItem.dictionary_entry_id, WordListItem.level).where(
            WordListItem.word_list_id == bank.id
        )
    )
    level_by_entry = dict(items_result.all())
    if not level_by_entry:
        return 0

    cards_result = await db.execute(
        select(SrsCard).where(
            SrsCard.learner_id == learner.id,
            SrsCard.dictionary_entry_id.in_(level_by_entry.keys()),
            SrsCard.released_at.is_not(None),
        )
    )
    reset = 0
    for card in cards_result.scalars().all():
        item_level = level_by_entry.get(card.dictionary_entry_id)
        if not item_level or level_matches(item_level, learner.english_level):
            continue
        if card.last_reviewed_at is not None:
            continue
        card.released_at = None
        card.due_at = _far_future(now)
        card.state = "new"
        reset += 1

    if reset:
        await db.flush()
    return reset


async def release_new_words(
    db: AsyncSession,
    *,
    learner: Learner,
    parent_id: int,
    now: datetime | None = None,
    daily_cap: int | None = None,
    entry_id_allowlist: set[int] | None = None,
    ignore_daily_cap: bool = False,
    source_word_list_id: int | None = None,
    shuffle_salt: int = 0,
) -> list[SrsCard]:
    if now is None:
        now = datetime.now(UTC)

    goal = (
        daily_cap
        if daily_cap is not None
        else (learner.daily_new_word_goal or default_new_goal(learner))
    )
    if entry_id_allowlist is not None or ignore_daily_cap:
        # Count only filter-matching releases so category/list regen can drip more.
        filtered_today = await list_released_today(db, learner_id=learner.id, now=now)
        if entry_id_allowlist is not None:
            already = sum(
                1 for card in filtered_today if card.dictionary_entry_id in entry_id_allowlist
            )
        else:
            already = len(filtered_today)
    else:
        already = await count_released_today(db, learner.id, now)
    remaining = max(0, goal - already)
    if remaining == 0:
        return []

    bank = await get_family_bank(db, parent_id)
    release_list_id = source_word_list_id or (bank.id if bank else None)
    if release_list_id is None:
        return []

    if source_word_list_id is not None and entry_id_allowlist is not None:
        entry_ids = list(entry_id_allowlist)
    else:
        if bank is None:
            return []
        items_result = await db.execute(
            select(WordListItem).where(WordListItem.word_list_id == bank.id)
        )
        items = [
            item
            for item in items_result.scalars().all()
            if level_matches(item.level, learner.english_level)
        ]
        if entry_id_allowlist is not None:
            items = [item for item in items if item.dictionary_entry_id in entry_id_allowlist]
        if not items:
            return []
        entry_ids = [item.dictionary_entry_id for item in items]

    if not entry_ids:
        return []

    cards_result = await db.execute(
        select(SrsCard).where(
            SrsCard.learner_id == learner.id,
            SrsCard.dictionary_entry_id.in_(entry_ids),
        )
    )
    cards_by_entry = {card.dictionary_entry_id: card for card in cards_result.scalars().all()}

    candidates: list[tuple[int, SrsCard | None]] = []
    for entry_id in entry_ids:
        card = cards_by_entry.get(entry_id)
        if card is None or card.released_at is None:
            candidates.append((entry_id, card))

    rng = random.Random(_daily_shuffle_seed(learner.id, now.date()) ^ shuffle_salt)
    rng.shuffle(candidates)

    released: list[SrsCard] = []
    for entry_id, card in candidates:
        if len(released) >= remaining:
            break
        if card is None:
            card = SrsCard(
                learner_id=learner.id,
                dictionary_entry_id=entry_id,
                word_list_id=release_list_id,
                ease_factor=DEFAULT_EASE_FACTOR,
                interval_days=0,
                repetitions=0,
                due_at=now,
                state="new",
                released_at=now,
            )
            db.add(card)
            released.append(card)
        else:
            card.due_at = now
            card.released_at = now
            card.word_list_id = release_list_id
            released.append(card)

    if released:
        await db.flush()
        released_ids = [card.id for card in released if card.id is not None]
        if released_ids:
            loaded = await db.execute(
                select(SrsCard)
                .options(selectinload(SrsCard.dictionary_entry))
                .where(SrsCard.id.in_(released_ids))
            )
            released = list(loaded.scalars().all())
    return released


async def list_released_today(
    db: AsyncSession, *, learner_id: int, now: datetime | None = None
) -> list[SrsCard]:
    if now is None:
        now = datetime.now(UTC)
    start = _start_of_day(now)
    result = await db.execute(
        select(SrsCard)
        .options(selectinload(SrsCard.dictionary_entry))
        .where(
            SrsCard.learner_id == learner_id,
            SrsCard.released_at.is_not(None),
            SrsCard.released_at >= start,
        )
        .order_by(SrsCard.released_at, SrsCard.id)
    )
    return list(result.scalars().all())


async def pick_retention(
    db: AsyncSession,
    *,
    learner: Learner,
    limit: int | None = None,
    now: datetime | None = None,
    exclude_ids: set[int] | None = None,
    entry_id_allowlist: set[int] | None = None,
    strength_in: set[str] | None = None,
) -> list[SrsCard]:
    if now is None:
        now = datetime.now(UTC)
    max_cards = limit if limit is not None else daily_retention_goal(learner)
    if max_cards <= 0:
        return []

    excluded = exclude_ids or set()
    result = await db.execute(
        select(SrsCard)
        .options(selectinload(SrsCard.dictionary_entry))
        .where(
            SrsCard.learner_id == learner.id,
            SrsCard.released_at.is_not(None),
            SrsCard.due_at <= _as_utc(now),
        )
        .order_by(SrsCard.due_at)
    )
    due_cards = [
        card
        for card in result.scalars().all()
        if card.id not in excluded
        and (entry_id_allowlist is None or card.dictionary_entry_id in entry_id_allowlist)
    ]

    card_ids = [card.id for card in due_cards if card.id is not None]
    distinct_days_map = await distinct_review_days_by_card(db, card_ids)

    def card_strength(card: SrsCard) -> str | None:
        return strength_for_card(card, distinct_days_map)

    if strength_in is not None:
        due_cards = [card for card in due_cards if card_strength(card) in strength_in]

    def retention_priority(card: SrsCard) -> tuple[int, datetime]:
        strength = card_strength(card) or "learning"
        due = _as_utc(card.due_at)
        if strength == "mastered":
            return (0, due)
        if strength == "familiar":
            return (1, due)
        if card.state == "relearning":
            return (2, due)
        return (3, due)

    due_cards.sort(key=retention_priority)
    if len(due_cards) >= max_cards:
        return due_cards[:max_cards]

    # Fill shortfall from older released cards (helps practice-again and day-1 edges).
    picked_ids = {card.id for card in due_cards}
    filler_result = await db.execute(
        select(SrsCard)
        .options(selectinload(SrsCard.dictionary_entry))
        .where(
            SrsCard.learner_id == learner.id,
            SrsCard.released_at.is_not(None),
        )
        .order_by(SrsCard.released_at, SrsCard.id)
    )
    filler_cards = [
        card
        for card in filler_result.scalars().all()
        if card.id not in excluded
        and card.id not in picked_ids
        and (entry_id_allowlist is None or card.dictionary_entry_id in entry_id_allowlist)
    ]
    filler_ids = [card.id for card in filler_cards if card.id is not None]
    filler_days_map = await distinct_review_days_by_card(
        db, [card_id for card_id in filler_ids if card_id not in distinct_days_map]
    )
    distinct_days_map.update(filler_days_map)

    for card in filler_cards:
        if strength_in is not None and card_strength(card) not in strength_in:
            continue
        due_cards.append(card)
        picked_ids.add(card.id)
        if len(due_cards) >= max_cards:
            break
    return due_cards[:max_cards]


def _deck_locked(log: DailyChallengeLog) -> bool:
    """True once either challenge phase is done: the deck stays frozen for the rest of the day."""
    return log.srs_completed_at is not None or log.dictation_completed_at is not None


def _can_regenerate(log: DailyChallengeLog | None) -> bool:
    return log is None or not _deck_locked(log)


async def _entry_ids_for_category(
    db: AsyncSession, *, learner: Learner, parent_id: int, category: str
) -> set[int]:
    from app.services.word_bank_service import format_category_name, item_category_names

    bank = await get_family_bank(db, parent_id)
    if bank is None:
        return set()
    result = await db.execute(
        select(WordListItem)
        .options(selectinload(WordListItem.categories))
        .where(WordListItem.word_list_id == bank.id)
        .order_by(WordListItem.sort_order, WordListItem.id)
    )
    wanted = format_category_name(category).casefold()
    ids: set[int] = set()
    for item in result.scalars().all():
        if not level_matches(item.level, learner.english_level):
            continue
        names = {format_category_name(n).casefold() for n in item_category_names(item)}
        if wanted in names:
            ids.add(item.dictionary_entry_id)
    return ids


async def _entry_ids_for_own_list(
    db: AsyncSession, *, learner: Learner, word_list_id: int
) -> tuple[WordList, set[int]]:
    from app.services import word_list_service

    wl = await word_list_service.get_learner_owned_word_list(db, word_list_id, learner.id)
    result = await db.execute(
        select(WordListItem.dictionary_entry_id).where(WordListItem.word_list_id == wl.id)
    )
    return wl, set(result.scalars().all())


async def challenge_source_options(
    db: AsyncSession, *, learner: Learner, parent_id: int, now: datetime | None = None
) -> dict:
    """Categories at learner level + learner-owned lists for regenerate picker."""
    from app.services import word_list_service
    from app.services.word_bank_service import format_category_name, item_category_names

    if now is None:
        now = datetime.now(UTC)

    bank = await get_family_bank(db, parent_id)
    categories: dict[str, int] = {}
    if bank is not None:
        result = await db.execute(
            select(WordListItem)
            .options(selectinload(WordListItem.categories))
            .where(WordListItem.word_list_id == bank.id)
        )
        for item in result.scalars().all():
            if not level_matches(item.level, learner.english_level):
                continue
            for raw in item_category_names(item):
                name = format_category_name(raw)
                categories[name] = categories.get(name, 0) + 1

    my_lists: list[dict] = []
    for summary in await word_list_service.list_assigned_for_learner(db, learner.id):
        if summary.get("source") != "learner":
            continue
        if summary.get("created_by_learner_id") != learner.id:
            continue
        item_count = int(summary.get("item_count") or 0)
        if item_count <= 0:
            continue
        my_lists.append({"id": summary["id"], "name": summary["name"], "item_count": item_count})

    log = await get_today_challenge_log(db, learner_id=learner.id, now=now)
    return {
        "english_level": learner.english_level,
        "categories": [
            {"name": name, "word_count": count}
            for name, count in sorted(categories.items(), key=lambda x: x[0].casefold())
        ],
        "my_lists": my_lists,
        "can_regenerate": _can_regenerate(log),
        "source_kind": (log.source_kind if log else None) or "random",
        "source_ref": log.source_ref if log else None,
    }


async def regenerate_daily_mix(
    db: AsyncSession,
    *,
    learner: Learner,
    parent_id: int,
    mode: str,
    category: str | None = None,
    word_list_id: int | None = None,
    now: datetime | None = None,
) -> dict:
    """Rebuild today's challenge before completion. Resets mid-session progress."""
    if now is None:
        now = datetime.now(UTC)
    today = now.date()
    learner_id = learner.id  # cache scalar — session objects get expired on rollback

    log_result = await db.execute(
        select(DailyChallengeLog).where(
            DailyChallengeLog.learner_id == learner_id,
            DailyChallengeLog.challenge_date == today,
        )
    )
    log = log_result.scalar_one_or_none()
    if log is not None and _deck_locked(log):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Today's challenge mix is locked. Finish both steps or use Practice again.",
        )

    mode_norm = (mode or "random").strip().lower()
    if mode_norm not in {"random", "category", "list"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid regenerate mode",
        )

    entry_allowlist: set[int] | None = None
    source_kind = "random"
    source_ref: str | None = None
    source_list_id: int | None = None

    if mode_norm == "category":
        if not category or not category.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="category is required",
            )
        entry_allowlist = await _entry_ids_for_category(
            db, learner=learner, parent_id=parent_id, category=category.strip()
        )
        if not entry_allowlist:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No words in category '{category}' at your level",
            )
        source_kind = "category"
        source_ref = category.strip()
    elif mode_norm == "list":
        if word_list_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="word_list_id is required"
            )
        wl, entry_allowlist = await _entry_ids_for_own_list(
            db, learner=learner, word_list_id=word_list_id
        )
        if not entry_allowlist:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="That word list is empty"
            )
        source_kind = "list"
        source_ref = str(wl.id)
        source_list_id = wl.id

    if log is None:
        log = DailyChallengeLog(
            learner_id=learner.id,
            challenge_date=today,
            new_count=0,
            retention_count=0,
            card_ids_json=None,
            source_kind=source_kind,
            source_ref=source_ref,
        )
        db.add(log)
    else:
        log.srs_completed_at = None
        log.dictation_completed_at = None
        log.card_ids_json = None
        log.new_count = 0
        log.retention_count = 0
        log.learning_retention_count = 0
        log.mastered_retention_count = 0
        log.source_kind = source_kind
        log.source_ref = source_ref
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent request created today's log first — reload and reuse it.
        await db.rollback()
        log_result = await db.execute(
            select(DailyChallengeLog).where(
                DailyChallengeLog.learner_id == learner_id,
                DailyChallengeLog.challenge_date == today,
            )
        )
        log = log_result.scalar_one()

    shuffle_salt = int(now.timestamp())
    return await build_daily_mix(
        db,
        learner=learner,
        parent_id=parent_id,
        now=now,
        force_rebuild=True,
        entry_id_allowlist=entry_allowlist,
        source_word_list_id=source_list_id,
        shuffle_salt=shuffle_salt,
        ignore_daily_cap=True,
        source_kind=source_kind,
        source_ref=source_ref,
    )


async def build_daily_mix(
    db: AsyncSession,
    *,
    learner: Learner,
    parent_id: int,
    now: datetime | None = None,
    force_rebuild: bool = False,
    entry_id_allowlist: set[int] | None = None,
    source_word_list_id: int | None = None,
    shuffle_salt: int = 0,
    ignore_daily_cap: bool = False,
    source_kind: str | None = None,
    source_ref: str | None = None,
    retention_entry_id_allowlist: object = _UNSET,
) -> dict:
    if now is None:
        now = datetime.now(UTC)

    await reconcile_mismatched_bank_cards(db, learner=learner, parent_id=parent_id, now=now)

    auto_book = False
    if entry_id_allowlist is None and source_word_list_id is None:
        from app.services import book_service

        active_book = await book_service.get_active_book_for_learner(db, learner.id)
        if active_book is not None and active_book.word_list_id is not None:
            study_ids = await book_service.study_entry_ids(db, active_book)
            if study_ids:
                auto_book = True
                entry_id_allowlist = study_ids
                source_word_list_id = active_book.word_list_id
                source_kind = source_kind or "book"
                source_ref = source_ref or str(active_book.word_list_id)
                if retention_entry_id_allowlist is _UNSET:
                    retention_entry_id_allowlist = None

    drip_allowlist = entry_id_allowlist
    if retention_entry_id_allowlist is _UNSET:
        retention_allowlist: set[int] | None = entry_id_allowlist
    else:
        retention_allowlist = retention_entry_id_allowlist  # type: ignore[assignment]

    learner_id = learner.id  # cache scalar — session objects get expired on rollback
    new_goal = learner.daily_new_word_goal or default_new_goal(learner)
    learning_retention_goal = daily_learning_retention_goal(learner)
    mastered_retention_goal = daily_mastered_retention_goal(learner)
    retention_goal = learning_retention_goal + mastered_retention_goal

    challenge_date = now.date()
    log_result = await db.execute(
        select(DailyChallengeLog).where(
            DailyChallengeLog.learner_id == learner_id,
            DailyChallengeLog.challenge_date == challenge_date,
        )
    )
    log = log_result.scalar_one_or_none()
    existing_ids = _card_ids_from_log(log) if log else []

    # Challenge target is always new_goal + retention_goal when the bank allows.
    # Retention comes from due/older cards first; shortfall is filled by extra drip.
    challenge_cap = new_goal + retention_goal
    await release_new_words(
        db,
        learner=learner,
        parent_id=parent_id,
        now=now,
        daily_cap=challenge_cap,
        entry_id_allowlist=drip_allowlist,
        ignore_daily_cap=ignore_daily_cap,
        source_word_list_id=source_word_list_id,
        shuffle_salt=shuffle_salt,
    )
    released_today = await list_released_today(db, learner_id=learner.id, now=now)
    if drip_allowlist is not None:
        released_today = [
            card for card in released_today if card.dictionary_entry_id in drip_allowlist
        ]
    if auto_book or source_kind == "book":
        from app.services import dictionary_service as dictionary_svc

        await dictionary_svc.prefetch_challenge_definitions(
            db,
            [card.dictionary_entry for card in released_today if card.dictionary_entry is not None],
        )
    released_today_ids = {card.id for card in released_today if card.id is not None}

    freeze = (
        log is not None
        and _deck_locked(log)
        and not force_rebuild
        and (drip_allowlist is None or auto_book)
    )
    learning_retention_count = 0
    mastered_retention_count = 0
    if freeze:
        # Deck is locked for the rest of the day so bonus dictation and
        # practice-again replay the exact words the learner reviewed.
        card_ids = existing_ids
        new_count = min(new_goal, sum(1 for card_id in card_ids if card_id in released_today_ids))
        retention_count = max(0, len(card_ids) - new_count)
        learning_retention_count = getattr(log, "learning_retention_count", None) or 0
        mastered_retention_count = getattr(log, "mastered_retention_count", None) or 0
        if learning_retention_count + mastered_retention_count == 0 and retention_count > 0:
            learning_retention_count = retention_count
    else:
        # Before SRS completion or on explicit regenerate: rebuild full mix.
        learning_retention_cards = await pick_retention(
            db,
            learner=learner,
            limit=learning_retention_goal,
            now=now,
            exclude_ids=set(),
            entry_id_allowlist=retention_allowlist,
            strength_in={"learning", "familiar"},
        )
        learning_picked_ids = {card.id for card in learning_retention_cards if card.id is not None}
        current_level_ids = await _entry_ids_at_learner_level(
            db, learner=learner, parent_id=parent_id
        )
        mastered_allowlist = current_level_ids
        if retention_allowlist is not None:
            mastered_allowlist = retention_allowlist & current_level_ids
        mastered_retention_cards = await pick_retention(
            db,
            learner=learner,
            limit=mastered_retention_goal,
            now=now,
            exclude_ids=learning_picked_ids,
            entry_id_allowlist=mastered_allowlist,
            strength_in={"mastered"},
        )
        # Prefer retention that is NOT part of today's freshest new drip when possible.
        ordered_today = [card.id for card in released_today if card.id is not None]
        newest_new = set(ordered_today[:new_goal])
        learning_retention_ids = [
            card.id
            for card in learning_retention_cards
            if card.id is not None and card.id not in newest_new
        ]
        mastered_retention_ids = [
            card.id
            for card in mastered_retention_cards
            if card.id is not None and card.id not in newest_new
        ]
        retention_ids = learning_retention_ids + mastered_retention_ids
        # Keep prior retention picks from an earlier lock when still valid (unfiltered only).
        if retention_allowlist is None and not force_rebuild:
            for card_id in existing_ids:
                if card_id in newest_new or card_id in retention_ids:
                    continue
                retention_ids.append(card_id)
                if len(retention_ids) >= retention_goal:
                    break
        learning_retention_ids = list(dict.fromkeys(learning_retention_ids))[
            :learning_retention_goal
        ]
        mastered_retention_ids = list(dict.fromkeys(mastered_retention_ids))[
            :mastered_retention_goal
        ]
        retention_ids = learning_retention_ids + mastered_retention_ids

        new_ids = [card_id for card_id in ordered_today if card_id not in retention_ids][:new_goal]
        # If retention pool was empty, use extra dripped cards as retention stand-ins.
        if len(retention_ids) < retention_goal:
            stand_ins = [
                card_id
                for card_id in ordered_today
                if card_id not in new_ids and card_id not in retention_ids
            ][: retention_goal - len(retention_ids)]
            retention_ids = retention_ids + stand_ins
            learning_retention_ids = retention_ids[:learning_retention_goal]
            mastered_retention_ids = retention_ids[learning_retention_goal:]

        card_ids = retention_ids + new_ids
        # Shuffle so review/dictation feel like a real mixed deck, not retention-then-new.
        # Seed is stable for the day; regenerate gets a fresh order via shuffle_salt.
        shuffle_seed = _daily_shuffle_seed(learner.id, challenge_date) ^ shuffle_salt
        random.Random(shuffle_seed).shuffle(card_ids)
        learning_retention_count = len(learning_retention_ids)
        mastered_retention_count = len(mastered_retention_ids)
        retention_count = learning_retention_count + mastered_retention_count
        new_count = len(new_ids)

        if log is None:
            log = DailyChallengeLog(
                learner_id=learner.id,
                challenge_date=challenge_date,
                new_count=new_count,
                retention_count=retention_count,
                learning_retention_count=learning_retention_count,
                mastered_retention_count=mastered_retention_count,
                card_ids_json=json.dumps(card_ids),
                source_kind=source_kind or "random",
                source_ref=source_ref,
            )
            db.add(log)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                log_result = await db.execute(
                    select(DailyChallengeLog).where(
                        DailyChallengeLog.learner_id == learner_id,
                        DailyChallengeLog.challenge_date == challenge_date,
                    )
                )
                log = log_result.scalar_one()
                if not _deck_locked(log) or force_rebuild:
                    log.new_count = new_count
                    log.retention_count = retention_count
                    log.learning_retention_count = learning_retention_count
                    log.mastered_retention_count = mastered_retention_count
                    log.card_ids_json = json.dumps(card_ids)
                    if source_kind is not None:
                        log.source_kind = source_kind
                        log.source_ref = source_ref
                    await db.commit()
                else:
                    card_ids = _card_ids_from_log(log)
                    new_count = min(
                        new_goal,
                        sum(1 for card_id in card_ids if card_id in released_today_ids),
                    )
                    retention_count = max(0, len(card_ids) - new_count)
                    learning_retention_count = log.learning_retention_count or 0
                    mastered_retention_count = log.mastered_retention_count or 0
        else:
            log.new_count = new_count
            log.retention_count = retention_count
            log.learning_retention_count = learning_retention_count
            log.mastered_retention_count = mastered_retention_count
            log.card_ids_json = json.dumps(card_ids)
            if source_kind is not None:
                log.source_kind = source_kind
                log.source_ref = source_ref
            elif log.source_kind is None:
                log.source_kind = "random"
            await db.commit()

    cards: list[SrsCard] = []
    if card_ids:
        loaded = await db.execute(
            select(SrsCard)
            .options(selectinload(SrsCard.dictionary_entry))
            .where(SrsCard.id.in_(card_ids))
        )
        cards_by_id = {card.id: card for card in loaded.scalars().all()}
        cards = [cards_by_id[card_id] for card_id in card_ids if card_id in cards_by_id]

    await srs_service.enrich_cards_zh_hant(db, cards)
    mix = {
        "cards": [srs_service.card_to_dict(card) for card in cards],
        "new_count": new_count,
        "retention_count": retention_count,
        "learning_retention_count": learning_retention_count,
        "mastered_retention_count": mastered_retention_count,
        "daily_new_goal": new_goal,
        "daily_learning_retention_goal": learning_retention_goal,
        "daily_mastered_retention_goal": mastered_retention_goal,
        "daily_retention_goal": retention_goal,
        "new_released_today": len(released_today),
        "completed_today": log.completed_at is not None,
        "srs_completed": log.srs_completed_at is not None,
        "dictation_completed": log.dictation_completed_at is not None,
        "suggested": True,
        "source_kind": log.source_kind or "random",
        "source_ref": log.source_ref,
        "can_regenerate": _can_regenerate(log),
        "book_title": None,
        "study_progress_percent": None,
        "page_coverage_percent": None,
        "ready_to_read": None,
    }
    if auto_book or (log.source_kind == "book"):
        from app.services import book_service

        active = await book_service.get_active_book_for_learner(db, learner.id)
        if active is not None:
            progress = await book_service.progress_for_learner(db, active, learner.id)
            mix["book_title"] = active.title
            mix["study_progress_percent"] = progress["study_progress_percent"]
            mix["page_coverage_percent"] = progress["page_coverage_percent"]
            mix["ready_to_read"] = progress["ready_to_read"]
    return mix


def _card_ids_from_log(log: DailyChallengeLog) -> list[int]:
    if not log.card_ids_json:
        return []
    try:
        raw = json.loads(log.card_ids_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    return [int(item) for item in raw if isinstance(item, int) or str(item).isdigit()]


async def get_today_challenge_log(
    db: AsyncSession, *, learner_id: int, now: datetime | None = None
) -> DailyChallengeLog | None:
    if now is None:
        now = datetime.now(UTC)
    result = await db.execute(
        select(DailyChallengeLog).where(
            DailyChallengeLog.learner_id == learner_id,
            DailyChallengeLog.challenge_date == now.date(),
        )
    )
    return result.scalar_one_or_none()


async def get_today_mix_cards(
    db: AsyncSession, *, learner: Learner, parent_id: int, now: datetime | None = None
) -> dict:
    """Return today's challenge mix cards (builds mix if needed)."""
    if now is None:
        now = datetime.now(UTC)
    mix = await build_daily_mix(db, learner=learner, parent_id=parent_id, now=now)
    log = await get_today_challenge_log(db, learner_id=learner.id, now=now)
    card_ids = _card_ids_from_log(log) if log else []
    cards = mix["cards"]
    if card_ids:
        loaded = await db.execute(
            select(SrsCard)
            .options(selectinload(SrsCard.dictionary_entry))
            .where(SrsCard.id.in_(card_ids))
        )
        cards_by_id = {card.id: card for card in loaded.scalars().all()}
        ordered = [cards_by_id[card_id] for card_id in card_ids if card_id in cards_by_id]
        await srs_service.enrich_cards_zh_hant(db, ordered)
        cards = [srs_service.card_to_dict(card) for card in ordered]
    return {
        "cards": cards,
        "due_count": len(cards),
        "daily_goal": (
            mix["daily_new_goal"]
            + mix["daily_learning_retention_goal"]
            + mix["daily_mastered_retention_goal"]
        ),
        "srs_completed": mix.get("srs_completed", False),
        "dictation_completed": mix.get("dictation_completed", False),
        "completed_today": mix["completed_today"],
    }


async def get_today_mix_entry_ids(
    db: AsyncSession, *, learner_id: int, now: datetime | None = None
) -> list[int]:
    log = await get_today_challenge_log(db, learner_id=learner_id, now=now)
    if log is None:
        return []
    card_ids = _card_ids_from_log(log)
    if not card_ids:
        return []
    result = await db.execute(
        select(SrsCard.id, SrsCard.dictionary_entry_id).where(SrsCard.id.in_(card_ids))
    )
    entry_by_card = {card_id: entry_id for card_id, entry_id in result.all()}
    return [entry_by_card[card_id] for card_id in card_ids if card_id in entry_by_card]


async def mark_srs_phase_complete(
    db: AsyncSession, *, learner_id: int, now: datetime | None = None
) -> dict:
    if now is None:
        now = datetime.now(UTC)
    log = await get_today_challenge_log(db, learner_id=learner_id, now=now)
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NO_CHALLENGE",
                "message": "Open Home to start today's challenge first",
            },
        )
    if log.srs_completed_at is not None:
        return {
            "srs_completed": True,
            "dictation_completed": log.dictation_completed_at is not None,
            "completed": log.completed_at is not None,
            "completed_at": log.completed_at,
        }

    card_ids = _card_ids_from_log(log)
    if not card_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMPTY_MIX", "message": "No challenge words to review today"},
        )

    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Latest review today per mix card — earlier correct + later wrong must not pass.
    latest_rows = (
        await db.execute(
            select(SrsReviewLog.srs_card_id, SrsReviewLog.quality, SrsReviewLog.reviewed_at)
            .where(
                SrsReviewLog.learner_id == learner_id,
                SrsReviewLog.srs_card_id.in_(card_ids),
                SrsReviewLog.reviewed_at >= start_of_day,
            )
            .order_by(SrsReviewLog.reviewed_at.desc(), SrsReviewLog.id.desc())
        )
    ).all()
    latest_quality: dict[int, int] = {}
    for card_id, quality, _reviewed_at in latest_rows:
        if card_id not in latest_quality:
            latest_quality[card_id] = int(quality)

    missing = [card_id for card_id in card_ids if card_id not in latest_quality]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "SRS_INCOMPLETE",
                "message": f"Review all challenge words first ({len(missing)} remaining)",
            },
        )

    correct_count = sum(
        1 for card_id in card_ids if latest_quality[card_id] >= CORRECT_QUALITY_THRESHOLD
    )
    accuracy = correct_count / len(card_ids)
    if accuracy < SOFT_DAILY_PASS_THRESHOLD:
        needed = int(SOFT_DAILY_PASS_THRESHOLD * 100)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "SRS_ACCURACY_BELOW",
                "message": (
                    f"Need at least {needed}% correct "
                    f"({correct_count}/{len(card_ids)}) — keep practicing"
                ),
            },
        )

    log.srs_completed_at = now
    _maybe_finalize_challenge(log, now=now)
    await db.commit()
    return {
        "srs_completed": True,
        "dictation_completed": log.dictation_completed_at is not None,
        "completed": log.completed_at is not None,
        "completed_at": log.completed_at,
    }


async def mark_dictation_phase_complete(
    db: AsyncSession, *, learner_id: int, now: datetime | None = None
) -> dict:
    if now is None:
        now = datetime.now(UTC)
    log = await get_today_challenge_log(db, learner_id=learner_id, now=now)
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NO_CHALLENGE",
                "message": "Open Home to start today's challenge first",
            },
        )
    if log.dictation_completed_at is None:
        log.dictation_completed_at = now
    _maybe_finalize_challenge(log, now=now)
    await db.commit()
    return {
        "srs_completed": log.srs_completed_at is not None,
        "dictation_completed": True,
        "completed": log.completed_at is not None,
        "completed_at": log.completed_at,
    }


def _maybe_finalize_challenge(log: DailyChallengeLog, *, now: datetime) -> None:
    # Day completes only after SRS recognition (≥80%) and Listen & Pick.
    if (
        log.srs_completed_at is not None
        and log.dictation_completed_at is not None
        and log.completed_at is None
    ):
        log.completed_at = now


async def complete_daily_challenge(
    db: AsyncSession, *, learner_id: int, now: datetime | None = None
) -> dict:
    """Finalize once SRS recognition and Listen & Pick are both done."""
    if now is None:
        now = datetime.now(UTC)
    log = await get_today_challenge_log(db, learner_id=learner_id, now=now)
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NO_CHALLENGE",
                "message": "Finish today's challenge review first",
            },
        )
    if log.completed_at is not None:
        return {"completed": True, "completed_at": log.completed_at}

    if log.srs_completed_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "CHALLENGE_INCOMPLETE",
                "message": "Review all of today's challenge words first",
            },
        )
    if log.dictation_completed_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "CHALLENGE_INCOMPLETE",
                "message": "Finish Listen & Pick first",
            },
        )

    log.completed_at = now
    await db.commit()
    return {"completed": True, "completed_at": log.completed_at}


async def progress_summary(
    db: AsyncSession, *, learner_id: int, now: datetime | None = None
) -> dict:
    if now is None:
        now = datetime.now(UTC)

    result = await db.execute(select(SrsCard).where(SrsCard.learner_id == learner_id))
    cards = result.scalars().all()
    released_cards = [card for card in cards if card.released_at is not None]

    due_count = 0
    for card in released_cards:
        if _as_utc(card.due_at) <= _as_utc(now):
            due_count += 1

    learner_result = await db.execute(select(Learner).where(Learner.id == learner_id))
    learner = learner_result.scalar_one()
    new_goal = learner.daily_new_word_goal or default_new_goal(learner)
    released_today = await count_released_today(db, learner_id, now)
    week_start = (now.date() - timedelta(days=now.weekday())).isoformat()
    week_start_dt = datetime.fromisoformat(week_start).replace(tzinfo=UTC)
    released_week_result = await db.execute(
        select(func.count(SrsCard.id)).where(
            SrsCard.learner_id == learner_id,
            SrsCard.released_at.is_not(None),
            SrsCard.released_at >= week_start_dt,
        )
    )
    new_released_this_week = released_week_result.scalar_one()

    bank_total = 0
    bank_at_level = 0
    learning = familiar = mastered = 0
    user_result = await db.execute(select(User).where(User.id == learner.user_id))
    user = user_result.scalar_one()
    if user.parent_id:
        level_counts = await strength_counts_for_level(
            db,
            learner_id=learner_id,
            parent_id=user.parent_id,
            level=learner.english_level,
        )
        learning = level_counts["learning"]
        familiar = level_counts["familiar"]
        mastered = level_counts["mastered"]
        bank_at_level = level_counts["bank_total"]

        bank = await get_family_bank(db, user.parent_id)
        if bank:
            total_result = await db.execute(
                select(func.count(WordListItem.id)).where(WordListItem.word_list_id == bank.id)
            )
            bank_total = total_result.scalar_one()

    challenge_log = await get_today_challenge_log(db, learner_id=learner_id, now=now)

    return {
        "learning_count": learning,
        "familiar_count": familiar,
        "mastered_count": mastered,
        "due_count": due_count,
        "new_released_today": released_today,
        "daily_new_goal": new_goal,
        "new_remaining_today": max(0, new_goal - released_today),
        "new_released_this_week": new_released_this_week,
        "weekly_new_target": new_goal * 5,
        "bank_total": bank_total,
        "bank_at_level": bank_at_level,
        "daily_challenge_completed": challenge_log is not None
        and challenge_log.completed_at is not None,
        "daily_challenge_srs_completed": challenge_log is not None
        and challenge_log.srs_completed_at is not None,
        "daily_challenge_dictation_completed": challenge_log is not None
        and challenge_log.dictation_completed_at is not None,
    }


async def get_learner_parent_id(db: AsyncSession, learner: Learner) -> int | None:
    result = await db.execute(select(User.parent_id).where(User.id == learner.user_id))
    return result.scalar_one_or_none()


VALID_STRENGTH_FILTERS = frozenset({"learning", "familiar", "mastered"})


async def list_learner_words(
    db: AsyncSession,
    *,
    learner: Learner,
    parent_id: int | None,
    query: str | None = None,
    level: str | None = None,
    category: str | None = None,
    strength: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """List released words for a learner with Word Bank–style filters + strength."""
    # Local import avoids circular dependency with word_bank_service.
    from app.services.word_bank_service import format_category_name, item_category_names

    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    strength_filter = (strength or "").strip().lower() or None
    if strength_filter and strength_filter not in VALID_STRENGTH_FILTERS:
        strength_filter = None

    cards_result = await db.execute(
        select(SrsCard)
        .options(selectinload(SrsCard.dictionary_entry))
        .where(SrsCard.learner_id == learner.id, SrsCard.released_at.is_not(None))
        .order_by(SrsCard.id)
    )
    cards = list(cards_result.scalars().all())
    if not cards:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "by_level": {},
            "by_category": {},
            "by_strength": {"learning": 0, "familiar": 0, "mastered": 0},
        }

    entry_ids = [card.dictionary_entry_id for card in cards]
    bank_items_by_entry: dict[int, WordListItem] = {}
    if parent_id is not None:
        bank = await get_family_bank(db, parent_id)
        if bank is not None:
            items_result = await db.execute(
                select(WordListItem)
                .options(selectinload(WordListItem.categories))
                .where(
                    WordListItem.word_list_id == bank.id,
                    WordListItem.dictionary_entry_id.in_(entry_ids),
                )
            )
            for item in items_result.scalars().all():
                bank_items_by_entry[item.dictionary_entry_id] = item

    distinct_days_map = await distinct_review_days_by_card(
        db, [card.id for card in cards if card.id]
    )

    rows: list[dict] = []
    for card in cards:
        entry = card.dictionary_entry
        if entry is None:
            continue
        item = bank_items_by_entry.get(card.dictionary_entry_id)
        categories = item_category_names(item) if item is not None else []
        item_level = item.level if item is not None else None
        card_strength = strength_for_card(card, distinct_days_map) or "new"
        released = card.released_at
        rows.append(
            {
                "card_id": card.id,
                "word": entry.word,
                "definition": entry.definition,
                "level": item_level,
                "categories": categories,
                "strength": card_strength,
                "distinct_review_days": distinct_days_map.get(card.id, 0) if card.id else 0,
                "released_at": released.isoformat() if released is not None else None,
                "interval_days": card.interval_days,
                "repetitions": card.repetitions,
                "state": card.state,
            }
        )

    by_level: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_strength = {"learning": 0, "familiar": 0, "mastered": 0, "new": 0}
    for row in rows:
        lvl = row["level"] or "unknown"
        by_level[lvl] = by_level.get(lvl, 0) + 1
        strength_key = row["strength"]
        if strength_key in by_strength:
            by_strength[strength_key] = by_strength.get(strength_key, 0) + 1
        if row["categories"]:
            for cat in row["categories"]:
                by_category[cat] = by_category.get(cat, 0) + 1
        else:
            by_category["General"] = by_category.get("General", 0) + 1

    filtered = rows
    if query and query.strip():
        term = query.strip().lower()
        filtered = [
            row
            for row in filtered
            if term in row["word"].lower() or term in (row["definition"] or "").lower()
        ]
    if level and level.strip():
        level_key = level.strip().lower()
        filtered = [row for row in filtered if (row["level"] or "").lower() == level_key]
    if category and category.strip():
        category_name = format_category_name(category.strip()).lower()
        filtered = [
            row
            for row in filtered
            if any(cat.lower() == category_name for cat in row["categories"])
            or (not row["categories"] and category_name == "general")
        ]
    if strength_filter:
        filtered = [row for row in filtered if row["strength"] == strength_filter]

    filtered.sort(key=lambda row: (row["word"].lower(), row["card_id"]))
    total = len(filtered)
    total_pages = (total + page_size - 1) // page_size if total else 0
    offset = (page - 1) * page_size
    page_items = filtered[offset : offset + page_size]

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "by_level": by_level,
        "by_category": by_category,
        "by_strength": by_strength,
    }
