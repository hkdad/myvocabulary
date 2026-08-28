"""Remove stale book uploads, fill jobs, and orphan placeholder dictionary data.

Keeps the family word bank and seeded users intact. Safe to re-run after deleting a book.
"""

from __future__ import annotations

import asyncio
import shutil

from sqlalchemy import delete, exists, not_, or_, select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.book import Book, BookLemma
from app.models.definition_fill_job import DefinitionFillJob
from app.models.dictation import DictationAttempt
from app.models.dictionary import DictionaryEntry
from app.models.srs import SrsCard
from app.models.word_list import MistakeLog, WordListItem


def _placeholder_filter():
    return or_(
        DictionaryEntry.source == "placeholder",
        DictionaryEntry.definition.like("Definition pending%"),
    )


def _not_in_word_bank():
    return not_(exists().where(WordListItem.dictionary_entry_id == DictionaryEntry.id))


async def cleanup_orphan_book_data() -> dict[str, int]:
    stats = {
        "fill_jobs": 0,
        "books": 0,
        "book_lemmas": 0,
        "srs_cards": 0,
        "dictation_attempts": 0,
        "mistake_log": 0,
        "dictionary_entries": 0,
        "book_upload_dirs": 0,
    }

    async with AsyncSessionLocal() as db:
        orphan_ids = list(
            (
                await db.execute(
                    select(DictionaryEntry.id).where(_placeholder_filter(), _not_in_word_bank())
                )
            ).scalars()
        )

        if orphan_ids:
            srs_result = await db.execute(
                delete(SrsCard).where(SrsCard.dictionary_entry_id.in_(orphan_ids))
            )
            stats["srs_cards"] = srs_result.rowcount or 0

            attempt_result = await db.execute(
                delete(DictationAttempt).where(
                    DictationAttempt.dictionary_entry_id.in_(orphan_ids)
                )
            )
            stats["dictation_attempts"] = attempt_result.rowcount or 0

            mistake_result = await db.execute(
                delete(MistakeLog).where(MistakeLog.dictionary_entry_id.in_(orphan_ids))
            )
            stats["mistake_log"] = mistake_result.rowcount or 0

            entry_result = await db.execute(
                delete(DictionaryEntry).where(DictionaryEntry.id.in_(orphan_ids))
            )
            stats["dictionary_entries"] = entry_result.rowcount or 0

        lemma_result = await db.execute(delete(BookLemma))
        stats["book_lemmas"] = lemma_result.rowcount or 0

        book_result = await db.execute(delete(Book))
        stats["books"] = book_result.rowcount or 0

        job_result = await db.execute(delete(DefinitionFillJob))
        stats["fill_jobs"] = job_result.rowcount or 0

        await db.commit()

    books_dir = get_settings().books_dir
    if books_dir.exists():
        for child in books_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
                stats["book_upload_dirs"] += 1

    return stats


async def main() -> None:
    stats = await cleanup_orphan_book_data()
    print("Cleanup complete:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
