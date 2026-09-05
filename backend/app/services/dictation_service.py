import json
import random
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dictation_scoring import (
    GIVE_UP_MARKER,
    generate_choices,
    hint_for_word,
    score_answer,
    split_syllables,
)
from app.models.dictation import DictationAttempt, DictationSession
from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.word_list import MistakeLog
from app.services import loop_engine, srs_service, tts_service, word_list_service

KID_MAX_ATTEMPTS = 3
CHALLENGE_SINGLE_ATTEMPT_SOURCES = frozenset({"daily_challenge", "mistakes"})


def _session_to_dict(session: DictationSession) -> dict:
    return {
        "id": session.id,
        "word_list_id": session.word_list_id,
        "source": session.source,
        "mode": session.mode,
        "ui_mode_snapshot": session.ui_mode_snapshot,
        "total_words": session.total_words,
        "correct_count": session.correct_count,
        "completed": session.completed_at is not None,
        "started_at": session.started_at,
        "completed_at": session.completed_at,
    }


def _entry_ids(session: DictationSession) -> list[int]:
    if not session.entry_ids_json:
        return []
    return json.loads(session.entry_ids_json)


def _correct_entry_ids(attempts: list[DictationAttempt]) -> set[int]:
    return {attempt.dictionary_entry_id for attempt in attempts if attempt.is_correct}


def _attempts_for_entry(attempts: list[DictationAttempt], entry_id: int) -> list[DictationAttempt]:
    return [attempt for attempt in attempts if attempt.dictionary_entry_id == entry_id]


async def _get_session_for_learner(
    db: AsyncSession, session_id: int, learner_id: int
) -> DictationSession:
    result = await db.execute(
        select(DictationSession).where(
            DictationSession.id == session_id,
            DictationSession.learner_id == learner_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


async def _load_entries(db: AsyncSession, entry_ids: list[int]) -> list[DictionaryEntry]:
    if not entry_ids:
        return []
    result = await db.execute(select(DictionaryEntry).where(DictionaryEntry.id.in_(entry_ids)))
    by_id = {entry.id: entry for entry in result.scalars().all()}
    return [by_id[entry_id] for entry_id in entry_ids if entry_id in by_id]


async def _get_attempts(db: AsyncSession, session_id: int) -> list[DictationAttempt]:
    result = await db.execute(
        select(DictationAttempt).where(DictationAttempt.session_id == session_id)
    )
    return list(result.scalars().all())


def _max_attempts(mode: str, source: str) -> int:
    if mode == "choice" and source in CHALLENGE_SINGLE_ATTEMPT_SOURCES:
        return 1
    return KID_MAX_ATTEMPTS if mode == "choice" else 1


def _is_entry_resolved(
    entry_id: int, attempts: list[DictationAttempt], mode: str, source: str
) -> bool:
    entry_attempts = _attempts_for_entry(attempts, entry_id)
    if any(attempt.is_correct for attempt in entry_attempts):
        return True
    if mode == "typed":
        return any(attempt.submitted_answer == GIVE_UP_MARKER for attempt in entry_attempts)
    return len(entry_attempts) >= _max_attempts(mode, source)


def _current_entry_id(
    entry_ids: list[int], attempts: list[DictationAttempt], mode: str, source: str
) -> int | None:
    for entry_id in entry_ids:
        if not _is_entry_resolved(entry_id, attempts, mode, source):
            return entry_id
    return None


def _is_session_complete(session: DictationSession, attempts: list[DictationAttempt]) -> bool:
    return (
        _current_entry_id(_entry_ids(session), attempts, session.mode, session.source) is None
    )


async def _collect_entry_ids(
    db: AsyncSession,
    *,
    learner_id: int,
    word_list_id: int | None,
    source: str,
    max_words: int,
    entry_ids_override: list[int] | None = None,
) -> tuple[list[int], int | None]:
    if source == "daily_challenge":
        entry_ids = await loop_engine.get_today_mix_entry_ids(db, learner_id=learner_id)
        return entry_ids[:max_words], None

    if source == "mistakes":
        if entry_ids_override:
            return entry_ids_override[:max_words], None
        entry_ids = await srs_service._mistake_challenge_entry_ids(db, learner_id=learner_id)
        return entry_ids, None

    if word_list_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="word_list_id is required for word_list source",
        )

    word_list = await word_list_service.get_word_list_for_learner(db, word_list_id, learner_id)
    items = sorted(word_list.items, key=lambda row: (row.sort_order, row.id))
    entry_ids = [item.dictionary_entry_id for item in items]
    return entry_ids[:max_words], word_list_id


async def _mark_daily_challenge_if_needed(db: AsyncSession, *, session: DictationSession) -> None:
    if (
        session.source != "daily_challenge"
        or session.mode != "choice"
        or session.completed_at is None
    ):
        return
    await loop_engine.mark_dictation_phase_complete(db, learner_id=session.learner_id)


async def start_session(
    db: AsyncSession,
    *,
    learner: Learner,
    word_list_id: int | None,
    source: str,
    mode: str | None,
    max_words: int,
    entry_ids: list[int] | None = None,
) -> dict:
    resolved_mode = mode or "typed"
    if resolved_mode not in {"choice", "typed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid mode")
    if source not in {"word_list", "mistakes", "daily_challenge"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source")
    if entry_ids is not None and source != "mistakes":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="entry_ids is only supported for mistakes source",
        )

    # Challenge mix is usually small; allow the full set.
    effective_max = max_words if source != "daily_challenge" else max(max_words, 30)

    resolved_entry_ids, resolved_list_id = await _collect_entry_ids(
        db,
        learner_id=learner.id,
        word_list_id=word_list_id,
        source=source,
        max_words=effective_max,
        entry_ids_override=entry_ids,
    )
    if not resolved_entry_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_WORDS",
                "message": (
                    "No challenge words yet — open Home first"
                    if source == "daily_challenge"
                    else "No words available for dictation"
                ),
            },
        )

    random.shuffle(resolved_entry_ids)
    session = DictationSession(
        learner_id=learner.id,
        word_list_id=resolved_list_id,
        source=source,
        mode=resolved_mode,
        ui_mode_snapshot=learner.ui_mode,
        total_words=len(resolved_entry_ids),
        correct_count=0,
        entry_ids_json=json.dumps(resolved_entry_ids),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _session_to_dict(session)


async def get_session(db: AsyncSession, *, learner_id: int, session_id: int) -> dict:
    session = await _get_session_for_learner(db, session_id, learner_id)
    return _session_to_dict(session)


async def get_next_prompt(db: AsyncSession, *, learner_id: int, session_id: int) -> dict:
    session = await _get_session_for_learner(db, session_id, learner_id)
    if session.completed_at is not None:
        return {
            "word_index": session.total_words,
            "total_words": session.total_words,
            "mode": session.mode,
            "choices": None,
            "hint": None,
            "retries_remaining": 0,
            "session_complete": True,
        }

    entry_ids = _entry_ids(session)
    attempts = await _get_attempts(db, session.id)
    current_entry_id = _current_entry_id(entry_ids, attempts, session.mode, session.source)
    if current_entry_id is None:
        session.completed_at = datetime.now(UTC)
        await db.commit()
        await _mark_daily_challenge_if_needed(db, session=session)
        return {
            "word_index": session.total_words,
            "total_words": session.total_words,
            "mode": session.mode,
            "choices": None,
            "hint": None,
            "retries_remaining": 0,
            "session_complete": True,
        }

    entries = await _load_entries(db, entry_ids)
    current = next(entry for entry in entries if entry.id == current_entry_id)
    entry_attempts = _attempts_for_entry(attempts, current_entry_id)
    max_attempts = _max_attempts(session.mode, session.source)
    retries_remaining = max(0, max_attempts - len(entry_attempts))
    resolved_count = sum(
        1 for entry_id in entry_ids if _is_entry_resolved(entry_id, attempts, session.mode, session.source)
    )
    word_index = resolved_count + 1

    choices = None
    if session.mode == "choice":
        pool = [entry.word for entry in entries]
        choices = generate_choices(current.word, pool)

    return {
        "word_index": word_index,
        "total_words": session.total_words,
        "mode": session.mode,
        "choices": choices,
        "hint": None,
        "retries_remaining": retries_remaining,
        "session_complete": False,
    }


async def get_hint(db: AsyncSession, *, learner_id: int, session_id: int) -> dict:
    session = await _get_session_for_learner(db, session_id, learner_id)
    if session.mode != "choice":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Hints are choice-mode only"
        )

    entry_ids = _entry_ids(session)
    attempts = await _get_attempts(db, session.id)
    current_entry_id = _current_entry_id(entry_ids, attempts, session.mode, session.source)
    if current_entry_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session complete")

    entries = await _load_entries(db, [current_entry_id])
    if not entries:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")
    return {"hint": hint_for_word(entries[0].word)}


async def get_current_audio_path(
    db: AsyncSession, *, learner_id: int, session_id: int, slow: bool = False
) -> tuple[DictationSession, str]:
    session = await _get_session_for_learner(db, session_id, learner_id)
    if session.completed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session complete")

    entry_ids = _entry_ids(session)
    attempts = await _get_attempts(db, session.id)
    current_entry_id = _current_entry_id(entry_ids, attempts, session.mode, session.source)
    if current_entry_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session complete")

    entries = await _load_entries(db, [current_entry_id])
    if not entries:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")
    path = await tts_service.ensure_audio(db, entries[0], slow=slow)
    return session, str(path)


async def submit_answer(
    db: AsyncSession,
    *,
    learner_id: int,
    session_id: int,
    answer: str,
    hint_used: bool,
) -> dict:
    session = await _get_session_for_learner(db, session_id, learner_id)
    if session.completed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SESSION_COMPLETE", "message": "Dictation already finished"},
        )

    entry_ids = _entry_ids(session)
    attempts = await _get_attempts(db, session.id)
    current_entry_id = _current_entry_id(entry_ids, attempts, session.mode, session.source)
    if current_entry_id is None:
        session.completed_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SESSION_COMPLETE", "message": "Dictation already finished"},
        )

    entry_attempts = _attempts_for_entry(attempts, current_entry_id)
    entries = await _load_entries(db, [current_entry_id])
    current = entries[0]
    is_correct = score_answer(current.word, answer)
    max_attempts = _max_attempts(session.mode, session.source)
    attempt_number = len(entry_attempts) + 1

    db.add(
        DictationAttempt(
            session_id=session.id,
            dictionary_entry_id=current.id,
            expected_word=current.word,
            submitted_answer=answer,
            is_correct=is_correct,
            hint_used=hint_used,
            attempt_number=attempt_number,
        )
    )

    reveal_word = False
    if is_correct:
        session.correct_count += 1
    elif session.mode == "choice" and attempt_number >= max_attempts:
        reveal_word = True
        db.add(
            MistakeLog(
                learner_id=learner_id,
                dictionary_entry_id=current.id,
                context="dictation",
                wrong_answer=answer,
            )
        )
        await srs_service.ensure_review_card_for_entry(
            db,
            learner_id=learner_id,
            dictionary_entry_id=current.id,
            word_list_id=session.word_list_id,
        )

    await db.flush()
    updated_attempts = await _get_attempts(db, session.id)

    if _is_session_complete(session, updated_attempts):
        session.completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(session)
    await _mark_daily_challenge_if_needed(db, session=session)

    current_entry_id_after = _current_entry_id(
        entry_ids, updated_attempts, session.mode, session.source
    )
    retries_remaining = 0
    if not is_correct and reveal_word:
        retries_remaining = 0
    elif current_entry_id_after is not None and session.mode == "choice":
        retries_remaining = max(
            0,
            max_attempts - len(_attempts_for_entry(updated_attempts, current_entry_id_after)),
        )

    result = {
        "is_correct": is_correct,
        "expected_word": current.word if reveal_word else None,
        "syllables": None,
        "can_retry": session.mode == "typed" and not is_correct and not reveal_word,
        "retries_remaining": retries_remaining,
        "session_complete": session.completed_at is not None,
        "correct_count": session.correct_count,
        "total_words": session.total_words,
    }
    return result


async def give_up(
    db: AsyncSession,
    *,
    learner_id: int,
    session_id: int,
) -> dict:
    session = await _get_session_for_learner(db, session_id, learner_id)
    if session.mode != "typed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Give up is only available in typed dictation",
        )
    if session.completed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SESSION_COMPLETE", "message": "Dictation already finished"},
        )

    entry_ids = _entry_ids(session)
    attempts = await _get_attempts(db, session.id)
    current_entry_id = _current_entry_id(entry_ids, attempts, session.mode, session.source)
    if current_entry_id is None:
        session.completed_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SESSION_COMPLETE", "message": "Dictation already finished"},
        )

    entry_attempts = _attempts_for_entry(attempts, current_entry_id)
    entries = await _load_entries(db, [current_entry_id])
    current = entries[0]
    last_wrong = next(
        (
            attempt.submitted_answer
            for attempt in reversed(entry_attempts)
            if not attempt.is_correct
        ),
        "gave up",
    )

    db.add(
        DictationAttempt(
            session_id=session.id,
            dictionary_entry_id=current.id,
            expected_word=current.word,
            submitted_answer=GIVE_UP_MARKER,
            is_correct=False,
            hint_used=False,
            attempt_number=len(entry_attempts) + 1,
        )
    )
    db.add(
        MistakeLog(
            learner_id=learner_id,
            dictionary_entry_id=current.id,
            context="dictation",
            wrong_answer=last_wrong,
        )
    )
    await srs_service.ensure_review_card_for_entry(
        db,
        learner_id=learner_id,
        dictionary_entry_id=current.id,
        word_list_id=session.word_list_id,
    )

    await db.flush()
    updated_attempts = await _get_attempts(db, session.id)
    if _is_session_complete(session, updated_attempts):
        session.completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(session)
    await _mark_daily_challenge_if_needed(db, session=session)

    return {
        "is_correct": False,
        "expected_word": current.word,
        "syllables": split_syllables(current.word),
        "can_retry": False,
        "retries_remaining": 0,
        "session_complete": session.completed_at is not None,
        "correct_count": session.correct_count,
        "total_words": session.total_words,
    }


async def complete_session(db: AsyncSession, *, learner_id: int, session_id: int) -> dict:
    session = await _get_session_for_learner(db, session_id, learner_id)
    if session.completed_at is None:
        session.completed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(session)
    await _mark_daily_challenge_if_needed(db, session=session)
    return _session_to_dict(session)


async def list_history(db: AsyncSession, *, learner_id: int, limit: int = 20) -> list[dict]:
    result = await db.execute(
        select(DictationSession)
        .where(
            DictationSession.learner_id == learner_id,
            DictationSession.completed_at.is_not(None),
        )
        .order_by(DictationSession.completed_at.desc())
        .limit(limit)
    )
    sessions = result.scalars().all()
    history: list[dict] = []
    for session in sessions:
        score = 0.0
        if session.total_words > 0:
            score = round((session.correct_count / session.total_words) * 100, 1)
        history.append(
            {
                "id": session.id,
                "mode": session.mode,
                "total_words": session.total_words,
                "correct_count": session.correct_count,
                "started_at": session.started_at,
                "completed_at": session.completed_at,
                "score_percent": score,
            }
        )
    return history
