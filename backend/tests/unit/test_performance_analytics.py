"""Unit tests for performance analytics service."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import hash_password
from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.srs import SrsCard, SrsReviewLog
from app.models.user import User
from app.models.word_list import WordList, WordListItem
from app.services import performance_analytics


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


@pytest.mark.asyncio
async def test_calculate_consistency_score_high_consistency(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="cons_hi")

    entry = DictionaryEntry(word="cons_hi", definition="test", source="test")
    db_session.add(entry)
    await db_session.flush()

    card = SrsCard(
        learner_id=learner.id,
        dictionary_entry_id=entry.id,
        due_at=datetime.now(UTC),
        released_at=datetime.now(UTC),
        state="review",
    )
    db_session.add(card)
    await db_session.flush()

    now = datetime.now(UTC)
    for day in range(7):
        review_date = now - timedelta(days=day)
        for _ in range(10):
            db_session.add(
                SrsReviewLog(
                    srs_card_id=card.id,
                    learner_id=learner.id,
                    quality=4,
                    reviewed_at=review_date,
                )
            )
    await db_session.commit()

    score = await performance_analytics.calculate_consistency_score(db_session, learner.id, days=14)
    assert score >= 0.85


@pytest.mark.asyncio
async def test_calculate_consistency_score_low_consistency(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="cons_lo")

    entry = DictionaryEntry(word="cons_lo", definition="test", source="test")
    db_session.add(entry)
    await db_session.flush()

    card = SrsCard(
        learner_id=learner.id,
        dictionary_entry_id=entry.id,
        due_at=datetime.now(UTC),
        released_at=datetime.now(UTC),
        state="review",
    )
    db_session.add(card)
    await db_session.flush()

    now = datetime.now(UTC)
    qualities = [5, 1, 5, 1, 5, 1, 5]
    for day, quality in enumerate(qualities):
        review_date = now - timedelta(days=day)
        for _ in range(10):
            db_session.add(
                SrsReviewLog(
                    srs_card_id=card.id,
                    learner_id=learner.id,
                    quality=quality,
                    reviewed_at=review_date,
                )
            )
    await db_session.commit()

    score = await performance_analytics.calculate_consistency_score(db_session, learner.id, days=14)
    assert score < 0.70


@pytest.mark.asyncio
async def test_calculate_retention_strength_good_retention(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="ret_good")

    for i in range(10):
        entry = DictionaryEntry(word=f"ret_good_{i}", definition=f"def {i}", source="test")
        db_session.add(entry)
        await db_session.flush()

        card = SrsCard(
            learner_id=learner.id,
            dictionary_entry_id=entry.id,
            due_at=datetime.now(UTC),
            released_at=datetime.now(UTC),
            state="review",
        )
        db_session.add(card)
        await db_session.flush()

        for _ in range(5):
            db_session.add(
                SrsReviewLog(
                    srs_card_id=card.id,
                    learner_id=learner.id,
                    quality=4,
                )
            )
    await db_session.commit()

    result = await performance_analytics.calculate_retention_strength(db_session, learner.id)
    assert result["forgetting_rate"] == 0.0
    assert result["score"] >= 0.90


@pytest.mark.asyncio
async def test_calculate_vocabulary_breadth(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="breadth")

    bank = WordList(parent_id=parent.id, name="Family Bank Breadth", source="bank")
    db_session.add(bank)
    await db_session.flush()

    mastered_count = 0
    now = datetime.now(UTC)
    for i in range(20):
        entry = DictionaryEntry(word=f"breadth_{i}", definition=f"A1 def {i}", source="test")
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

        if i < 12:
            card = SrsCard(
                learner_id=learner.id,
                dictionary_entry_id=entry.id,
                due_at=now,
                released_at=now - timedelta(days=10),
                state="review",
            )
            db_session.add(card)
            await db_session.flush()

            for day in range(5):
                db_session.add(
                    SrsReviewLog(
                        srs_card_id=card.id,
                        learner_id=learner.id,
                        quality=4,
                        reviewed_at=now - timedelta(days=day),
                    )
                )
            mastered_count += 1

    await db_session.commit()

    result = await performance_analytics.calculate_vocabulary_breadth(
        db_session, learner, parent.id
    )
    # Score against released words (12), not full bank (20).
    assert result["bank_at_level"] == 20
    assert result["released_at_level"] == mastered_count
    assert result["total_at_level"] == mastered_count
    assert result["familiar_or_mastered"] == mastered_count
    assert result["mastered"] == mastered_count
    assert result["percentage"] == 1.0
    assert result["score"] == 1.0


@pytest.mark.asyncio
async def test_calculate_vocabulary_breadth_excludes_off_bank_cards(db_session) -> None:
    """Familiar cards outside the level bank must not inflate the numerator."""
    parent, learner = await _make_parent_learner(db_session, suffix="breadth_scope")

    bank = WordList(parent_id=parent.id, name="Family Bank Scope", source="bank")
    db_session.add(bank)
    await db_session.flush()

    now = datetime.now(UTC)
    bank_entry = DictionaryEntry(word="bank_word", definition="in bank", source="test")
    db_session.add(bank_entry)
    await db_session.flush()
    db_session.add(
        WordListItem(
            word_list_id=bank.id,
            dictionary_entry_id=bank_entry.id,
            level="A1",
            sort_order=0,
        )
    )
    await db_session.flush()

    off_bank_entry = DictionaryEntry(word="off_bank_word", definition="not in bank", source="test")
    db_session.add(off_bank_entry)
    await db_session.flush()

    for entry in (bank_entry, off_bank_entry):
        card = SrsCard(
            learner_id=learner.id,
            dictionary_entry_id=entry.id,
            due_at=now,
            released_at=now - timedelta(days=10),
            state="review",
        )
        db_session.add(card)
        await db_session.flush()
        for day in range(2):
            db_session.add(
                SrsReviewLog(
                    srs_card_id=card.id,
                    learner_id=learner.id,
                    quality=4,
                    reviewed_at=now - timedelta(days=day),
                )
            )
    await db_session.commit()

    result = await performance_analytics.calculate_vocabulary_breadth(
        db_session, learner, parent.id
    )
    assert result["bank_at_level"] == 1
    assert result["released_at_level"] == 1
    assert result["total_at_level"] == 1
    assert result["familiar_or_mastered"] == 1
    assert result["mastered"] == 0
    assert result["score"] == 1.0


@pytest.mark.asyncio
async def test_review_accuracy_ignores_off_level_cards(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="acc_level")

    bank = WordList(parent_id=parent.id, name="Family Bank Acc", source="bank")
    db_session.add(bank)
    await db_session.flush()

    now = datetime.now(UTC)
    a1 = DictionaryEntry(word="a1_word", definition="a1", source="test")
    b1 = DictionaryEntry(word="b1_word", definition="b1", source="test")
    db_session.add_all([a1, b1])
    await db_session.flush()
    db_session.add(
        WordListItem(word_list_id=bank.id, dictionary_entry_id=a1.id, level="A1", sort_order=0)
    )
    db_session.add(
        WordListItem(word_list_id=bank.id, dictionary_entry_id=b1.id, level="B1", sort_order=1)
    )
    await db_session.flush()

    a1_card = SrsCard(
        learner_id=learner.id,
        dictionary_entry_id=a1.id,
        due_at=now,
        released_at=now,
        state="review",
    )
    b1_card = SrsCard(
        learner_id=learner.id,
        dictionary_entry_id=b1.id,
        due_at=now,
        released_at=now,
        state="review",
    )
    db_session.add_all([a1_card, b1_card])
    await db_session.flush()

    # Perfect A1 reviews; failing B1 reviews must not drag current-level accuracy.
    for _ in range(5):
        db_session.add(
            SrsReviewLog(
                srs_card_id=a1_card.id,
                learner_id=learner.id,
                quality=5,
                reviewed_at=now,
            )
        )
        db_session.add(
            SrsReviewLog(
                srs_card_id=b1_card.id,
                learner_id=learner.id,
                quality=1,
                reviewed_at=now,
            )
        )
    await db_session.commit()

    cards, bank_at_level = await performance_analytics.current_level_released_cards(
        db_session, learner, parent.id
    )
    assert bank_at_level == 1
    assert len(cards) == 1
    card_ids = {cards[0].id}
    accuracy, samples = await performance_analytics.review_accuracy_for_cards(
        db_session, learner.id, 14, card_ids
    )
    assert samples == 5
    assert accuracy == 100.0

    metrics = await performance_analytics.get_performance_metrics(
        db_session, learner, parent.id, days=14
    )
    assert metrics["review_accuracy"] == 100.0
    assert metrics["review_samples"] == 5
    assert metrics["vocabulary_breadth"]["score"] == 0.0  # released but not yet Familiar (1 day)


@pytest.mark.asyncio
async def test_consistency_score_insufficient_data(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="cons_empty")
    score = await performance_analytics.calculate_consistency_score(db_session, learner.id, days=14)
    assert score == 0.5

    empty_scoped = await performance_analytics.calculate_consistency_score(
        db_session, learner.id, days=14, card_ids=set()
    )
    assert empty_scoped == 0.5


@pytest.mark.asyncio
async def test_retention_ignores_wrongs_older_than_30_days(db_session) -> None:
    parent, learner = await _make_parent_learner(db_session, suffix="ret_window")
    now = datetime.now(UTC)

    entry = DictionaryEntry(word="ret_old", definition="test", source="test")
    db_session.add(entry)
    await db_session.flush()
    card = SrsCard(
        learner_id=learner.id,
        dictionary_entry_id=entry.id,
        due_at=now,
        released_at=now - timedelta(days=60),
        state="review",
    )
    db_session.add(card)
    await db_session.flush()
    db_session.add(
        SrsReviewLog(
            srs_card_id=card.id,
            learner_id=learner.id,
            quality=1,
            reviewed_at=now - timedelta(days=45),
        )
    )
    db_session.add(
        SrsReviewLog(
            srs_card_id=card.id,
            learner_id=learner.id,
            quality=4,
            reviewed_at=now - timedelta(days=2),
        )
    )
    await db_session.commit()

    result = await performance_analytics.calculate_retention_strength(db_session, learner.id)
    assert result["forgetting_rate"] == 0.0
    assert result["score"] >= 0.90
