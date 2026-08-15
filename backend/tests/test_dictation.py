from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.dictionary import DictionaryEntry
from app.models.srs import SrsCard
from app.models.word_list import MistakeLog


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


async def _create_assigned_list(client, parent_token: str, learner_id: int) -> int:
    create = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"name": "Dictation List", "level_tag": "A2"},
    )
    list_id = create.json()["id"]
    for index, word in enumerate(["apple", "banana", "cherry"], start=1):
        with patch(
            "app.services.word_list_service.dictionary_service.lookup_word",
            new_callable=AsyncMock,
            return_value=_mock_entry(word, index + 10),
        ):
            await client.post(
                f"/api/v1/word-lists/{list_id}/items",
                headers={"Authorization": f"Bearer {parent_token}"},
                json={"word": word},
            )
    await client.post(
        f"/api/v1/word-lists/{list_id}/assign",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"learner_ids": [learner_id]},
    )
    return list_id


@pytest.mark.asyncio
async def test_choice_mode_dictation(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"word_list_id": list_id, "mode": "choice"},
    )
    assert start.status_code == 201
    session = start.json()
    assert session["mode"] == "choice"
    assert session["ui_mode_snapshot"] == "kid"
    assert session["total_words"] == 3

    prompt = await client.get(
        f"/api/v1/dictation/sessions/{session['id']}/next",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert prompt.status_code == 200
    payload = prompt.json()
    assert payload["choices"] is not None
    assert 2 <= len(payload["choices"]) <= 4
    assert payload["retries_remaining"] == 3


@pytest.mark.asyncio
async def test_default_typed_mode_dictation(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=1)
    mia_token = await _login(client, "mia", "mia")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {mia_token}"},
        json={"word_list_id": list_id},
    )
    assert start.status_code == 201
    session = start.json()
    assert session["mode"] == "typed"
    assert session["ui_mode_snapshot"] == "teen"

    prompt = await client.get(
        f"/api/v1/dictation/sessions/{session['id']}/next",
        headers={"Authorization": f"Bearer {mia_token}"},
    )
    assert prompt.json()["choices"] is None


@pytest.mark.asyncio
async def test_wrong_answer_logged_to_mistakes_and_review_queue(client, db_session) -> None:
    import json

    from app.models.dictation import DictationSession

    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"word_list_id": list_id, "max_words": 1, "mode": "choice"},
    )
    session_id = start.json()["id"]
    await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    for _ in range(3):
        answer = await client.post(
            f"/api/v1/dictation/sessions/{session_id}/answer",
            headers={"Authorization": f"Bearer {leo_token}"},
            json={"answer": "zzzinvalid", "hint_used": False},
        )
    assert answer.status_code == 200
    result = answer.json()
    assert result["is_correct"] is False
    assert result["expected_word"] is not None
    assert result["session_complete"] is True

    session_row = await db_session.get(DictationSession, session_id)
    entry_id = json.loads(session_row.entry_ids_json)[0]

    mistakes = await db_session.execute(
        select(MistakeLog).where(
            MistakeLog.learner_id == 2,
            MistakeLog.context == "dictation",
            MistakeLog.dictionary_entry_id == entry_id,
        )
    )
    assert mistakes.scalar_one_or_none() is not None

    cards = await db_session.execute(
        select(SrsCard).where(SrsCard.learner_id == 2, SrsCard.dictionary_entry_id == entry_id)
    )
    assert cards.scalar_one_or_none() is not None

    due = await client.get(
        "/api/v1/reviews/due",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert due.json()["due_count"] >= 1


@pytest.mark.asyncio
async def test_session_score_at_end(client, db_session) -> None:
    import json

    from app.models.dictation import DictationSession

    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"word_list_id": list_id, "max_words": 1},
    )
    session_id = start.json()["id"]
    await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    session_row = await db_session.get(DictationSession, session_id)
    entry_id = json.loads(session_row.entry_ids_json)[0]
    entry = await db_session.get(DictionaryEntry, entry_id)

    answer = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/answer",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"answer": entry.word, "hint_used": False},
    )
    assert answer.json()["correct_count"] == 1
    assert answer.json()["session_complete"] is True

    history = await client.get(
        "/api/v1/dictation/history",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert history.status_code == 200
    assert history.json()["sessions"][0]["score_percent"] == 100.0


@pytest.mark.asyncio
async def test_typed_wrong_answer_allows_retry(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"word_list_id": list_id, "max_words": 1, "mode": "typed"},
    )
    session_id = start.json()["id"]
    await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    answer = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/answer",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"answer": "wrong", "hint_used": False},
    )
    result = answer.json()
    assert result["is_correct"] is False
    assert result["expected_word"] is None
    assert result["can_retry"] is True
    assert result["session_complete"] is False

    prompt = await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert prompt.json()["session_complete"] is False


@pytest.mark.asyncio
async def test_typed_give_up_reveals_syllables_and_completes(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"word_list_id": list_id, "max_words": 1, "mode": "typed"},
    )
    session_id = start.json()["id"]
    await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    give_up = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/give-up",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert give_up.status_code == 200
    result = give_up.json()
    assert result["expected_word"] is not None
    assert result["syllables"]
    assert len(result["syllables"]) >= 1
    assert result["session_complete"] is True


@pytest.mark.asyncio
async def test_choice_wrong_answer_decrements_retries(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"word_list_id": list_id, "max_words": 1, "mode": "choice"},
    )
    session_id = start.json()["id"]
    await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    answer = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/answer",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"answer": "wrong", "hint_used": False},
    )
    result = answer.json()
    assert result["is_correct"] is False
    assert result["expected_word"] is None
    assert result["retries_remaining"] == 2
    assert result["session_complete"] is False

    prompt = await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert prompt.json()["session_complete"] is False
    assert prompt.json()["choices"] is not None


@pytest.mark.asyncio
async def test_typed_multi_word_session_progresses(client, db_session) -> None:
    import json

    from app.models.dictation import DictationSession

    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"word_list_id": list_id, "max_words": 2, "mode": "typed"},
    )
    session_id = start.json()["id"]
    session_row = await db_session.get(DictationSession, session_id)
    entry_ids = json.loads(session_row.entry_ids_json)
    entries = [await db_session.get(DictionaryEntry, entry_id) for entry_id in entry_ids]

    await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    first = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/answer",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"answer": entries[0].word, "hint_used": False},
    )
    assert first.json()["is_correct"] is True
    assert first.json()["session_complete"] is False
    assert first.json()["correct_count"] == 1

    next_prompt = await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert next_prompt.json()["word_index"] == 2
    assert next_prompt.json()["session_complete"] is False

    second = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/answer",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"answer": entries[1].word, "hint_used": False},
    )
    assert second.json()["session_complete"] is True
    assert second.json()["correct_count"] == 2
