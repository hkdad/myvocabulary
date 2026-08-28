"""Family word bank CSV import."""

from __future__ import annotations

import asyncio
import csv
import io
import re
from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.models.definition_fill_job import DefinitionFillJob
from app.models.dictation import DictationSession
from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.srs import SrsCard
from app.models.user import User
from app.models.word_list import WordList, WordListAssignment, WordListItem, WordListItemCategory
from app.services.definition_fill_utils import (
    fill_job_error_message_from_exception,
    sanitize_fill_job_error_message,
)
from app.services import dictionary_service, loop_engine
from app.services.dictionary_service import (
    fill_placeholder_definition,
    is_placeholder_definition,
    normalize_word,
)

BANK_LIST_NAME = "Family word bank"

PLACEHOLDER_DEFINITION = loop_engine.PLACEHOLDER_DEFINITION

ACTIVE_JOB_STATUSES = ("queued", "running")
FILL_PER_WORD_TIMEOUT = 8.0
FILL_COMMIT_BATCH = 10

REQUIRED_COLUMNS = ("word", "level", "category")
LEVEL_MAX_LENGTH = 32
CATEGORY_MAX_LENGTH = 64
# "and" / ";" / "," / spaced "-" (e.g. "Places - town"). Spaced hyphen avoids
# splitting hyphenated single tokens like "pre-school".
CATEGORY_SPLIT_RE = re.compile(
    r"\s+and\s+|\s*;\s*|\s*,\s*|\s+-\s+",
    re.IGNORECASE,
)
LEADING_ARTICLE_RE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)

# Casefolded alias → canonical display name. Keep this list small and obvious.
CATEGORY_ALIASES: dict[str, str] = {
    "communications": "Communication",
    "sport": "Sports",
}

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "word": ("word", "vocabulary", "term", "english"),
    "level": ("level", "cefr", "cefr_level", "grade", "difficulty"),
    "category": ("categories", "category", "topic", "theme", "tag", "subject"),
    "definition": ("definition", "meaning", "def", "translation"),
}

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 10_000


def _placeholder_entry_filter():
    return or_(
        DictionaryEntry.source == "placeholder",
        DictionaryEntry.definition.like("Definition pending%"),
    )


async def count_placeholder_entries(db: AsyncSession, parent_id: int) -> int:
    bank = await loop_engine.get_family_bank(db, parent_id)
    if bank is None:
        return 0
    result = await db.execute(
        select(func.count(WordListItem.id))
        .join(DictionaryEntry, WordListItem.dictionary_entry_id == DictionaryEntry.id)
        .where(WordListItem.word_list_id == bank.id, _placeholder_entry_filter())
    )
    return int(result.scalar_one())


async def _list_placeholder_entry_ids(db: AsyncSession, bank_id: int) -> list[int]:
    result = await db.execute(
        select(DictionaryEntry.id)
        .join(WordListItem, WordListItem.dictionary_entry_id == DictionaryEntry.id)
        .where(WordListItem.word_list_id == bank_id, _placeholder_entry_filter())
        .order_by(WordListItem.sort_order, WordListItem.id)
    )
    return list(result.scalars().all())


def job_to_dict(job: DefinitionFillJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "total": job.total,
        "processed": job.processed,
        "filled": job.filled,
        "failed": job.failed,
        "error_message": sanitize_fill_job_error_message(job.error_message),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


async def get_current_definition_fill_job(
    db: AsyncSession, parent_id: int
) -> DefinitionFillJob | None:
    result = await db.execute(
        select(DefinitionFillJob)
        .where(
            DefinitionFillJob.parent_id == parent_id,
            DefinitionFillJob.scope == "bank",
        )
        .order_by(DefinitionFillJob.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def start_definition_fill_job(db: AsyncSession, parent_id: int) -> dict:
    bank = await loop_engine.get_family_bank(db, parent_id)
    if bank is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "BANK_NOT_FOUND", "message": "No family word bank found"},
        )

    active = await db.execute(
        select(DefinitionFillJob).where(
            DefinitionFillJob.parent_id == parent_id,
            DefinitionFillJob.scope == "bank",
            DefinitionFillJob.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    if active.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "JOB_ALREADY_RUNNING",
                "message": "A definition fill job is already in progress",
            },
        )

    total = await count_placeholder_entries(db, parent_id)
    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NO_PLACEHOLDERS",
                "message": "All words already have definitions",
            },
        )

    job = DefinitionFillJob(
        parent_id=parent_id,
        scope="bank",
        bank_id=bank.id,
        status="queued",
        total=total,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    asyncio.create_task(run_definition_fill_job(job.id))
    return job_to_dict(job)


async def cancel_definition_fill_job(db: AsyncSession, parent_id: int, job_id: int) -> dict:
    job = await db.get(DefinitionFillJob, job_id)
    if job is None or job.parent_id != parent_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status not in ACTIVE_JOB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only queued or running jobs can be cancelled",
        )
    job.status = "cancelled"
    job.finished_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(job)
    return job_to_dict(job)


async def run_definition_fill_job(job_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await execute_definition_fill_job(db, job_id)


async def execute_definition_fill_job(db: AsyncSession, job_id: int) -> None:
    try:
        job = await db.get(DefinitionFillJob, job_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = datetime.now(UTC)
        await db.commit()

        entry_ids = await _list_placeholder_entry_ids(db, job.bank_id)
        job.total = len(entry_ids)
        await db.commit()

        processed = filled = failed = 0
        for entry_id in entry_ids:
            job = await db.get(DefinitionFillJob, job_id)
            if job is None or job.status == "cancelled":
                if job is not None:
                    job.finished_at = datetime.now(UTC)
                    await db.commit()
                return

            entry = await db.get(DictionaryEntry, entry_id)
            if entry is None or not is_placeholder_definition(entry):
                processed += 1
                continue

            try:
                await asyncio.wait_for(
                    fill_placeholder_definition(db, entry),
                    timeout=FILL_PER_WORD_TIMEOUT,
                )
                await db.commit()
                if not is_placeholder_definition(entry):
                    filled += 1
                else:
                    failed += 1
            except (TimeoutError, Exception):
                failed += 1

            processed += 1
            job.processed = processed
            job.filled = filled
            job.failed = failed
            await db.commit()

        job = await db.get(DefinitionFillJob, job_id)
        if job is None:
            return
        job.status = "completed"
        job.processed = processed
        job.filled = filled
        job.failed = failed
        job.finished_at = datetime.now(UTC)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        job = await db.get(DefinitionFillJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error_message = fill_job_error_message_from_exception(exc)
            job.finished_at = datetime.now(UTC)
            await db.commit()


def _resolve_column_map(fieldnames: list[str]) -> dict[str, str]:
    lower_headers = {name.strip().lower() for name in fieldnames if name}
    resolved: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_headers:
                resolved[canonical] = alias
                break
    return resolved


def _row_value(row: dict[str, str], column_map: dict[str, str], key: str) -> str:
    header = column_map.get(key)
    if not header:
        return ""
    return (row.get(header) or "").strip()


def parse_categories(value: str | None) -> list[str]:
    if not value or not value.strip():
        return ["General"]
    parts = [part.strip() for part in CATEGORY_SPLIT_RE.split(value.strip()) if part.strip()]
    return parts or ["General"]


def item_category_names(item: WordListItem) -> list[str]:
    return normalize_category_list([link.category for link in item.categories])


def format_category_name(category: str) -> str:
    cleaned = " ".join(category.strip().split())
    if not cleaned:
        return cleaned

    without_article = LEADING_ARTICLE_RE.sub("", cleaned).strip()
    if without_article:
        cleaned = without_article

    formatted = cleaned[0].upper() + cleaned[1:].lower()
    return CATEGORY_ALIASES.get(formatted.casefold(), formatted)


def normalize_category_list(categories: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for category in categories:
        if not category or not category.strip():
            continue
        for part in parse_categories(category):
            formatted = format_category_name(part)
            if not formatted:
                continue
            key = formatted.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(formatted)
    return deduped or ["General"]


def _normalize_categories(value: str | None) -> tuple[list[str] | None, str | None]:
    categories = normalize_category_list([value] if value is not None else [])
    for category in categories:
        if len(category) > CATEGORY_MAX_LENGTH:
            return None, (f"category '{category}' too long (max {CATEGORY_MAX_LENGTH} characters)")
    return categories, None


def _normalize_level(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    level = value.strip()
    if len(level) > LEVEL_MAX_LENGTH:
        return None
    return level


async def set_item_categories(db: AsyncSession, item: WordListItem, categories: list[str]) -> None:
    if item.id is None:
        await db.flush()
    await db.execute(
        delete(WordListItemCategory).where(WordListItemCategory.word_list_item_id == item.id)
    )
    for category in normalize_category_list(categories):
        db.add(WordListItemCategory(word_list_item_id=item.id, category=category))


async def get_or_create_bank(db: AsyncSession, parent_id: int) -> WordList:
    bank = await loop_engine.get_family_bank(db, parent_id)
    if bank is not None:
        return bank

    bank = WordList(
        parent_id=parent_id,
        name=BANK_LIST_NAME,
        description="Shared family vocabulary bank imported from CSV.",
        level_tag=None,
        source="bank",
        is_active=True,
    )
    db.add(bank)
    await db.flush()
    return bank


async def _resolve_entry(
    db: AsyncSession, *, word: str, definition: str | None
) -> tuple[DictionaryEntry, bool]:
    """Return entry and whether a placeholder was used."""
    normalized = normalize_word(word)
    if not normalized:
        raise ValueError("Word is required")

    existing = await dictionary_service.get_entry_by_word(db, normalized)
    if existing:
        return existing, False

    if definition and definition.strip():
        entry = DictionaryEntry(
            word=normalized,
            definition=definition.strip(),
            source="manual",
            fetched_at=datetime.now(UTC),
        )
        db.add(entry)
        await db.flush()
        return entry, False

    entry = DictionaryEntry(
        word=normalized,
        definition=PLACEHOLDER_DEFINITION,
        source="placeholder",
        fetched_at=datetime.now(UTC),
    )
    db.add(entry)
    await db.flush()
    return entry, True


async def _auto_assign_bank(db: AsyncSession, bank: WordList, parent_id: int) -> None:
    result = await db.execute(
        select(Learner).join(User, Learner.user_id == User.id).where(User.parent_id == parent_id)
    )
    learners = result.scalars().all()
    for learner in learners:
        existing = await db.execute(
            select(WordListAssignment).where(
                WordListAssignment.word_list_id == bank.id,
                WordListAssignment.learner_id == learner.id,
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(
                WordListAssignment(
                    word_list_id=bank.id,
                    learner_id=learner.id,
                    is_active=True,
                )
            )


async def import_csv(
    db: AsyncSession, *, parent_id: int, upload: UploadFile
) -> dict[str, int | list[str]]:
    raw = await upload.read()
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV file too large (max {MAX_IMPORT_BYTES // (1024 * 1024)} MB)",
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="CSV must be UTF-8 encoded"
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV header row required",
        )

    column_map = _resolve_column_map(reader.fieldnames)
    missing = [col for col in REQUIRED_COLUMNS if col not in column_map]
    if missing:
        found = ", ".join(name.strip() for name in reader.fieldnames if name)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Missing required column(s): {', '.join(missing)}. "
                f"Found headers: {found or '(none)'}"
            ),
        )

    bank = await get_or_create_bank(db, parent_id)
    now = datetime.now(UTC)

    created = updated = skipped = placeholder_count = 0
    invalid_level_count = invalid_category_count = 0
    errors: list[str] = []
    sort_order = 0
    row_count = 0

    existing_items_result = await db.execute(
        select(WordListItem).where(WordListItem.word_list_id == bank.id)
    )
    existing_by_entry: dict[int, WordListItem] = {
        item.dictionary_entry_id: item for item in existing_items_result.scalars().all()
    }

    for row_num, row in enumerate(reader, start=2):
        row_count += 1
        if row_count > MAX_IMPORT_ROWS:
            errors.append(f"Import stopped at row {row_num}: max {MAX_IMPORT_ROWS} rows")
            break

        normalized_row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        word = _row_value(normalized_row, column_map, "word")
        if not word:
            skipped += 1
            continue

        definition = _row_value(normalized_row, column_map, "definition") or None
        raw_level = _row_value(normalized_row, column_map, "level")
        level = _normalize_level(raw_level)
        if level is None:
            invalid_level_count += 1
            reason = (
                f"level too long (max {LEVEL_MAX_LENGTH} characters)"
                if raw_level and raw_level.strip()
                else "level is required"
            )
            errors.append(f"Row {row_num}: {reason} for '{word}'")
            skipped += 1
            continue

        categories, category_error = _normalize_categories(
            _row_value(normalized_row, column_map, "category")
        )
        if category_error:
            invalid_category_count += 1
            errors.append(f"Row {row_num}: {category_error} for '{word}'")
            skipped += 1
            continue

        try:
            entry, used_placeholder = await _resolve_entry(db, word=word, definition=definition)
        except ValueError as exc:
            errors.append(f"Row {row_num}: {exc}")
            skipped += 1
            continue

        if used_placeholder:
            placeholder_count += 1

        existing_item = existing_by_entry.get(entry.id)
        if existing_item:
            existing_item.level = level
            existing_item.sort_order = sort_order
            if definition:
                existing_item.notes = definition
            await set_item_categories(db, existing_item, categories)
            updated += 1
        else:
            item = WordListItem(
                word_list_id=bank.id,
                dictionary_entry_id=entry.id,
                sort_order=sort_order,
                level=level,
                notes=definition,
            )
            db.add(item)
            await db.flush()
            await set_item_categories(db, item, categories)
            existing_by_entry[entry.id] = item
            created += 1
        sort_order += 1

    if created == 0 and updated == 0 and row_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "IMPORT_VALIDATION_FAILED",
                "message": "No valid rows imported. Check word, level, and category columns.",
                "errors": errors[:20],
            },
        )

    await _auto_assign_bank(db, bank, parent_id)
    await db.commit()

    learners_result = await db.execute(
        select(Learner).join(User, Learner.user_id == User.id).where(User.parent_id == parent_id)
    )
    for learner in learners_result.scalars().all():
        await loop_engine.seed_bank_cards_for_learner(
            db, learner=learner, parent_id=parent_id, now=now
        )
    await db.commit()

    total_result = await db.execute(
        select(func.count(WordListItem.id)).where(WordListItem.word_list_id == bank.id)
    )
    total_items = total_result.scalar_one()

    return {
        "bank_id": bank.id,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "placeholder_count": placeholder_count,
        "needs_level_count": invalid_level_count,
        "invalid_category_count": invalid_category_count,
        "total_items": total_items,
        "errors": errors[:50],
    }


async def get_bank_summary(db: AsyncSession, parent_id: int) -> dict:
    bank = await loop_engine.get_family_bank(db, parent_id)
    if bank is None:
        return {
            "bank_id": None,
            "name": BANK_LIST_NAME,
            "total_items": 0,
            "placeholder_count": 0,
            "by_level": {},
            "by_category": {},
        }

    total_result = await db.execute(
        select(func.count(WordListItem.id)).where(WordListItem.word_list_id == bank.id)
    )
    total = total_result.scalar_one()

    level_result = await db.execute(
        select(WordListItem.level, func.count(WordListItem.id))
        .where(WordListItem.word_list_id == bank.id)
        .group_by(WordListItem.level)
    )
    by_level = {level or "unknown": count for level, count in level_result.all()}

    category_result = await db.execute(
        select(
            WordListItemCategory.category,
            func.count(func.distinct(WordListItemCategory.word_list_item_id)),
        )
        .join(WordListItem, WordListItemCategory.word_list_item_id == WordListItem.id)
        .where(WordListItem.word_list_id == bank.id)
        .group_by(WordListItemCategory.category)
    )
    by_category: dict[str, int] = {}
    for category, count in category_result.all():
        key = format_category_name(category)
        by_category[key] = by_category.get(key, 0) + count

    return {
        "bank_id": bank.id,
        "name": bank.name,
        "total_items": total,
        "placeholder_count": await count_placeholder_entries(db, parent_id),
        "by_level": by_level,
        "by_category": by_category,
    }


async def list_bank_items(
    db: AsyncSession,
    parent_id: int,
    *,
    level: str | None = None,
    category: str | None = None,
    query: str | None = None,
    page: int = 1,
    page_size: int = 50,
    placeholders_only: bool = False,
) -> dict:
    bank = await loop_engine.get_family_bank(db, parent_id)
    if bank is None:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
        }

    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    filters = [WordListItem.word_list_id == bank.id]
    if level:
        filters.append(func.lower(WordListItem.level) == level.strip().lower())
    if category:
        category_name = format_category_name(category.strip())
        filters.append(
            WordListItem.id.in_(
                select(WordListItemCategory.word_list_item_id).where(
                    func.lower(WordListItemCategory.category) == category_name.lower()
                )
            )
        )
    if query and query.strip():
        term = f"%{query.strip().lower()}%"
        filters.append(
            (DictionaryEntry.word.ilike(term)) | (DictionaryEntry.definition.ilike(term))
        )
    if placeholders_only:
        filters.append(_placeholder_entry_filter())

    base_filters = filters.copy()
    count_result = await db.execute(
        select(func.count(WordListItem.id))
        .join(DictionaryEntry, WordListItem.dictionary_entry_id == DictionaryEntry.id)
        .where(*base_filters)
    )
    total = count_result.scalar_one()
    total_pages = (total + page_size - 1) // page_size if total else 0

    items_result = await db.execute(
        select(WordListItem)
        .join(DictionaryEntry, WordListItem.dictionary_entry_id == DictionaryEntry.id)
        .options(
            selectinload(WordListItem.dictionary_entry),
            selectinload(WordListItem.categories),
        )
        .where(*filters)
        .order_by(WordListItem.sort_order, WordListItem.id)
        .offset(offset)
        .limit(page_size)
    )
    items = []
    for item in items_result.scalars().all():
        entry = item.dictionary_entry
        categories = item_category_names(item)
        items.append(
            {
                "id": item.id,
                "word": entry.word,
                "definition": entry.definition,
                "part_of_speech": entry.part_of_speech,
                "phonetic": entry.phonetic,
                "has_audio": entry.audio_path is not None,
                "level": item.level,
                "categories": categories,
                "sort_order": item.sort_order,
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


async def delete_bank(db: AsyncSession, parent_id: int) -> dict[str, int]:
    bank = await loop_engine.get_family_bank(db, parent_id)
    if bank is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "BANK_NOT_FOUND", "message": "No family word bank to delete"},
        )

    total_result = await db.execute(
        select(func.count(WordListItem.id)).where(WordListItem.word_list_id == bank.id)
    )
    deleted_items = total_result.scalar_one()

    cards_result = await db.execute(select(SrsCard).where(SrsCard.word_list_id == bank.id))
    cards = cards_result.scalars().all()
    deleted_cards = len(cards)
    for card in cards:
        await db.delete(card)

    sessions_result = await db.execute(
        select(DictationSession).where(DictationSession.word_list_id == bank.id)
    )
    for session in sessions_result.scalars().all():
        session.word_list_id = None

    await db.execute(delete(WordListItem).where(WordListItem.word_list_id == bank.id))
    await db.execute(delete(WordListAssignment).where(WordListAssignment.word_list_id == bank.id))
    await db.delete(bank)
    await db.commit()

    return {"deleted_items": deleted_items, "deleted_cards": deleted_cards}
