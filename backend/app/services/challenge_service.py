import json
import random
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dictation_scoring import generate_choices, score_answer
from app.models.challenge import LearnerBadge, LevelAssessment, LevelChallenge
from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.user import User
from app.models.word_list import WordList, WordListAssignment, WordListItem
from app.services import dashboard_service, readiness_service, srs_service, word_list_service

CHALLENGE_META = {
    "level_up": {
        "title": "Level-up exam",
        "description": "Pick the right word for each meaning to earn your level badge.",
        "word_count": 30,
        "pass_threshold": 0.8,
    },
    "streak": {
        "title": "Streak champion",
        "description": "Pick the right word for each meaning on your streak day.",
        "word_count": 5,
        "pass_threshold": 0.6,
    },
    "mistake_mastery": {
        "title": "Mistake mastery",
        "description": "Answer up to 5 mistake words correctly to clear them.",
        "word_count": 5,
        "pass_threshold": 0.8,
    },
}


def _entry_ids(challenge: LevelChallenge) -> list[int]:
    if not challenge.entry_ids_json:
        return []
    return json.loads(challenge.entry_ids_json)


async def _parent_id_for_learner(db: AsyncSession, learner: Learner) -> int | None:
    result = await db.execute(select(User.parent_id).where(User.id == learner.user_id))
    return result.scalar_one_or_none()


async def _parent_unlocked_level_up(
    db: AsyncSession, *, learner_id: int, challenge: LevelChallenge
) -> bool:
    """True when parent accepted a level suggestion that created this exam."""
    if challenge.target_level is None:
        return False
    result = await db.execute(
        select(LevelAssessment.id)
        .where(
            LevelAssessment.learner_id == learner_id,
            LevelAssessment.status == "accepted",
            LevelAssessment.suggested_level == challenge.target_level,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _level_up_gate(
    db: AsyncSession,
    *,
    learner: Learner,
    existing: LevelChallenge | None,
) -> dict:
    """
    Soft gate: unlock Level-up exam at readiness ≥ 75%.

    Parent-accepted exams (pending/in_progress tied to an accepted assessment)
    stay unlocked even if readiness later dips. Stale self-started sessions do not.
    """
    if (
        existing is not None
        and existing.status in {"pending", "in_progress"}
        and await _parent_unlocked_level_up(db, learner_id=learner.id, challenge=existing)
    ):
        return {
            "can_start": True,
            "readiness_score": None,
            "lock_reason": None,
        }

    parent_id = await _parent_id_for_learner(db, learner)
    if parent_id is None:
        return {
            "can_start": False,
            "readiness_score": None,
            "lock_reason": "Level-up exam unlocks when readiness reaches 75%.",
        }

    readiness = await readiness_service.calculate_readiness_score(db, learner, parent_id)
    score = float(readiness["overall_score"])
    threshold = readiness_service.READY_THRESHOLD
    if score >= threshold:
        return {
            "can_start": True,
            "readiness_score": score,
            "lock_reason": None,
        }

    percent = int(round(score * 100))
    need = int(threshold * 100)
    return {
        "can_start": False,
        "readiness_score": score,
        "lock_reason": f"Keep practicing — readiness {percent}% (need {need}% to unlock).",
    }


async def _collect_entry_ids(
    db: AsyncSession, *, level: str | None, count: int, learner_id: int
) -> list[int]:
    entry_ids: list[int] = []
    if level:
        result = await db.execute(
            select(WordListItem.dictionary_entry_id)
            .join(WordList, WordListItem.word_list_id == WordList.id)
            .where(WordList.source == "curated", WordList.level_tag == level.upper())
            .distinct()
        )
        entry_ids = [row[0] for row in result.all()]

    if len(entry_ids) < count:
        assigned = await db.execute(
            select(WordListItem.dictionary_entry_id)
            .join(WordListAssignment, WordListAssignment.word_list_id == WordListItem.word_list_id)
            .where(
                WordListAssignment.learner_id == learner_id,
                WordListAssignment.is_active.is_(True),
            )
            .distinct()
        )
        entry_ids = list({*entry_ids, *(row[0] for row in assigned.all())})

    random.shuffle(entry_ids)
    have = len(entry_ids)
    need = min(3, count)
    if have < need:
        shortfall = need - have
        more_label = "1 more word" if shortfall == 1 else f"{shortfall} more words"
        have_label = "none yet" if have == 0 else f"{have} ready"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Almost there! Learn {more_label} to unlock this challenge "
                f"(you have {have_label}). Keep practicing — you can do it!"
            ),
        )
    return entry_ids[:count]


async def assign_catalog_lists_for_level(
    db: AsyncSession, *, learner_id: int, parent_id: int, level: str
) -> None:
    catalog = await word_list_service.list_catalog(db, level=level)
    if not catalog:
        return

    assigned_result = await db.execute(
        select(WordListAssignment.word_list_id).where(
            WordListAssignment.learner_id == learner_id,
            WordListAssignment.is_active.is_(True),
        )
    )
    assigned_ids = {row[0] for row in assigned_result.all()}
    to_assign = [item["id"] for item in catalog[:2] if item["id"] not in assigned_ids]
    if not to_assign:
        return

    for list_id in to_assign:
        result = await db.execute(select(WordList).where(WordList.id == list_id))
        word_list = result.scalar_one_or_none()
        if word_list is not None:
            await word_list_service.assign_word_list(
                db,
                word_list,
                parent_id=parent_id,
                learner_ids=[learner_id],
            )


async def create_level_up_challenge(
    db: AsyncSession, *, learner_id: int, target_level: str
) -> LevelChallenge:
    existing = await db.execute(
        select(LevelChallenge).where(
            LevelChallenge.learner_id == learner_id,
            LevelChallenge.challenge_type == "level_up",
            LevelChallenge.target_level == target_level.upper(),
            LevelChallenge.status.in_(["pending", "in_progress"]),
        )
    )
    challenge = existing.scalar_one_or_none()
    if challenge is not None:
        return challenge

    meta = CHALLENGE_META["level_up"]
    challenge = LevelChallenge(
        learner_id=learner_id,
        challenge_type="level_up",
        target_level=target_level.upper(),
        status="pending",
        pass_threshold=meta["pass_threshold"],
    )
    db.add(challenge)
    await db.flush()
    return challenge


async def get_available_challenges(db: AsyncSession, *, learner: Learner) -> list[dict]:
    streak_days = await dashboard_service._review_streak_days(db, learner.id)

    active_result = await db.execute(
        select(LevelChallenge).where(
            LevelChallenge.learner_id == learner.id,
            LevelChallenge.status.in_(["pending", "in_progress"]),
        )
    )
    active = {row.challenge_type: row for row in active_result.scalars().all()}
    available: list[dict] = []

    for challenge_type, meta in CHALLENGE_META.items():
        # Deferred until a real timed dictation UX exists (Phase 1 teen optional).
        if challenge_type == "speed_dictation":
            continue
        if challenge_type == "streak" and streak_days < 7:
            continue
        # Mistake practice reuses Daily Challenge (?mistakes=1) — not this typing quiz.
        if challenge_type == "mistake_mastery":
            continue

        existing = active.get(challenge_type)
        can_start = True
        readiness_score = None
        lock_reason = None
        if challenge_type == "level_up":
            gate = await _level_up_gate(db, learner=learner, existing=existing)
            can_start = gate["can_start"]
            readiness_score = gate["readiness_score"]
            lock_reason = gate["lock_reason"]

        available.append(
            {
                "id": existing.id if existing else None,
                "challenge_type": challenge_type,
                "title": meta["title"],
                "description": meta["description"],
                "target_level": existing.target_level if existing else None,
                "status": existing.status if existing else None,
                "can_start": can_start,
                "word_count": meta["word_count"],
                "pass_threshold": meta["pass_threshold"],
                "readiness_score": readiness_score,
                "lock_reason": lock_reason,
            }
        )

    return available


def _challenge_to_session(challenge: LevelChallenge, entries: list[DictionaryEntry]) -> dict:
    # Recognition-based: each definition comes with word choices drawn from the
    # other challenge words. Choices reshuffle on resume, which is acceptable.
    word_pool = [entry.word for entry in entries]
    return {
        "id": challenge.id,
        "challenge_type": challenge.challenge_type,
        "target_level": challenge.target_level,
        "status": challenge.status,
        "pass_threshold": challenge.pass_threshold,
        "total_words": len(entries),
        "words": [
            {
                "dictionary_entry_id": entry.id,
                "word_index": index + 1,
                "total_words": len(entries),
                "definition": entry.definition,
                "choices": generate_choices(entry.word, word_pool),
            }
            for index, entry in enumerate(entries)
        ],
        "started_at": challenge.started_at,
    }


async def start_challenge(
    db: AsyncSession,
    *,
    learner: Learner,
    challenge_type: str,
    challenge_id: int | None = None,
    target_level: str | None = None,
) -> dict:
    if challenge_type not in CHALLENGE_META:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown challenge type"
        )

    challenge: LevelChallenge | None = None
    if challenge_id is not None:
        result = await db.execute(
            select(LevelChallenge).where(
                LevelChallenge.id == challenge_id,
                LevelChallenge.learner_id == learner.id,
            )
        )
        challenge = result.scalar_one_or_none()
        if challenge is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    else:
        result = await db.execute(
            select(LevelChallenge).where(
                LevelChallenge.learner_id == learner.id,
                LevelChallenge.challenge_type == challenge_type,
                LevelChallenge.status.in_(["pending", "in_progress"]),
            )
        )
        challenge = result.scalar_one_or_none()

    if challenge_type == "level_up":
        gate = await _level_up_gate(db, learner=learner, existing=challenge)
        if not gate["can_start"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=gate["lock_reason"] or "Level-up exam unlocks when readiness reaches 75%.",
            )

    meta = CHALLENGE_META[challenge_type]
    level = target_level or (challenge.target_level if challenge else None) or learner.english_level

    if challenge is None:
        challenge = LevelChallenge(
            learner_id=learner.id,
            challenge_type=challenge_type,
            target_level=level.upper() if challenge_type == "level_up" else None,
            status="pending",
            pass_threshold=meta["pass_threshold"],
        )
        db.add(challenge)
        await db.flush()

    if challenge.status == "passed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge already passed"
        )

    entry_ids = _entry_ids(challenge)
    if not entry_ids:
        if challenge_type == "mistake_mastery":
            entry_ids = await srs_service._mistake_challenge_entry_ids(db, learner_id=learner.id)
        else:
            pick_level = level if challenge_type == "level_up" else learner.english_level
            entry_ids = await _collect_entry_ids(
                db, level=pick_level, count=meta["word_count"], learner_id=learner.id
            )
        challenge.entry_ids_json = json.dumps(entry_ids)

    if not entry_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No words available for this challenge",
        )

    challenge.status = "in_progress"
    challenge.started_at = challenge.started_at or datetime.now(UTC)
    await db.commit()
    await db.refresh(challenge)

    result = await db.execute(select(DictionaryEntry).where(DictionaryEntry.id.in_(entry_ids)))
    by_id = {entry.id: entry for entry in result.scalars().all()}
    entries = [by_id[entry_id] for entry_id in entry_ids if entry_id in by_id]
    return _challenge_to_session(challenge, entries)


async def submit_challenge(
    db: AsyncSession,
    *,
    learner: Learner,
    challenge_id: int,
    answers: list[dict],
) -> dict:
    result = await db.execute(
        select(LevelChallenge).where(
            LevelChallenge.id == challenge_id,
            LevelChallenge.learner_id == learner.id,
        )
    )
    challenge = result.scalar_one_or_none()
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    if challenge.status not in {"in_progress", "pending"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge not active")

    entry_ids = _entry_ids(challenge)
    if not entry_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge has no words"
        )

    entries_result = await db.execute(
        select(DictionaryEntry).where(DictionaryEntry.id.in_(entry_ids))
    )
    by_id = {entry.id: entry for entry in entries_result.scalars().all()}
    answer_map = {item["dictionary_entry_id"]: item["answer"] for item in answers}

    correct = 0
    for entry_id in entry_ids:
        entry = by_id.get(entry_id)
        if entry is None:
            continue
        submitted = answer_map.get(entry_id, "")
        if score_answer(submitted, entry.word):
            correct += 1

    total = len(entry_ids)
    score = round(correct / total, 3) if total else 0.0
    passed = score >= challenge.pass_threshold
    challenge.score = score
    challenge.status = "passed" if passed else "failed"
    challenge.completed_at = datetime.now(UTC)

    badge_earned: str | None = None
    new_level: str | None = None
    if passed:
        badge_type = f"{challenge.challenge_type}_badge"
        badge = LearnerBadge(learner_id=learner.id, badge_type=badge_type)
        db.add(badge)
        badge_earned = badge_type
        if challenge.challenge_type == "level_up" and challenge.target_level:
            learner.english_level = challenge.target_level
            new_level = challenge.target_level
        if challenge.challenge_type == "mistake_mastery":
            await srs_service.complete_mistake_challenge(
                db,
                learner_id=learner.id,
                dictionary_entry_ids=entry_ids,
            )

    await db.commit()
    return {
        "id": challenge.id,
        "status": challenge.status,
        "score": score,
        "passed": passed,
        "correct_count": correct,
        "total_words": total,
        "badge_earned": badge_earned,
        "new_english_level": new_level,
    }


async def get_history(db: AsyncSession, *, learner_id: int, limit: int = 20) -> list[dict]:
    result = await db.execute(
        select(LevelChallenge)
        .where(
            LevelChallenge.learner_id == learner_id,
            LevelChallenge.status.in_(["passed", "failed"]),
        )
        .order_by(LevelChallenge.completed_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": row.id,
            "challenge_type": row.challenge_type,
            "target_level": row.target_level,
            "status": row.status,
            "score": row.score,
            "completed_at": row.completed_at,
        }
        for row in result.scalars().all()
    ]


async def get_badges(db: AsyncSession, *, learner_id: int) -> list[dict]:
    result = await db.execute(
        select(LearnerBadge)
        .where(LearnerBadge.learner_id == learner_id)
        .order_by(LearnerBadge.earned_at.desc())
    )
    return [
        {"id": badge.id, "badge_type": badge.badge_type, "earned_at": badge.earned_at}
        for badge in result.scalars().all()
    ]
