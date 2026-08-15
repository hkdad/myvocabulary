"""Seed dictionary entries with cached zh glosses for clear-translation e2e tests."""

import asyncio
import os
import sys
from datetime import UTC, datetime

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend"))
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.dictionary import DictionaryEntry

FIXTURE_WORD = "e2eline"
FIXTURE_WORD_PARENT = "e2elineparent"
FIXTURE_DEFINITION = "A long thin mark on a surface."
FIXTURE_ZH = "錯誤翻譯"


async def _upsert_fixture(
    db,
    *,
    word: str,
    definition: str = FIXTURE_DEFINITION,
    zh: str = FIXTURE_ZH,
) -> None:
    result = await db.execute(select(DictionaryEntry).where(DictionaryEntry.word == word))
    entry = result.scalar_one_or_none()
    if entry is None:
        entry = DictionaryEntry(
            word=word,
            part_of_speech="noun",
            definition=definition,
            example_sentence="Draw a line on the paper.",
            source="e2e",
            fetched_at=datetime.now(UTC),
            definition_zh_hant=zh,
        )
        db.add(entry)
    else:
        entry.definition = definition
        entry.part_of_speech = "noun"
        entry.example_sentence = "Draw a line on the paper."
        entry.definition_zh_hant = zh


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await _upsert_fixture(db, word=FIXTURE_WORD)
        await _upsert_fixture(db, word=FIXTURE_WORD_PARENT)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
