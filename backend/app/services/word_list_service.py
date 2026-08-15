from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.user import User
from app.models.word_list import WordList, WordListAssignment, WordListItem
from app.services import dictionary_service


async def _get_assignments_map(db: AsyncSession, list_ids: list[int]) -> dict[int, list[int]]:
    if not list_ids:
        return {}
    result = await db.execute(
        select(WordListAssignment.word_list_id, WordListAssignment.learner_id).where(
            WordListAssignment.word_list_id.in_(list_ids),
            WordListAssignment.is_active.is_(True),
        )
    )
    mapping: dict[int, list[int]] = {list_id: [] for list_id in list_ids}
    for word_list_id, learner_id in result.all():
        mapping[word_list_id].append(learner_id)
    return mapping


async def _item_counts(db: AsyncSession, list_ids: list[int]) -> dict[int, int]:
    if not list_ids:
        return {}
    result = await db.execute(
        select(WordListItem.word_list_id, func.count(WordListItem.id))
        .where(WordListItem.word_list_id.in_(list_ids))
        .group_by(WordListItem.word_list_id)
    )
    return dict(result.all())


def entry_summary(entry: DictionaryEntry) -> dict:
    return {
        "id": entry.id,
        "word": entry.word,
        "definition": entry.definition,
        "definition_zh_hant": entry.definition_zh_hant,
        "part_of_speech": entry.part_of_speech,
        "phonetic": entry.phonetic,
        "has_audio": entry.audio_path is not None,
    }


def list_to_summary(
    word_list: WordList,
    *,
    item_count: int,
    assigned_learner_ids: list[int] | None = None,
    due_date: date | None = None,
) -> dict:
    data = {
        "id": word_list.id,
        "name": word_list.name,
        "description": word_list.description,
        "level_tag": word_list.level_tag,
        "source": word_list.source,
        "source_url": word_list.source_url,
        "is_active": word_list.is_active,
        "item_count": item_count,
        "assigned_learner_ids": assigned_learner_ids or [],
        "created_by_learner_id": word_list.created_by_learner_id,
        "created_at": word_list.created_at,
        "updated_at": word_list.updated_at,
    }
    if due_date is not None:
        data["due_date"] = due_date
    return data


def list_to_detail(
    word_list: WordList, *, item_count: int, assigned_learner_ids: list[int]
) -> dict:
    items = []
    for item in sorted(word_list.items, key=lambda row: (row.sort_order, row.id)):
        items.append(
            {
                "id": item.id,
                "sort_order": item.sort_order,
                "notes": item.notes,
                "dictionary_entry": entry_summary(item.dictionary_entry),
            }
        )
    return {
        **list_to_summary(
            word_list, item_count=item_count, assigned_learner_ids=assigned_learner_ids
        ),
        "items": items,
    }


async def list_parent_word_lists(db: AsyncSession, parent_id: int) -> list[dict]:
    result = await db.execute(
        select(WordList).where(WordList.parent_id == parent_id).order_by(WordList.name)
    )
    word_lists = result.scalars().all()
    list_ids = [word_list.id for word_list in word_lists]
    counts = await _item_counts(db, list_ids)
    assignments = await _get_assignments_map(db, list_ids)
    return [
        list_to_summary(
            word_list,
            item_count=counts.get(word_list.id, 0),
            assigned_learner_ids=assignments.get(word_list.id, []),
        )
        for word_list in word_lists
    ]


async def create_word_list(
    db: AsyncSession,
    *,
    parent_id: int,
    name: str,
    description: str | None = None,
    level_tag: str | None = None,
    source: str = "custom",
    source_url: str | None = None,
) -> WordList:
    word_list = WordList(
        parent_id=parent_id,
        name=name.strip(),
        description=description,
        level_tag=level_tag,
        source=source,
        source_url=source_url,
        is_active=True,
    )
    db.add(word_list)
    await db.commit()
    await db.refresh(word_list)
    return word_list


async def create_learner_word_list(
    db: AsyncSession,
    *,
    learner_id: int,
    parent_id: int,
    name: str,
    description: str | None = None,
    level_tag: str | None = None,
) -> WordList:
    word_list = WordList(
        parent_id=parent_id,
        name=name.strip(),
        description=description,
        level_tag=level_tag,
        source="learner",
        is_active=True,
        created_by_learner_id=learner_id,
    )
    db.add(word_list)
    await db.flush()

    assignment = WordListAssignment(
        word_list_id=word_list.id,
        learner_id=learner_id,
        is_active=True,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(word_list)
    return word_list


async def get_parent_word_list(db: AsyncSession, list_id: int, parent_id: int) -> WordList:
    result = await db.execute(
        select(WordList)
        .options(
            selectinload(WordList.items).selectinload(WordListItem.dictionary_entry),
        )
        .where(WordList.id == list_id, WordList.parent_id == parent_id)
    )
    word_list = result.scalar_one_or_none()
    if word_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word list not found")
    return word_list


async def get_word_list_for_learner(db: AsyncSession, list_id: int, learner_id: int) -> WordList:
    assignment = await db.execute(
        select(WordListAssignment).where(
            WordListAssignment.word_list_id == list_id,
            WordListAssignment.learner_id == learner_id,
            WordListAssignment.is_active.is_(True),
        )
    )
    if assignment.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word list not found")

    result = await db.execute(
        select(WordList)
        .options(
            selectinload(WordList.items).selectinload(WordListItem.dictionary_entry),
        )
        .where(WordList.id == list_id)
    )
    word_list = result.scalar_one_or_none()
    if word_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word list not found")
    return word_list


async def get_learner_owned_word_list(db: AsyncSession, list_id: int, learner_id: int) -> WordList:
    result = await db.execute(
        select(WordList)
        .options(
            selectinload(WordList.items).selectinload(WordListItem.dictionary_entry),
        )
        .where(
            WordList.id == list_id,
            WordList.created_by_learner_id == learner_id,
            WordList.source == "learner",
        )
    )
    word_list = result.scalar_one_or_none()
    if word_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word list not found")
    return word_list


async def get_word_list_detail_for_parent(db: AsyncSession, list_id: int, parent_id: int) -> dict:
    word_list = await get_parent_word_list(db, list_id, parent_id)
    counts = await _item_counts(db, [word_list.id])
    assignments = await _get_assignments_map(db, [word_list.id])
    return list_to_detail(
        word_list,
        item_count=counts.get(word_list.id, 0),
        assigned_learner_ids=assignments.get(word_list.id, []),
    )


async def get_word_list_detail_for_learner(db: AsyncSession, list_id: int, learner_id: int) -> dict:
    word_list = await get_word_list_for_learner(db, list_id, learner_id)
    counts = await _item_counts(db, [word_list.id])
    return list_to_detail(
        word_list, item_count=counts.get(word_list.id, 0), assigned_learner_ids=[]
    )


async def update_word_list(
    db: AsyncSession,
    word_list: WordList,
    *,
    name: str | None = None,
    description: str | None = None,
    level_tag: str | None = None,
    is_active: bool | None = None,
) -> WordList:
    if name is not None:
        word_list.name = name.strip()
    if description is not None:
        word_list.description = description
    if level_tag is not None:
        word_list.level_tag = level_tag
    if is_active is not None:
        word_list.is_active = is_active
    await db.commit()
    await db.refresh(word_list)
    return word_list


async def delete_word_list(db: AsyncSession, word_list: WordList) -> None:
    await db.delete(word_list)
    await db.commit()


async def add_word_to_list(
    db: AsyncSession,
    word_list: WordList,
    *,
    word: str,
    notes: str | None = None,
    sort_order: int | None = None,
) -> WordListItem:
    entry = await dictionary_service.lookup_word(db, word)
    existing = await db.execute(
        select(WordListItem).where(
            WordListItem.word_list_id == word_list.id,
            WordListItem.dictionary_entry_id == entry.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_WORD", "message": "Word already in list"},
        )

    if sort_order is None:
        result = await db.execute(
            select(func.max(WordListItem.sort_order)).where(
                WordListItem.word_list_id == word_list.id
            )
        )
        max_order = result.scalar_one_or_none()
        sort_order = (max_order or 0) + 1

    item = WordListItem(
        word_list_id=word_list.id,
        dictionary_entry_id=entry.id,
        sort_order=sort_order,
        notes=notes,
    )
    db.add(item)
    await db.commit()
    result = await db.execute(
        select(WordListItem)
        .options(selectinload(WordListItem.dictionary_entry))
        .where(WordListItem.id == item.id)
    )
    loaded = result.scalar_one()
    if loaded.dictionary_entry is None:
        loaded.dictionary_entry = entry
    return loaded


async def remove_word_from_list(db: AsyncSession, word_list: WordList, item_id: int) -> None:
    result = await db.execute(
        select(WordListItem).where(
            WordListItem.id == item_id,
            WordListItem.word_list_id == word_list.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    await db.delete(item)
    await db.commit()


async def _verify_parent_learners(
    db: AsyncSession, parent_id: int, learner_ids: list[int]
) -> list[Learner]:
    result = await db.execute(
        select(Learner)
        .join(User, Learner.user_id == User.id)
        .where(Learner.id.in_(learner_ids), User.parent_id == parent_id)
    )
    learners = result.scalars().all()
    if len(learners) != len(set(learner_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learner not found")
    return learners


async def assign_word_list(
    db: AsyncSession,
    word_list: WordList,
    *,
    parent_id: int,
    learner_ids: list[int],
    due_date: date | None = None,
) -> list[WordListAssignment]:
    await _verify_parent_learners(db, parent_id, learner_ids)
    created: list[WordListAssignment] = []
    for learner_id in learner_ids:
        result = await db.execute(
            select(WordListAssignment).where(
                WordListAssignment.word_list_id == word_list.id,
                WordListAssignment.learner_id == learner_id,
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment is None:
            assignment = WordListAssignment(
                word_list_id=word_list.id,
                learner_id=learner_id,
                due_date=due_date,
                is_active=True,
            )
            db.add(assignment)
        else:
            assignment.is_active = True
            assignment.due_date = due_date
            assignment.assigned_at = datetime.now(UTC)
        created.append(assignment)
    await db.commit()
    for assignment in created:
        await db.refresh(assignment)
    return created


async def unassign_word_list(
    db: AsyncSession, word_list: WordList, learner_id: int, parent_id: int
) -> None:
    await _verify_parent_learners(db, parent_id, [learner_id])
    result = await db.execute(
        select(WordListAssignment).where(
            WordListAssignment.word_list_id == word_list.id,
            WordListAssignment.learner_id == learner_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    assignment.is_active = False
    await db.commit()


async def list_assigned_for_learner(db: AsyncSession, learner_id: int) -> list[dict]:
    result = await db.execute(
        select(WordList, WordListAssignment.due_date)
        .join(WordListAssignment, WordListAssignment.word_list_id == WordList.id)
        .where(
            WordListAssignment.learner_id == learner_id,
            WordListAssignment.is_active.is_(True),
            WordList.is_active.is_(True),
        )
        .order_by(WordList.name)
    )
    rows = result.all()
    list_ids = [word_list.id for word_list, _ in rows]
    counts = await _item_counts(db, list_ids)
    return [
        list_to_summary(
            word_list,
            item_count=counts.get(word_list.id, 0),
            due_date=due_date,
        )
        for word_list, due_date in rows
    ]


async def list_catalog(db: AsyncSession, level: str | None = None) -> list[dict]:
    query = select(WordList).where(WordList.source == "curated", WordList.is_active.is_(True))
    if level:
        query = query.where(WordList.level_tag == level.upper())
    query = query.order_by(WordList.level_tag, WordList.name)
    result = await db.execute(query)
    word_lists = result.scalars().all()
    list_ids = [word_list.id for word_list in word_lists]
    counts = await _item_counts(db, list_ids)
    return [
        list_to_summary(word_list, item_count=counts.get(word_list.id, 0))
        for word_list in word_lists
    ]
