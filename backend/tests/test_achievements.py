from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.sm2 import DEFAULT_EASE_FACTOR
from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.srs import SrsCard, SrsReviewLog
from app.models.word_list import WordList, WordListItem, WordListItemCategory
from app.services import achievement_service


async def _login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_quests_endpoint_returns_packs_and_milestones(client, db_session) -> None:
    await _login(client, "parent", "parent123")
    leo = await _login(client, "leo", "leo")

    bank = WordList(
        parent_id=1,
        name="Family word bank",
        source="bank",
        is_active=True,
    )
    db_session.add(bank)
    await db_session.flush()

    for idx, (word, category) in enumerate(
        [("apple", "Food"), ("banana", "Food"), ("cat", "Animals / nature")]
    ):
        entry = DictionaryEntry(word=word, definition=f"def {word}", source="manual")
        db_session.add(entry)
        await db_session.flush()
        item = WordListItem(
            word_list_id=bank.id,
            dictionary_entry_id=entry.id,
            sort_order=idx,
            level="A1",
        )
        db_session.add(item)
        await db_session.flush()
        db_session.add(WordListItemCategory(word_list_item_id=item.id, category=category))
    await db_session.commit()

    response = await client.get(
        "/api/v1/loop/quests",
        headers={"Authorization": f"Bearer {leo}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["packs"]) == 2
    assert "packs_by_level" in data
    assert len(data["packs_by_level"]["Overall"]) == 2
    assert "A1" in data["packs_by_level"]
    assert "overall" in data
    assert data["overall"]["bank_total"] == 3
    assert len(data["levels"]) == 1
    assert "readiness_score" in data["levels"][0]
    assert 0 <= data["levels"][0]["readiness_score"] <= 1
    assert len(data["levels"][0]["milestones"]) == 3
    food_pack = next(p for p in data["packs"] if p["slug"] == "food")
    assert food_pack["total_words"] == 2


@pytest.mark.asyncio
async def test_milestone_badge_awarded_for_explorer(client, db_session) -> None:
    from sqlalchemy import select

    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    bank = WordList(parent_id=1, name="Bank", source="bank", is_active=True)
    db_session.add(bank)
    await db_session.flush()

    now = datetime.now(UTC)
    for i in range(10):
        entry = DictionaryEntry(word=f"word{i}", definition="x", source="manual")
        db_session.add(entry)
        await db_session.flush()
        item = WordListItem(
            word_list_id=bank.id,
            dictionary_entry_id=entry.id,
            sort_order=i,
            level="A1",
        )
        db_session.add(item)
        await db_session.flush()
        db_session.add(WordListItemCategory(word_list_item_id=item.id, category="General"))
        db_session.add(
            SrsCard(
                learner_id=learner.id,
                dictionary_entry_id=entry.id,
                word_list_id=bank.id,
                ease_factor=DEFAULT_EASE_FACTOR,
                interval_days=0,
                repetitions=0,
                due_at=now,
                state="new",
                released_at=now,
            )
        )
    await db_session.commit()

    earned = await achievement_service.sync_achievements(db_session, learner=learner, parent_id=1)
    assert "a1_explorer" in earned


async def _add_familiar_card(
    db_session,
    *,
    learner_id: int,
    bank_id: int,
    word: str,
    level: str,
    category: str,
    now: datetime,
) -> SrsCard:
    entry = DictionaryEntry(word=word, definition=f"def {word}", source="manual")
    db_session.add(entry)
    await db_session.flush()
    item = WordListItem(
        word_list_id=bank_id,
        dictionary_entry_id=entry.id,
        sort_order=0,
        level=level,
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(WordListItemCategory(word_list_item_id=item.id, category=category))
    card = SrsCard(
        learner_id=learner_id,
        dictionary_entry_id=entry.id,
        word_list_id=bank_id,
        ease_factor=DEFAULT_EASE_FACTOR,
        interval_days=30,
        repetitions=3,
        due_at=now + timedelta(days=10),
        state="review",
        released_at=now - timedelta(days=5),
    )
    db_session.add(card)
    await db_session.flush()
    for day_offset in (2, 1):
        db_session.add(
            SrsReviewLog(
                srs_card_id=card.id,
                learner_id=learner_id,
                quality=4,
                reviewed_at=now - timedelta(days=day_offset),
            )
        )
    return card


@pytest.mark.asyncio
async def test_quests_multi_level_strength_and_pack_counts(client, db_session) -> None:
    from sqlalchemy import select

    leo = await _login(client, "leo", "leo")
    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()

    bank = WordList(
        parent_id=1,
        name="Family word bank",
        source="bank",
        is_active=True,
    )
    db_session.add(bank)
    await db_session.flush()

    now = datetime.now(UTC)

    for word in ["prea1a", "prea1b", "prea1c"]:
        await _add_familiar_card(
            db_session,
            learner_id=learner.id,
            bank_id=bank.id,
            word=word,
            level="PRE-A1",
            category="Food",
            now=now,
        )
        # bump sort_order via separate learning-only A1 words below

    for idx, word in enumerate(["a1a", "a1b"], start=3):
        entry = DictionaryEntry(word=word, definition=f"def {word}", source="manual")
        db_session.add(entry)
        await db_session.flush()
        item = WordListItem(
            word_list_id=bank.id,
            dictionary_entry_id=entry.id,
            sort_order=idx,
            level="A1",
        )
        db_session.add(item)
        await db_session.flush()
        db_session.add(WordListItemCategory(word_list_item_id=item.id, category="General"))
        db_session.add(
            SrsCard(
                learner_id=learner.id,
                dictionary_entry_id=entry.id,
                word_list_id=bank.id,
                ease_factor=DEFAULT_EASE_FACTOR,
                interval_days=0,
                repetitions=0,
                due_at=now,
                state="new",
                released_at=now,
            )
        )
    await db_session.commit()

    response = await client.get(
        "/api/v1/loop/quests",
        headers={"Authorization": f"Bearer {leo}"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["overall"]["familiar"] >= 3

    a1_level = next(level for level in data["levels"] if level["level"] == "A1")
    pre_level = next(level for level in data["levels"] if level["level"] == "PRE-A1")

    a1_captain = next(m for m in a1_level["milestones"] if m["tier"] == "captain")
    pre_captain = next(m for m in pre_level["milestones"] if m["tier"] == "captain")
    assert a1_captain["current"] == 0
    assert pre_captain["current"] >= 3

    food_pack = next(p for p in data["packs"] if p["slug"] == "food")
    assert food_pack["strong_words"] >= 3
