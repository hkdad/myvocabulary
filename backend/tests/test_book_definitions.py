from unittest.mock import AsyncMock, patch

import pytest

from app.models.dictionary import DictionaryEntry
from app.services.dictionary_service import (
    fill_placeholder_definition,
    is_placeholder_definition,
)


@pytest.mark.asyncio
async def test_fill_placeholder_uses_ollama_then_api(db_session) -> None:
    entry = DictionaryEntry(
        word="fox",
        definition="Definition pending — added from family word bank.",
        source="placeholder",
    )
    db_session.add(entry)
    await db_session.flush()
    assert is_placeholder_definition(entry)

    kid = {
        "definition": "A wild animal with a bushy tail.",
        "part_of_speech": "noun",
        "example_sentence": "The fox ran up the hill.",
        "source": "ollama",
    }
    with patch(
        "app.services.dictionary_service.generate_kid_definition",
        new=AsyncMock(return_value=kid),
    ):
        filled = await fill_placeholder_definition(db_session, entry)
    assert filled.definition == kid["definition"]
    assert filled.source == "ollama"
    assert not is_placeholder_definition(filled)


@pytest.mark.asyncio
async def test_fill_placeholder_falls_back_to_api(db_session) -> None:
    entry = DictionaryEntry(
        word="hill",
        definition="Definition pending — added from family word bank.",
        source="placeholder",
    )
    db_session.add(entry)
    await db_session.flush()
    api_payload = {
        "definition": "A small mountain.",
        "part_of_speech": "noun",
        "example_sentence": "We walked up the hill.",
        "phonetic": None,
        "source": "freedictionary",
        "source_url": None,
        "fetched_at": None,
    }
    with (
        patch(
            "app.services.dictionary_service.generate_kid_definition",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.dictionary_service.fetch_from_api",
            new=AsyncMock(return_value=api_payload),
        ),
    ):
        filled = await fill_placeholder_definition(db_session, entry)
    assert filled.definition == "A small mountain."
    assert filled.source == "freedictionary"


@pytest.mark.asyncio
async def test_fill_placeholder_repairs_truncated_ous_lemma(db_session) -> None:
    entry = DictionaryEntry(
        word="consciou",
        definition="Definition pending — added from family word bank.",
        source="placeholder",
    )
    db_session.add(entry)
    await db_session.flush()

    api_payload = {
        "definition": "Awake and aware of what is happening.",
        "part_of_speech": "adjective",
        "source": "freedictionary",
        "fetched_at": None,
    }
    fetch_mock = AsyncMock(side_effect=[Exception("bad token"), api_payload])
    with (
        patch(
            "app.services.dictionary_service.generate_kid_definition",
            new=AsyncMock(return_value=None),
        ),
        patch("app.services.dictionary_service.fetch_from_api", new=fetch_mock),
    ):
        filled = await fill_placeholder_definition(db_session, entry)

    assert filled.word == "conscious"
    assert filled.definition == api_payload["definition"]
    fetch_mock.assert_any_await("conscious")


@pytest.mark.asyncio
async def test_prefetch_challenge_definitions_respects_deadline(db_session) -> None:
    from app.services.dictionary_service import prefetch_challenge_definitions

    entries = [
        DictionaryEntry(
            word=f"word{i}",
            definition="Definition pending — added from family word bank.",
            source="placeholder",
        )
        for i in range(5)
    ]
    for entry in entries:
        db_session.add(entry)
    await db_session.flush()

    async def slow_fill(_db, entry):
        import asyncio

        await asyncio.sleep(2.0)
        entry.definition = f"Defined {entry.word}"
        entry.source = "test"
        await _db.flush()

    with patch(
        "app.services.dictionary_service.fill_placeholder_definition",
        side_effect=slow_fill,
    ):
        import asyncio

        start = asyncio.get_event_loop().time()
        await prefetch_challenge_definitions(db_session, entries)
        elapsed = asyncio.get_event_loop().time() - start

    assert elapsed < 13.0
    filled = sum(1 for entry in entries if entry.definition.startswith("Defined"))
    assert filled <= 6


@pytest.mark.asyncio
async def test_ensure_definitions_for_entry_ids(db_session) -> None:
    from app.services.dictionary_service import ensure_definitions_for_entry_ids

    entry = DictionaryEntry(
        word="argument",
        definition="Definition pending — added from family word bank.",
        source="placeholder",
    )
    db_session.add(entry)
    await db_session.flush()

    api_payload = {
        "definition": "A reason given for or against something.",
        "part_of_speech": "noun",
        "source": "freedictionary",
    }
    with (
        patch(
            "app.services.dictionary_service.generate_kid_definition",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.dictionary_service.fetch_from_api",
            new=AsyncMock(return_value=api_payload),
        ),
    ):
        items = await ensure_definitions_for_entry_ids(db_session, [entry.id])

    assert len(items) == 1
    assert items[0]["definition"] == api_payload["definition"]
    assert not is_placeholder_definition(entry)


@pytest.mark.asyncio
async def test_prefetch_challenge_definitions_commits_cache(db_session) -> None:
    from sqlalchemy import select

    from app.services.dictionary_service import prefetch_challenge_definitions

    entry = DictionaryEntry(
        word="wheel",
        definition="Definition pending — added from family word bank.",
        source="placeholder",
    )
    db_session.add(entry)
    await db_session.flush()
    entry_id = entry.id

    api_payload = {
        "definition": "A circular object that turns.",
        "part_of_speech": "noun",
        "source": "freedictionary",
        "fetched_at": None,
    }
    fetch_mock = AsyncMock(return_value=api_payload)
    with (
        patch(
            "app.services.dictionary_service.generate_kid_definition",
            new=AsyncMock(return_value=None),
        ),
        patch("app.services.dictionary_service.fetch_from_api", new=fetch_mock),
    ):
        await prefetch_challenge_definitions(db_session, [entry])

    db_session.expire_all()
    result = await db_session.execute(select(DictionaryEntry).where(DictionaryEntry.id == entry_id))
    cached = result.scalar_one()
    assert cached.definition == api_payload["definition"]
    assert cached.source == "freedictionary"
    fetch_mock.assert_awaited_once()

    with patch(
        "app.services.dictionary_service.fetch_from_api",
        new=AsyncMock(side_effect=AssertionError("should use DB cache")),
    ):
        await prefetch_challenge_definitions(db_session, [cached])
    assert cached.definition == api_payload["definition"]


@pytest.mark.asyncio
async def test_list_learner_words_fills_placeholder_definitions(db_session) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.core.sm2 import DEFAULT_EASE_FACTOR
    from app.models.learner import Learner
    from app.models.srs import SrsCard
    from app.services.loop_engine import list_learner_words

    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()

    entry = DictionaryEntry(
        word="precious",
        definition="Definition pending — added from family word bank.",
        source="placeholder",
    )
    db_session.add(entry)
    await db_session.flush()
    entry_id = entry.id
    db_session.add(
        SrsCard(
            learner_id=learner.id,
            dictionary_entry_id=entry.id,
            ease_factor=DEFAULT_EASE_FACTOR,
            interval_days=0,
            repetitions=0,
            due_at=datetime.now(UTC),
            state="new",
            released_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    api_payload = {
        "definition": "Very valuable or important.",
        "part_of_speech": "adjective",
        "source": "freedictionary",
        "fetched_at": None,
    }
    with (
        patch(
            "app.services.dictionary_service.generate_kid_definition",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.dictionary_service.fetch_from_api",
            new=AsyncMock(return_value=api_payload),
        ),
    ):
        data = await list_learner_words(
            db_session,
            learner=learner,
            parent_id=None,
            page=1,
            page_size=50,
        )

    assert data["total"] >= 1
    precious = next(item for item in data["items"] if item["word"] == "precious")
    assert precious["definition"] == api_payload["definition"]
    result = await db_session.execute(select(DictionaryEntry).where(DictionaryEntry.id == entry_id))
    cached = result.scalar_one()
    assert not is_placeholder_definition(cached)
