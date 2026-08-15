"""Theme pack quests and CEFR milestone badges."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cefr import CEFR_LEVELS
from app.models.challenge import LearnerBadge
from app.models.learner import Learner
from app.models.srs import SrsCard
from app.models.word_list import WordListItem, WordListItemCategory
from app.services import loop_engine, readiness_service

PACK_COMPLETE_RATIO = 0.8
PACK_MIN_WORDS = 3
THEME_PACK_LEVEL_FILTERS: tuple[str, ...] = ("Overall", *CEFR_LEVELS)

PACK_META: list[dict[str, str]] = [
    {"category": "Daily life", "slug": "daily_life", "emoji": "🏠", "title": "Daily life quest"},
    {"category": "School", "slug": "school", "emoji": "🏫", "title": "School hero"},
    {"category": "Food", "slug": "food", "emoji": "🍎", "title": "Food explorer"},
    {
        "category": "Animals / nature",
        "slug": "animals_nature",
        "emoji": "🦊",
        "title": "Zoo & nature",
    },
    {"category": "Science", "slug": "science", "emoji": "🔬", "title": "Mini scientist"},
    {
        "category": "Feelings / people",
        "slug": "feelings_people",
        "emoji": "💛",
        "title": "Feelings & friends",
    },
    {
        "category": "Places / travel",
        "slug": "places_travel",
        "emoji": "✈️",
        "title": "Adventure map",
    },
    {"category": "General", "slug": "general", "emoji": "⭐", "title": "Word collector"},
]

MILESTONE_TIERS = ("explorer", "captain", "champion")

MILESTONE_LABELS = {
    "explorer": "Explorer",
    "captain": "Captain",
    "champion": "Champion",
}


def _pack_meta_for_category(category: str) -> dict[str, str]:
    for pack in PACK_META:
        if pack["category"].lower() == category.lower():
            return pack
    slug = re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")
    return {
        "category": category,
        "slug": slug,
        "emoji": "📚",
        "title": f"{category} quest",
    }


async def _bank_categories(db: AsyncSession, bank_id: int) -> list[str]:
    result = await db.execute(
        select(WordListItemCategory.category)
        .join(WordListItem, WordListItemCategory.word_list_item_id == WordListItem.id)
        .where(WordListItem.word_list_id == bank_id)
        .distinct()
        .order_by(WordListItemCategory.category)
    )
    return [category for (category,) in result.all() if category]


def milestone_thresholds(learner: Learner) -> dict[str, int]:
    if learner.ui_mode == "kid":
        return {"explorer": 10, "captain": 25, "champion": 50}
    return {"explorer": 25, "captain": 50, "champion": 100}


def pack_badge_type(slug: str) -> str:
    return f"pack_{slug}"


def milestone_badge_type(level: str, tier: str) -> str:
    return f"{level.lower()}_{tier}"


async def _existing_badge_types(db: AsyncSession, learner_id: int) -> set[str]:
    result = await db.execute(
        select(LearnerBadge.badge_type).where(LearnerBadge.learner_id == learner_id)
    )
    return set(result.scalars().all())


async def _award_badge(db: AsyncSession, *, learner_id: int, badge_type: str) -> bool:
    existing = await db.execute(
        select(LearnerBadge.id).where(
            LearnerBadge.learner_id == learner_id,
            LearnerBadge.badge_type == badge_type,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return False
    db.add(LearnerBadge(learner_id=learner_id, badge_type=badge_type))
    return True


def _milestones_for_level(
    *,
    level: str,
    counts: dict[str, int],
    thresholds: dict[str, int],
    existing: set[str],
) -> list[dict]:
    milestones = []
    for tier in MILESTONE_TIERS:
        badge_type = milestone_badge_type(level, tier)
        if tier == "explorer":
            current = counts["released"]
        elif tier == "captain":
            current = counts["familiar"] + counts["mastered"]
        else:
            current = counts["mastered"]
        target = thresholds[tier]
        milestones.append(
            {
                "tier": tier,
                "label": f"{level} {MILESTONE_LABELS[tier]}",
                "badge_type": badge_type,
                "current": current,
                "target": target,
                "earned": badge_type in existing,
                "progress_percent": min(100, round((current / target) * 100, 1)) if target else 0,
            }
        )
    return milestones


async def _pack_progress_for_category(
    db: AsyncSession,
    *,
    learner: Learner,
    parent_id: int,
    category: str,
    level: str | None = None,
) -> dict:
    bank = await loop_engine.get_family_bank(db, parent_id)
    if bank is None:
        return {
            "total_words": 0,
            "started_words": 0,
            "strong_words": 0,
            "progress_percent": 0,
            "completed": False,
        }

    items_result = await db.execute(
        select(WordListItem.dictionary_entry_id, WordListItem.level)
        .join(
            WordListItemCategory,
            WordListItemCategory.word_list_item_id == WordListItem.id,
        )
        .where(
            WordListItem.word_list_id == bank.id,
            WordListItemCategory.category == category,
        )
        .distinct()
    )
    entry_ids = [
        entry_id
        for entry_id, item_level in items_result.all()
        if level is None or loop_engine.level_matches(item_level, level)
    ]
    total = len(entry_ids)
    if total == 0:
        return {
            "total_words": 0,
            "started_words": 0,
            "strong_words": 0,
            "progress_percent": 0,
            "completed": False,
        }

    cards_result = await db.execute(
        select(SrsCard).where(
            SrsCard.learner_id == learner.id,
            SrsCard.dictionary_entry_id.in_(entry_ids),
            SrsCard.released_at.is_not(None),
        )
    )
    cards = list(cards_result.scalars().all())
    started = len(cards)
    distinct_days_map = await loop_engine.distinct_review_days_by_card(
        db, [card.id for card in cards]
    )
    strong = sum(
        1
        for card in cards
        if loop_engine.strength_for_card(card, distinct_days_map) in ("familiar", "mastered")
    )
    progress_percent = round((strong / total) * 100, 1) if total else 0.0
    completed = total >= PACK_MIN_WORDS and strong / total >= PACK_COMPLETE_RATIO

    return {
        "total_words": total,
        "started_words": started,
        "strong_words": strong,
        "progress_percent": progress_percent,
        "completed": completed,
    }


async def sync_achievements(
    db: AsyncSession, *, learner: Learner, parent_id: int | None
) -> list[str]:
    """Award new pack/milestone badges. Returns badge types newly earned."""
    if parent_id is None:
        return []

    newly_earned: list[str] = []

    bank = await loop_engine.get_family_bank(db, parent_id)
    categories = await _bank_categories(db, bank.id) if bank is not None else []

    for category in categories:
        pack = _pack_meta_for_category(category)
        progress = await _pack_progress_for_category(
            db, learner=learner, parent_id=parent_id, category=category
        )
        if progress["completed"]:
            badge_type = pack_badge_type(pack["slug"])
            if await _award_badge(db, learner_id=learner.id, badge_type=badge_type):
                newly_earned.append(badge_type)

    thresholds = milestone_thresholds(learner)
    bank_levels = await loop_engine.bank_level_labels(db, parent_id)
    for level in bank_levels:
        counts = await loop_engine.strength_counts_for_level(
            db, learner_id=learner.id, parent_id=parent_id, level=level
        )
        tier_checks = [
            ("explorer", counts["released"] >= thresholds["explorer"]),
            ("captain", (counts["familiar"] + counts["mastered"]) >= thresholds["captain"]),
            ("champion", counts["mastered"] >= thresholds["champion"]),
        ]
        for tier, earned in tier_checks:
            if not earned:
                continue
            badge_type = milestone_badge_type(level, tier)
            if await _award_badge(db, learner_id=learner.id, badge_type=badge_type):
                newly_earned.append(badge_type)

    if newly_earned:
        await db.commit()
    return newly_earned


async def _theme_packs_for_level(
    db: AsyncSession,
    *,
    learner: Learner,
    parent_id: int,
    level_filter: str,
) -> list[dict]:
    bank = await loop_engine.get_family_bank(db, parent_id)
    if bank is None:
        return []

    level = None if level_filter == "Overall" else level_filter
    categories = await _bank_categories(db, bank.id)
    packs: list[dict] = []
    for category in categories:
        pack = _pack_meta_for_category(category)
        progress = await _pack_progress_for_category(
            db,
            learner=learner,
            parent_id=parent_id,
            category=category,
            level=level,
        )
        packs.append(
            {
                "slug": pack["slug"],
                "category": pack["category"],
                "emoji": pack["emoji"],
                "title": pack["title"],
                "badge_type": pack_badge_type(pack["slug"]),
                **progress,
            }
        )
    return packs


async def get_quests_summary(db: AsyncSession, *, learner: Learner, parent_id: int | None) -> dict:
    packs: list[dict] = []
    packs_by_level: dict[str, list[dict]] = {}
    if parent_id is not None:
        packs = await _theme_packs_for_level(
            db, learner=learner, parent_id=parent_id, level_filter="Overall"
        )
        for level_filter in THEME_PACK_LEVEL_FILTERS:
            packs_by_level[level_filter] = await _theme_packs_for_level(
                db, learner=learner, parent_id=parent_id, level_filter=level_filter
            )

    current_level = learner.english_level.strip()
    thresholds = milestone_thresholds(learner)
    existing = await _existing_badge_types(db, learner.id)

    overall = await loop_engine.strength_counts_overall(
        db, learner_id=learner.id, parent_id=parent_id
    )

    levels: list[dict] = []
    if parent_id is not None:
        for level in await loop_engine.bank_level_labels(db, parent_id):
            counts = await loop_engine.strength_counts_for_level(
                db, learner_id=learner.id, parent_id=parent_id, level=level
            )
            readiness = await readiness_service.calculate_readiness_score(
                db, learner, parent_id, level=level
            )
            levels.append(
                {
                    "level": level,
                    "is_current": loop_engine.level_matches(level, current_level),
                    "bank_total": counts["bank_total"],
                    "released": counts["released"],
                    "learning": counts["learning"],
                    "familiar": counts["familiar"],
                    "mastered": counts["mastered"],
                    "readiness_score": readiness["overall_score"],
                    "milestones": _milestones_for_level(
                        level=level,
                        counts=counts,
                        thresholds=thresholds,
                        existing=existing,
                    ),
                }
            )

    pack_badges = [badge for badge in existing if badge.startswith("pack_")]
    milestone_badges = [badge for badge in existing if any(t in badge for t in MILESTONE_TIERS)]

    return {
        "english_level": current_level,
        "overall": overall,
        "levels": levels,
        "packs": packs,
        "packs_by_level": packs_by_level,
        "earned_pack_badges": len(pack_badges),
        "earned_milestone_badges": len(milestone_badges),
        "total_pack_quests": len([p for p in packs if p["total_words"] > 0]),
        "completed_pack_quests": len([p for p in packs if p["completed"]]),
    }
