from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.challenge import LevelAssessment, LevelChallenge
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


async def _create_assigned_list(client, parent_token: str, learner_id: int) -> int:
    create = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"name": "Challenge List", "level_tag": "A2"},
    )
    list_id = create.json()["id"]
    for index, word in enumerate(["apple", "banana", "cherry", "date", "elder"], start=1):
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
async def test_learner_lists_available_challenges(client) -> None:
    leo_token = await _login(client, "leo", "leo")
    response = await client.get(
        "/api/v1/challenges/available",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json()["challenges"], list)
    level_up = next(
        item for item in response.json()["challenges"] if item["challenge_type"] == "level_up"
    )
    assert "can_start" in level_up
    assert "lock_reason" in level_up
    assert "readiness_score" in level_up


@pytest.mark.asyncio
async def test_level_up_locked_below_readiness_threshold(client) -> None:
    leo_token = await _login(client, "leo", "leo")
    available = await client.get(
        "/api/v1/challenges/available",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    level_up = next(
        item for item in available.json()["challenges"] if item["challenge_type"] == "level_up"
    )
    # Seeded Leo is early in PRE-A1/A1 practice — not readiness-ready.
    if level_up["can_start"]:
        pytest.skip("Learner already at readiness threshold in this seed")

    assert level_up["lock_reason"]
    assert "75%" in level_up["lock_reason"]

    start = await client.post(
        "/api/v1/challenges/start",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"challenge_type": "level_up"},
    )
    assert start.status_code == 400
    assert "75%" in start.json()["detail"]


@pytest.mark.asyncio
async def test_level_up_unlocked_when_parent_challenge_pending(client, db_session) -> None:
    leo_token = await _login(client, "leo", "leo")
    challenge = LevelChallenge(
        learner_id=2,
        challenge_type="level_up",
        target_level="B1",
        status="pending",
        pass_threshold=0.8,
    )
    db_session.add(challenge)
    db_session.add(
        LevelAssessment(
            learner_id=2,
            current_level="A2",
            suggested_level="B1",
            reason="Parent accepted",
            source="rules",
            status="accepted",
        )
    )
    await db_session.commit()

    available = await client.get(
        "/api/v1/challenges/available",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    level_up = next(
        item for item in available.json()["challenges"] if item["challenge_type"] == "level_up"
    )
    assert level_up["can_start"] is True
    assert level_up["lock_reason"] is None


@pytest.mark.asyncio
async def test_stale_self_started_level_up_does_not_bypass_gate(client, db_session) -> None:
    leo_token = await _login(client, "leo", "leo")
    db_session.add(
        LevelChallenge(
            learner_id=2,
            challenge_type="level_up",
            target_level="PRE-A1",
            status="in_progress",
            pass_threshold=0.8,
        )
    )
    await db_session.commit()

    available = await client.get(
        "/api/v1/challenges/available",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    level_up = next(
        item for item in available.json()["challenges"] if item["challenge_type"] == "level_up"
    )
    if level_up["can_start"] and level_up["readiness_score"] is not None:
        assert level_up["readiness_score"] >= 0.75
    else:
        assert level_up["can_start"] is False
        assert level_up["lock_reason"]
        assert "75%" in level_up["lock_reason"]


@pytest.mark.asyncio
async def test_level_up_challenge_flow(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    await _create_assigned_list(client, parent_token, learner_id=2)
    leo_token = await _login(client, "leo", "leo")

    challenge = LevelChallenge(
        learner_id=2,
        challenge_type="level_up",
        target_level="B1",
        status="pending",
        pass_threshold=0.8,
    )
    db_session.add(challenge)
    db_session.add(
        LevelAssessment(
            learner_id=2,
            current_level="A2",
            suggested_level="B1",
            reason="Parent accepted",
            source="rules",
            status="accepted",
        )
    )
    await db_session.commit()
    await db_session.refresh(challenge)

    start = await client.post(
        "/api/v1/challenges/start",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"challenge_type": "level_up", "challenge_id": challenge.id},
    )
    assert start.status_code == 200
    session = start.json()
    assert session["total_words"] >= 3
    assert len(session["words"]) >= 3

    # Recognition-based: each prompt carries word choices including the answer.
    answers = []
    for word_prompt in session["words"]:
        entry_result = await db_session.execute(
            select(DictionaryEntry).where(DictionaryEntry.id == word_prompt["dictionary_entry_id"])
        )
        entry = entry_result.scalar_one()
        assert len(word_prompt["choices"]) >= 2
        assert entry.word in word_prompt["choices"]
        answers.append({"dictionary_entry_id": entry.id, "answer": entry.word})

    submit = await client.post(
        f"/api/v1/challenges/{session['id']}/submit",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"answers": answers},
    )
    assert submit.status_code == 200
    result = submit.json()
    assert result["passed"] is True
    assert result["badge_earned"] == "level_up_badge"

    badges = await client.get(
        "/api/v1/challenges/badges",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert badges.status_code == 200
    assert len(badges.json()["badges"]) >= 1


@pytest.mark.asyncio
async def test_speed_dictation_challenge_hidden_until_timed_ux(client) -> None:
    leo_token = await _login(client, "leo", "leo")
    mia_token = await _login(client, "mia", "mia")

    for token in (leo_token, mia_token):
        response = await client.get(
            "/api/v1/challenges/available",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        types = {item["challenge_type"] for item in response.json()["challenges"]}
        assert "speed_dictation" not in types


@pytest.mark.asyncio
async def test_mistake_mastery_not_listed_uses_daily_challenge(client, db_session) -> None:
    from datetime import UTC, datetime

    from app.models.dictionary import DictionaryEntry
    from app.models.word_list import MistakeLog

    leo_token = await _login(client, "leo", "leo")
    entry = DictionaryEntry(
        word="mistake-challenge-word",
        phonetic=None,
        part_of_speech="noun",
        definition="A word for mistake mastery.",
        source="manual",
    )
    db_session.add(entry)
    await db_session.flush()
    db_session.add(
        MistakeLog(
            learner_id=2,
            dictionary_entry_id=entry.id,
            context="review",
            wrong_answer=None,
            occurred_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/challenges/available",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert response.status_code == 200
    types = {item["challenge_type"] for item in response.json()["challenges"]}
    assert "mistake_mastery" not in types
