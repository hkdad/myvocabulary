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

    assert elapsed < 5.0
    filled = sum(1 for entry in entries if entry.definition.startswith("Defined"))
    assert filled <= 2
