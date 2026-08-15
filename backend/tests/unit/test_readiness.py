"""Unit tests for readiness service."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import hash_password
from app.models.challenge import LevelAssessment
from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.srs import SrsCard, SrsReviewLog
from app.models.user import User
from app.models.word_list import WordList, WordListItem
from app.services import readiness_service


async def _make_parent_learner(db_session, *, suffix: str) -> tuple[User, Learner]:
    parent = User(
        username=f"parent_{suffix}",
        password_hash=hash_password("parent123"),
        role="parent",
        is_active=True,
    )
    db_session.add(parent)
    await db_session.flush()

    user = User(
        username=f"learner_{suffix}",
        password_hash=hash_password("learner"),
        role="learner",
        parent_id=parent.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    learner = Learner(
        user_id=user.id,
        display_name=f"Learner {suffix}",
        age=10,
        english_level="A1",
        ui_mode="kid",
    )
    db_session.add(learner)
    await db_session.commit()
    await db_session.refresh(learner)
    await db_session.refresh(parent)
    return parent, learner


async def _seed_strong_practice(
    db_session, *, parent: User, learner: Learner, words: int = 20
) -> None:
    bank = WordList(parent_id=parent.id, name=f"Bank {learner.id}", source="bank")
    db_session.add(bank)
    await db_session.flush()

    now = datetime.now(UTC)
    for i in range(words):
        entry = DictionaryEntry(
            word=f"ready_{learner.id}_{i}",
            definition=f"def {i}",
            source="test",
        )
        db_session.add(entry)
        await db_session.flush()

        db_session.add(
            WordListItem(
                word_list_id=bank.id,
                dictionary_entry_id=entry.id,
                level="A1",
                sort_order=i,
            )
        )
        await db_session.flush()

        card = SrsCard(
            learner_id=learner.id,
            dictionary_entry_id=entry.id,
            due_at=now,
            released_at=now - timedelta(days=10),
            state="review",
        )
        db_session.add(card)
        await db_session.flush()

        for day in range(7):
            db_session.add(
                SrsReviewLog(
                    srs_card_id=card.id,
                    learner_id=learner.id,
                    quality=5,
                    reviewed_at=now - timedelta(days=day),
                )
            )
    await db_session.commit()


@pytest.mark.asyncio
async def test_calculate_readiness_score_ready(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="ready")
    await _seed_strong_practice(db_session, parent=parent, learner=learner)

    result = await readiness_service.calculate_readiness_score(db_session, learner, parent.id)

    assert result["overall_score"] >= 0.70
    assert result["recommendation"] in {"ready", "progressing"}
    assert "dimensions" in result
    assert "accuracy" in result["dimensions"]
    assert "vocabulary_breadth" in result["dimensions"]
    assert len(result["focus_areas"]) > 0


@pytest.mark.asyncio
async def test_calculate_readiness_score_not_ready(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="notready")

    bank = WordList(parent_id=parent.id, name="Bank Not Ready", source="bank")
    db_session.add(bank)
    await db_session.flush()

    now = datetime.now(UTC)
    for i in range(20):
        entry = DictionaryEntry(word=f"notready_{i}", definition=f"def {i}", source="test")
        db_session.add(entry)
        await db_session.flush()
        db_session.add(
            WordListItem(
                word_list_id=bank.id,
                dictionary_entry_id=entry.id,
                level="A1",
                sort_order=i,
            )
        )
        await db_session.flush()

        if i < 5:
            card = SrsCard(
                learner_id=learner.id,
                dictionary_entry_id=entry.id,
                due_at=now,
                released_at=now - timedelta(days=2),
                state="learning",
            )
            db_session.add(card)
            await db_session.flush()
            for day in range(2):
                db_session.add(
                    SrsReviewLog(
                        srs_card_id=card.id,
                        learner_id=learner.id,
                        quality=2,
                        reviewed_at=now - timedelta(days=day),
                    )
                )
    await db_session.commit()

    result = await readiness_service.calculate_readiness_score(db_session, learner, parent.id)

    assert result["overall_score"] < 0.75
    assert result["recommendation"] in {"keep_practicing", "progressing"}
    assert result["estimated_weeks_to_ready"] > 0


@pytest.mark.asyncio
async def test_should_suggest_assessment_response_shape(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="suggest")
    await _seed_strong_practice(db_session, parent=parent, learner=learner)

    result = await readiness_service.should_suggest_assessment(db_session, learner, parent.id)

    assert "should_suggest" in result
    assert "reason" in result
    assert "cooldown_days_remaining" in result


@pytest.mark.asyncio
async def test_should_suggest_requires_ready_threshold(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="nudge75")
    await _seed_strong_practice(db_session, parent=parent, learner=learner)

    readiness = await readiness_service.calculate_readiness_score(db_session, learner, parent.id)
    result = await readiness_service.should_suggest_assessment(db_session, learner, parent.id)

    if readiness["overall_score"] >= readiness_service.READY_THRESHOLD:
        # Strong fixture may or may not have a 7-day calendar streak depending on seed timing.
        if readiness["metadata"]["streak_days"] >= 7:
            assert result["should_suggest"] is True
        else:
            assert result["should_suggest"] is False
    else:
        assert result["should_suggest"] is False
        assert (
            "continue practicing" in (result["reason"] or "").lower()
            or "not enough" in (result["reason"] or "").lower()
        )


@pytest.mark.asyncio
async def test_should_suggest_assessment_cooldown(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="cooldown")

    db_session.add(
        LevelAssessment(
            learner_id=learner.id,
            current_level="A1",
            suggested_level="A2",
            reason="Test",
            source="rules",
            status="pending",
            assessed_at=datetime.now(UTC) - timedelta(days=3),
        )
    )
    await db_session.commit()

    result = await readiness_service.should_suggest_assessment(db_session, learner, parent.id)

    assert result["should_suggest"] is False
    assert result["cooldown_days_remaining"] > 0
    assert "Run check" in (result["reason"] or "") or "pending" in (result["reason"] or "").lower()


def test_score_status() -> None:
    assert readiness_service._score_status(0.90) == "excellent"
    assert readiness_service._score_status(0.80) == "strong"
    assert readiness_service._score_status(0.70) == "good"
    assert readiness_service._score_status(0.55) == "fair"
    assert readiness_service._score_status(0.40) == "weak"


def test_estimate_weeks_to_ready() -> None:
    weeks = readiness_service._estimate_weeks_to_ready(0.60, 0.75)
    assert 1 <= weeks <= 8

    weeks = readiness_service._estimate_weeks_to_ready(0.74, 0.75)
    assert weeks == 1

    weeks = readiness_service._estimate_weeks_to_ready(0.80, 0.75)
    assert weeks == 1


def test_calculate_accuracy_score_recognition_first() -> None:
    # 80% recognition, 20% spelling — low dictation should not drag score as much.
    score = readiness_service._calculate_accuracy_score(90.0, 0.0, review_samples=10)
    assert score == pytest.approx(0.72)

    # With enough samples, recognition-only path still scores well.
    score_full_review = readiness_service._calculate_accuracy_score(100.0, 0.0, review_samples=10)
    assert score_full_review == 0.8


def test_vocabulary_breadth_description() -> None:
    text = readiness_service._vocabulary_breadth_description(
        {
            "familiar_or_mastered": 2,
            "mastered": 0,
            "released_at_level": 5,
            "total_at_level": 5,
            "bank_at_level": 446,
        },
        "A2",
    )
    assert text == "2 familiar, 0 mastered of 5 released at A2"
