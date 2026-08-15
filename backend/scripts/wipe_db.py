"""Delete all application data from the configured SQLite database."""

import asyncio

from sqlalchemy import text

from app.database import AsyncSessionLocal, engine

TABLES = [
    "daily_challenge_logs",
    "srs_review_log",
    "srs_cards",
    "word_list_item_categories",
    "word_list_items",
    "word_list_assignments",
    "word_lists",
    "mistake_log",
    "dictation_attempts",
    "dictation_sessions",
    "level_assessments",
    "level_challenges",
    "learner_badges",
    "refresh_tokens",
    "learners",
    "users",
    "dictionary_entries",
]


async def wipe() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("PRAGMA foreign_keys = OFF"))
        for table in TABLES:
            await db.execute(text(f"DELETE FROM {table}"))
        await db.commit()
    await engine.dispose()
    print("Database wiped.")


if __name__ == "__main__":
    asyncio.run(wipe())
