from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.dictionary import DictionaryEntry
from app.models.srs import SrsCard


async def _login(client, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _mock_entry(word: str, entry_id: int) -> DictionaryEntry:
    return DictionaryEntry(
        id=entry_id,
        word=word,
        phonetic=None,
        part_of_speech="noun",
        definition=f"Definition of {word}",
        example_sentence=None,
        synonyms=None,
        source="manual",
        source_url=None,
        audio_path=None,
        fetched_at=None,
    )


async def _create_assigned_list(
    client, parent_token: str, learner_id: int
) -> tuple[int, list[str]]:
    create = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"name": "SRS Test List", "level_tag": "A2"},
    )
    assert create.status_code == 201
    list_id = create.json()["id"]

    words = ["apple", "banana", "cherry"]
    for index, word in enumerate(words, start=1):
        with patch(
            "app.services.word_list_service.dictionary_service.lookup_word",
            new_callable=AsyncMock,
            return_value=_mock_entry(word, index + 10),
        ):
            add = await client.post(
                f"/api/v1/word-lists/{list_id}/items",
                headers={"Authorization": f"Bearer {parent_token}"},
                json={"word": word},
            )
        assert add.status_code == 201

    assign = await client.post(
        f"/api/v1/word-lists/{list_id}/assign",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"learner_ids": [learner_id]},
    )
    assert assign.status_code == 201
    return list_id, words


@pytest.mark.asyncio
async def test_initialize_creates_srs_cards(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    leo_result = await db_session.execute(select(SrsCard).where(SrsCard.learner_id == 2))
    cards_before = len(leo_result.scalars().all())

    list_id, _ = await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    init = await client.post(
        f"/api/v1/reviews/initialize?word_list_id={list_id}",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert init.status_code == 200
    payload = init.json()
    assert payload["created_count"] == 3
    assert payload["skipped_count"] == 0
    assert payload["total_cards"] == cards_before + 3

    init_again = await client.post(
        f"/api/v1/reviews/initialize?word_list_id={list_id}",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert init_again.json()["created_count"] == 0
    assert init_again.json()["skipped_count"] == 3


@pytest.mark.asyncio
async def test_due_cards_and_answer_updates_sm2(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    leo_result = await db_session.execute(select(SrsCard).where(SrsCard.learner_id == 2))
    cards_before = len(leo_result.scalars().all())

    list_id, _ = await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    await client.post(
        f"/api/v1/reviews/initialize?word_list_id={list_id}",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    due = await client.get(
        "/api/v1/reviews/due",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert due.status_code == 200
    due_payload = due.json()
    assert due_payload["due_count"] == cards_before + 3
    assert len(due_payload["cards"]) == cards_before + 3
    first_card = due_payload["cards"][0]
    assert first_card["strength"] == "new"
    assert first_card["books"] == []
    assert "level" in first_card

    card_id = first_card["id"]
    answer = await client.post(
        f"/api/v1/reviews/{card_id}/answer",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"quality": 4},
    )
    assert answer.status_code == 200
    updated = answer.json()["card"]
    assert updated["repetitions"] == 1
    assert updated["interval_days"] == 1
    assert updated["state"] == "learning"

    stats = await client.get(
        "/api/v1/reviews/stats",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert stats.status_code == 200
    assert stats.json()["reviewed_today"] == 1
    assert stats.json()["total_cards"] == cards_before + 3


@pytest.mark.asyncio
async def test_failed_answer_resets_card(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    list_id, _ = await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    await client.post(
        f"/api/v1/reviews/initialize?word_list_id={list_id}",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    due = await client.get(
        "/api/v1/reviews/due",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    card_id = due.json()["cards"][0]["id"]

    answer = await client.post(
        f"/api/v1/reviews/{card_id}/answer",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"quality": 1},
    )
    assert answer.status_code == 200
    updated = answer.json()["card"]
    assert updated["repetitions"] == 0
    assert updated["state"] == "relearning"


@pytest.mark.asyncio
async def test_mia_and_leo_have_independent_progress(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    list_id, _ = await _create_assigned_list(client, parent_token, learner_id=2)

    assign = await client.post(
        f"/api/v1/word-lists/{list_id}/assign",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"learner_ids": [1]},
    )
    assert assign.status_code == 201

    leo_token = await _login(client, "leo", "leo")
    mia_token = await _login(client, "mia", "mia")

    leo_result = await db_session.execute(select(SrsCard).where(SrsCard.learner_id == 2))
    leo_cards_before = len(leo_result.scalars().all())

    await client.post(
        f"/api/v1/reviews/initialize?word_list_id={list_id}",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    await client.post(
        f"/api/v1/reviews/initialize?word_list_id={list_id}",
        headers={"Authorization": f"Bearer {mia_token}"},
    )

    leo_due = await client.get(
        "/api/v1/reviews/due",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    mia_due = await client.get(
        "/api/v1/reviews/due",
        headers={"Authorization": f"Bearer {mia_token}"},
    )
    assert len(leo_due.json()["cards"]) == leo_cards_before + 3
    assert len(mia_due.json()["cards"]) == 3

    leo_card_id = leo_due.json()["cards"][0]["id"]
    await client.post(
        f"/api/v1/reviews/{leo_card_id}/answer",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"quality": 5},
    )

    leo_stats = await client.get(
        "/api/v1/reviews/stats",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    mia_stats = await client.get(
        "/api/v1/reviews/stats",
        headers={"Authorization": f"Bearer {mia_token}"},
    )
    assert leo_stats.json()["reviewed_today"] == 1
    assert mia_stats.json()["reviewed_today"] == 0


@pytest.mark.asyncio
async def test_due_cards_filter_by_word_list(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    leo_token = await _login(client, "leo", "leo")

    list_a, _ = await _create_assigned_list(client, parent_token, learner_id=2)

    leo_result = await db_session.execute(select(SrsCard).where(SrsCard.learner_id == 2))
    cards_before = len(leo_result.scalars().all())

    create_b = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"name": "Second List", "level_tag": "A2"},
    )
    list_b = create_b.json()["id"]
    for index, word in enumerate(["delta", "echo"], start=10):
        with patch(
            "app.services.word_list_service.dictionary_service.lookup_word",
            new_callable=AsyncMock,
            return_value=_mock_entry(word, index + 10),
        ):
            add = await client.post(
                f"/api/v1/word-lists/{list_b}/items",
                headers={"Authorization": f"Bearer {parent_token}"},
                json={"word": word},
            )
        assert add.status_code == 201
    assign_b = await client.post(
        f"/api/v1/word-lists/{list_b}/assign",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"learner_ids": [2]},
    )
    assert assign_b.status_code == 201

    await client.post(
        f"/api/v1/reviews/initialize?word_list_id={list_a}",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    await client.post(
        f"/api/v1/reviews/initialize?word_list_id={list_b}",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    all_due = await client.get(
        "/api/v1/reviews/due",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert all_due.json()["due_count"] == cards_before + 5

    filtered = await client.get(
        f"/api/v1/reviews/due?word_list_id={list_b}",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["due_count"] == 2
    assert len(payload["cards"]) == 2
    words = {card["dictionary_entry"]["word"] for card in payload["cards"]}
    assert words == {"delta", "echo"}


@pytest.mark.asyncio
async def test_mistake_review_initialization_and_filter(client, db_session) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.dictionary import DictionaryEntry
    from app.models.srs import SrsCard
    from app.models.word_list import MistakeLog

    leo_token = await _login(client, "leo", "leo")

    entry = DictionaryEntry(
        word="mistake-word",
        phonetic=None,
        part_of_speech="noun",
        definition="A test mistake word.",
        source="manual",
    )
    db_session.add(entry)
    await db_session.flush()
    db_session.add(
        MistakeLog(
            learner_id=2,
            dictionary_entry_id=entry.id,
            context="dictation",
            wrong_answer="mistak",
            occurred_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    init = await client.post(
        "/api/v1/reviews/initialize-mistakes",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert init.status_code == 200
    assert init.json()["mistake_count"] == 1
    assert init.json()["created_count"] == 1

    due = await client.get(
        "/api/v1/reviews/due?mistakes_only=true",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert due.status_code == 200
    payload = due.json()
    assert payload["due_count"] == 1
    assert payload["cards"][0]["dictionary_entry"]["word"] == "mistake-word"

    all_due = await client.get(
        "/api/v1/reviews/due",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert all_due.json()["due_count"] >= 2

    card_result = await db_session.execute(
        select(SrsCard).where(SrsCard.learner_id == 2, SrsCard.dictionary_entry_id == entry.id)
    )
    assert card_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_mistake_challenge_caps_at_five_words(client, db_session) -> None:
    from datetime import UTC, datetime, timedelta

    from app.models.dictionary import DictionaryEntry
    from app.models.word_list import MistakeLog

    leo_token = await _login(client, "leo", "leo")
    now = datetime.now(UTC)

    for i in range(6):
        entry = DictionaryEntry(
            word=f"mistake-{i}",
            phonetic=None,
            part_of_speech="noun",
            definition=f"Mistake word {i}.",
            source="manual",
        )
        db_session.add(entry)
        await db_session.flush()
        db_session.add(
            MistakeLog(
                learner_id=2,
                dictionary_entry_id=entry.id,
                context="dictation",
                wrong_answer="wrong",
                occurred_at=now - timedelta(seconds=i),
            )
        )
    await db_session.commit()

    init = await client.post(
        "/api/v1/reviews/initialize-mistakes",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert init.status_code == 200
    assert init.json()["mistake_count"] == 5

    due = await client.get(
        "/api/v1/reviews/due?mistakes_only=true",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert due.status_code == 200
    assert len(due.json()["cards"]) <= 5


@pytest.mark.asyncio
async def test_complete_mistake_challenge_clears_mistake_log(client, db_session) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.dictionary import DictionaryEntry
    from app.models.word_list import MistakeLog

    leo_token = await _login(client, "leo", "leo")

    entry = DictionaryEntry(
        word="clear-me",
        phonetic=None,
        part_of_speech="noun",
        definition="A word to clear from mistakes.",
        source="manual",
    )
    db_session.add(entry)
    await db_session.flush()
    db_session.add(
        MistakeLog(
            learner_id=2,
            dictionary_entry_id=entry.id,
            context="dictation",
            wrong_answer="clearm",
            occurred_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    await client.post(
        "/api/v1/reviews/initialize-mistakes",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    due = await client.get(
        "/api/v1/reviews/due?mistakes_only=true",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    entry_id = due.json()["cards"][0]["dictionary_entry"]["id"]

    complete = await client.post(
        "/api/v1/reviews/mistakes/complete",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"dictionary_entry_ids": [entry_id]},
    )
    assert complete.status_code == 200
    assert complete.json()["resolved_count"] == 1
    assert complete.json()["entry_count"] == 1

    open_logs = await db_session.execute(
        select(MistakeLog).where(
            MistakeLog.learner_id == 2,
            MistakeLog.dictionary_entry_id == entry_id,
            MistakeLog.resolved_at.is_(None),
        )
    )
    assert open_logs.scalar_one_or_none() is None


async def _create_learner_school_list(
    client, learner_token: str, word_count: int, *, start_id: int = 200
) -> int:
    create = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {learner_token}"},
        json={"name": "My B1 List", "level_tag": "B1"},
    )
    assert create.status_code == 201
    list_id = create.json()["id"]
    for index in range(word_count):
        word = f"school{index}"
        with patch(
            "app.services.word_list_service.dictionary_service.lookup_word",
            new_callable=AsyncMock,
            return_value=_mock_entry(word, start_id + index),
        ):
            add = await client.post(
                f"/api/v1/word-lists/{list_id}/items",
                headers={"Authorization": f"Bearer {learner_token}"},
                json={"word": word},
            )
        assert add.status_code == 201
    return list_id


@pytest.mark.asyncio
async def test_school_list_initialize_releases_all_words(client, db_session) -> None:
    from sqlalchemy import select

    from app.models.learner import Learner
    from app.models.user import User

    mia = (
        await db_session.execute(select(Learner).join(User).where(User.username == "mia"))
    ).scalar_one()
    mia_token = await _login(client, "mia", "mia")
    list_id = await _create_learner_school_list(client, mia_token, 10)

    init = await client.post(
        f"/api/v1/reviews/initialize?word_list_id={list_id}",
        headers={"Authorization": f"Bearer {mia_token}"},
    )
    assert init.status_code == 200
    assert init.json()["created_count"] == 10

    cards_result = await db_session.execute(
        select(SrsCard).where(
            SrsCard.learner_id == mia.id,
            SrsCard.word_list_id == list_id,
        )
    )
    cards = list(cards_result.scalars().all())
    assert len(cards) == 10
    assert all(card.released_at is not None for card in cards)


@pytest.mark.asyncio
async def test_practice_all_returns_all_list_cards_even_when_not_due(client, db_session) -> None:
    mia_token = await _login(client, "mia", "mia")
    list_id = await _create_learner_school_list(client, mia_token, 8, start_id=300)

    await client.post(
        f"/api/v1/reviews/initialize?word_list_id={list_id}",
        headers={"Authorization": f"Bearer {mia_token}"},
    )
    due = await client.get(
        f"/api/v1/reviews/due?word_list_id={list_id}",
        headers={"Authorization": f"Bearer {mia_token}"},
    )
    card_id = due.json()["cards"][0]["id"]
    await client.post(
        f"/api/v1/reviews/{card_id}/answer",
        headers={"Authorization": f"Bearer {mia_token}"},
        json={"quality": 4},
    )

    due_after = await client.get(
        f"/api/v1/reviews/due?word_list_id={list_id}",
        headers={"Authorization": f"Bearer {mia_token}"},
    )
    assert len(due_after.json()["cards"]) < 8

    practice = await client.get(
        f"/api/v1/reviews/due?word_list_id={list_id}&practice_all=true",
        headers={"Authorization": f"Bearer {mia_token}"},
    )
    assert practice.status_code == 200
    assert len(practice.json()["cards"]) == 8


@pytest.mark.asyncio
async def test_practice_all_only_for_learner_owned_lists(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    list_id, _ = await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    response = await client.get(
        f"/api/v1/reviews/due?word_list_id={list_id}&practice_all=true",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert response.status_code == 404
