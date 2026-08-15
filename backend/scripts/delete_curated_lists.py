"""Remove all curated catalog word lists and linked learner SRS cards."""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, select, update

from app.database import AsyncSessionLocal
from app.models.dictation import DictationSession
from app.models.srs import SrsCard, SrsReviewLog
from app.models.word_list import WordList, WordListAssignment, WordListItem


async def delete_curated_lists() -> dict[str, int]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WordList).where(WordList.source == "curated"))
        lists = list(result.scalars().all())
        if not lists:
            print("No curated lists found.")
            return {"lists": 0, "cards": 0, "assignments": 0, "items": 0}

        list_ids = [word_list.id for word_list in lists]
        names = [word_list.name for word_list in lists]

        cards_result = await db.execute(select(SrsCard).where(SrsCard.word_list_id.in_(list_ids)))
        cards = list(cards_result.scalars().all())
        card_ids = [card.id for card in cards]

        items_result = await db.execute(
            select(WordListItem.id).where(WordListItem.word_list_id.in_(list_ids))
        )
        item_count = len(items_result.scalars().all())

        assignments_result = await db.execute(
            select(WordListAssignment.id).where(WordListAssignment.word_list_id.in_(list_ids))
        )
        assignment_count = len(assignments_result.scalars().all())

        if card_ids:
            await db.execute(delete(SrsReviewLog).where(SrsReviewLog.srs_card_id.in_(card_ids)))
            await db.execute(delete(SrsCard).where(SrsCard.id.in_(card_ids)))

        await db.execute(
            update(DictationSession)
            .where(DictationSession.word_list_id.in_(list_ids))
            .values(word_list_id=None)
        )
        await db.execute(
            delete(WordListAssignment).where(WordListAssignment.word_list_id.in_(list_ids))
        )
        await db.execute(delete(WordListItem).where(WordListItem.word_list_id.in_(list_ids)))
        await db.execute(delete(WordList).where(WordList.id.in_(list_ids)))

        await db.commit()

        print(f"Deleted curated lists: {', '.join(names)}")
        print(
            f"Removed {len(lists)} lists, {item_count} items, "
            f"{assignment_count} assignments, {len(cards)} SRS cards."
        )
        return {
            "lists": len(lists),
            "items": item_count,
            "assignments": assignment_count,
            "cards": len(cards),
        }


if __name__ == "__main__":
    asyncio.run(delete_curated_lists())
