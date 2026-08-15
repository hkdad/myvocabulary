"""Import curated word lists from data/curated/*.json into the database."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.word_list import WordList, WordListItem
from app.services import dictionary_service, word_list_service

CURATED_DIR = Path(__file__).resolve().parents[2] / "data" / "curated"


async def _ensure_entry(db, word_data: dict):
    existing = await dictionary_service.get_entry_by_word(db, word_data["word"])
    if existing:
        return existing
    try:
        return await dictionary_service.create_manual_entry(
            db,
            word=word_data["word"],
            definition=word_data["definition"],
            part_of_speech=word_data.get("part_of_speech"),
            example_sentence=word_data.get("example_sentence"),
        )
    except Exception:
        return await dictionary_service.lookup_word(db, word_data["word"])


async def _find_curated_list(db, parent_id: int, payload: dict) -> WordList | None:
    result = await db.execute(
        select(WordList).where(
            WordList.parent_id == parent_id,
            WordList.source == "curated",
            WordList.name == payload["name"],
            WordList.level_tag == payload["level_tag"],
        )
    )
    return result.scalar_one_or_none()


async def import_file(db, parent_id: int, path: Path) -> WordList:
    payload = json.loads(path.read_text(encoding="utf-8"))
    word_list = await _find_curated_list(db, parent_id, payload)
    if word_list is None:
        word_list = await word_list_service.create_word_list(
            db,
            parent_id=parent_id,
            name=payload["name"],
            description=payload.get("description"),
            level_tag=payload.get("level_tag"),
            source="curated",
            source_url=payload.get("source_url"),
        )
    else:
        word_list.description = payload.get("description")
        word_list.source_url = payload.get("source_url")
        await db.commit()
        await db.refresh(word_list)

    existing_items = await db.execute(
        select(WordListItem.dictionary_entry_id).where(WordListItem.word_list_id == word_list.id)
    )
    existing_entry_ids = set(existing_items.scalars().all())

    for index, word_data in enumerate(payload.get("words", []), start=1):
        entry = await _ensure_entry(db, word_data)
        if entry.id in existing_entry_ids:
            continue
        db.add(
            WordListItem(
                word_list_id=word_list.id,
                dictionary_entry_id=entry.id,
                sort_order=index,
            )
        )
        existing_entry_ids.add(entry.id)

    await db.commit()
    return word_list


async def import_curated_lists() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == "parent"))
        parent = result.scalar_one_or_none()
        if parent is None:
            print("Parent user not found. Run seed first.")
            return

        files = sorted(CURATED_DIR.glob("*.json"))
        if not files:
            print(f"No curated files found in {CURATED_DIR}")
            return

        for path in files:
            word_list = await import_file(db, parent.id, path)
            print(f"Imported curated list: {word_list.name} ({word_list.level_tag})")

    print("Curated import complete.")


if __name__ == "__main__":
    asyncio.run(import_curated_lists())
