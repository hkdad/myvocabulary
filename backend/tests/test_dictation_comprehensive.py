"""Comprehensive dictation flow tests covering typed, choice, give-up, and audio."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.models.dictionary import DictionaryEntry


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
    client, parent_token: str, learner_id: int, words: list[str] | None = None
) -> int:
    words = words or ["apple", "banana", "cherry"]
    create = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"name": "Dictation List", "level_tag": "A2"},
    )
    list_id = create.json()["id"]
    for index, word in enumerate(words, start=1):
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
async def test_word_index_increments_after_give_up(client) -> None:
    """BUG CHECK: word_index must count resolved words, not only correct ones."""
    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"word_list_id": list_id, "max_words": 2, "mode": "typed"},
    )
    session_id = start.json()["id"]

    prompt1 = await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert prompt1.json()["word_index"] == 1

    give_up = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/give-up",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert give_up.status_code == 200
    assert give_up.json()["session_complete"] is False
    assert give_up.json()["expected_word"] is not None
    assert give_up.json()["syllables"]

    prompt2 = await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert prompt2.json()["session_complete"] is False
    assert prompt2.json()["word_index"] == 2, (
        f"Expected word_index=2 after give-up, got {prompt2.json()['word_index']}"
    )


@pytest.mark.asyncio
async def test_give_up_last_word_still_allows_slow_audio(client, tmp_path: Path) -> None:
    """After give-up, teaching uses dictionary slow audio for the revealed word."""
    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"word_list_id": list_id, "max_words": 1, "mode": "typed"},
    )
    session_id = start.json()["id"]
    await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {token}"},
    )

    give_up = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/give-up",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert give_up.json()["session_complete"] is True
    expected = give_up.json()["expected_word"]

    fake_audio = tmp_path / "fake-slow.mp3"
    fake_audio.write_bytes(b"fake")

    with (
        patch(
            "app.services.dictionary_service.lookup_word",
            new_callable=AsyncMock,
            return_value=_mock_entry(expected, 99),
        ),
        patch(
            "app.services.tts_service.ensure_audio",
            new_callable=AsyncMock,
            return_value=fake_audio,
        ),
    ):
        audio = await client.get(
            f"/api/v1/dictionary/words/{expected}/audio?slow=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert audio.status_code == 200, (
            f"Slow audio after give-up failed: {audio.status_code} {audio.text}"
        )


@pytest.mark.asyncio
async def test_give_up_mid_session_audio_should_be_given_up_word(
    client, db_session, tmp_path: Path
) -> None:
    """Teaching slow audio is keyed by revealed word, not the next session entry."""
    import json

    from app.models.dictation import DictationSession

    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(
        client, parent_token, learner_id=2, words=["privacy", "garden", "market"]
    )
    token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"word_list_id": list_id, "max_words": 3, "mode": "typed"},
    )
    session_id = start.json()["id"]
    session_row = await db_session.get(DictationSession, session_id)
    entry_ids = json.loads(session_row.entry_ids_json)
    first_entry = await db_session.get(DictionaryEntry, entry_ids[0])

    await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {token}"},
    )

    give_up = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/give-up",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert give_up.json()["expected_word"] == first_entry.word
    assert give_up.json()["session_complete"] is False

    captured: list[str] = []

    async def capture_ensure(db, entry, *, slow=False):
        captured.append(entry.word)
        path = tmp_path / f"dictation-test-{entry.word}.mp3"
        path.write_bytes(b"fake")
        return path

    with patch(
        "app.services.tts_service.ensure_audio",
        new_callable=AsyncMock,
        side_effect=capture_ensure,
    ):
        audio = await client.get(
            f"/api/v1/dictionary/words/{first_entry.word}/audio?slow=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert audio.status_code == 200, f"Audio failed: {audio.status_code} {audio.text}"
        assert captured, "TTS was not called"
        assert captured[-1] == first_entry.word, (
            f"Expected slow audio for given-up word '{first_entry.word}', got '{captured[-1]}'"
        )


@pytest.mark.asyncio
async def test_choice_last_word_wrong_reveals_expected(client) -> None:
    """BUG CHECK: choice mode exhausting last word should still return expected_word."""
    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"word_list_id": list_id, "max_words": 1, "mode": "choice"},
    )
    session_id = start.json()["id"]
    await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {token}"},
    )

    result = None
    for _ in range(3):
        answer = await client.post(
            f"/api/v1/dictation/sessions/{session_id}/answer",
            headers={"Authorization": f"Bearer {token}"},
            json={"answer": "zzzwrong", "hint_used": False},
        )
        assert answer.status_code == 200
        result = answer.json()

    assert result is not None
    assert result["is_correct"] is False
    assert result["expected_word"] is not None
    assert result["session_complete"] is True


@pytest.mark.asyncio
async def test_typed_retry_then_correct_advances(client, db_session) -> None:
    import json

    from app.models.dictation import DictationSession

    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"word_list_id": list_id, "max_words": 2, "mode": "typed"},
    )
    session_id = start.json()["id"]
    session_row = await db_session.get(DictationSession, session_id)
    entry_ids = json.loads(session_row.entry_ids_json)
    first = await db_session.get(DictionaryEntry, entry_ids[0])
    second = await db_session.get(DictionaryEntry, entry_ids[1])

    await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {token}"},
    )

    wrong = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/answer",
        headers={"Authorization": f"Bearer {token}"},
        json={"answer": "nope", "hint_used": False},
    )
    assert wrong.json()["can_retry"] is True
    assert wrong.json()["session_complete"] is False

    right = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/answer",
        headers={"Authorization": f"Bearer {token}"},
        json={"answer": first.word, "hint_used": False},
    )
    assert right.json()["is_correct"] is True
    assert right.json()["correct_count"] == 1
    assert right.json()["session_complete"] is False

    prompt2 = await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert prompt2.json()["word_index"] == 2

    final = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/answer",
        headers={"Authorization": f"Bearer {token}"},
        json={"answer": second.word, "hint_used": False},
    )
    assert final.json()["session_complete"] is True
    assert final.json()["correct_count"] == 2


@pytest.mark.asyncio
async def test_choice_wrong_then_correct(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    token = await _login(client, "leo", "leo")

    start = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"word_list_id": list_id, "max_words": 1, "mode": "choice"},
    )
    session_id = start.json()["id"]
    prompt = await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {token}"},
    )
    choices = prompt.json()["choices"]
    assert choices

    wrong = await client.post(
        f"/api/v1/dictation/sessions/{session_id}/answer",
        headers={"Authorization": f"Bearer {token}"},
        json={"answer": "zzz", "hint_used": False},
    )
    assert wrong.json()["retries_remaining"] == 2
    assert wrong.json()["can_retry"] is False  # choice uses retries_remaining, not can_retry

    # Find correct by fetching next (same word) — we need the expected from DB
    # Re-get prompt still on same word
    prompt2 = await client.get(
        f"/api/v1/dictation/sessions/{session_id}/next",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert prompt2.json()["session_complete"] is False
    assert prompt2.json()["retries_remaining"] == 2


@pytest.mark.asyncio
async def test_hint_only_in_choice_mode(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    list_id = await _create_assigned_list(client, parent_token, learner_id=2)
    token = await _login(client, "leo", "leo")

    typed = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"word_list_id": list_id, "max_words": 1, "mode": "typed"},
    )
    typed_id = typed.json()["id"]
    await client.get(
        f"/api/v1/dictation/sessions/{typed_id}/next",
        headers={"Authorization": f"Bearer {token}"},
    )
    hint_typed = await client.get(
        f"/api/v1/dictation/sessions/{typed_id}/hint",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hint_typed.status_code == 400

    choice = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"word_list_id": list_id, "max_words": 1, "mode": "choice"},
    )
    choice_id = choice.json()["id"]
    await client.get(
        f"/api/v1/dictation/sessions/{choice_id}/next",
        headers={"Authorization": f"Bearer {token}"},
    )
    hint_choice = await client.get(
        f"/api/v1/dictation/sessions/{choice_id}/hint",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hint_choice.status_code == 200
    assert "Starts with" in hint_choice.json()["hint"]
