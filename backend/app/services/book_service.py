"""Book upload, parse preview, confirm, assignment, and progress."""

from __future__ import annotations

import asyncio
import json
import math
import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings

from app.database import AsyncSessionLocal
from app.models.book import Book, BookLemma
from app.models.definition_fill_job import DefinitionFillJob
from app.models.dictation import DictationSession
from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.srs import SrsCard
from app.models.word_list import WordList, WordListAssignment, WordListItem
from app.services import dictionary_service, loop_engine
from app.services.book_analysis import (
    DEFAULT_COVERAGE_TARGET,
    analyze_text,
    extract_book_text,
    extract_book_title,
    suspicious_lemma_reason,
)
from app.services.dictionary_service import (
    fill_placeholder_definition,
    is_placeholder_definition,
    normalize_word,
)
from app.services.definition_fill_utils import fill_job_error_message_from_exception
from app.services.word_bank_service import job_to_dict

MAX_BOOK_BYTES = 10 * 1024 * 1024
PLACEHOLDER_DEFINITION = loop_engine.PLACEHOLDER_DEFINITION

BOOK_FILL_SCOPE = "books"
ACTIVE_JOB_STATUSES = ("queued", "running")
BOOK_FILL_PER_WORD_TIMEOUT = 12.0
BOOK_FILL_COMMIT_BATCH = 10
MAX_JOB_FAILED_WORDS = 500


def _safe_upload_basename(filename: str) -> str:
    stem = Path(filename).name.strip()
    if not stem or stem in {".", ".."}:
        return "book.txt"
    return stem[:255]


def _book_storage_dir(book_id: int) -> Path:
    path = get_settings().books_dir / str(book_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_book_upload(book_id: int, filename: str, data: bytes) -> Path:
    path = _book_storage_dir(book_id) / _safe_upload_basename(filename)
    path.write_bytes(data)
    return path


def _delete_book_upload(book_id: int) -> None:
    root = get_settings().books_dir / str(book_id)
    if root.exists():
        shutil.rmtree(root)


def _curve_dict(raw: str | dict) -> dict[str, int]:
    if isinstance(raw, dict):
        return {str(k): int(v) for k, v in raw.items()}
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): int(v) for k, v in data.items() if str(v).isdigit() or isinstance(v, int)}


async def _parent_learner(db: AsyncSession, *, parent_id: int, learner_id: int) -> Learner:
    result = await db.execute(
        select(Learner).options(selectinload(Learner.user)).where(Learner.id == learner_id)
    )
    learner = result.scalar_one_or_none()
    if learner is None or learner.user is None or learner.user.parent_id != parent_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learner not found")
    return learner


def _normalize_coverage(value: float | None) -> float:
    target = DEFAULT_COVERAGE_TARGET if value is None else float(value)
    rounded = round(target, 2)
    if rounded not in {0.8, 0.9}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="coverage_target must be 0.8 or 0.9",
        )
    return rounded


async def _get_book_for_parent(db: AsyncSession, book_id: int, parent_id: int) -> Book:
    result = await db.execute(
        select(Book).options(selectinload(Book.lemmas)).where(Book.id == book_id)
    )
    book = result.scalar_one_or_none()
    if book is None or book.parent_id != parent_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return book


def _apply_coverage(lemmas: list[BookLemma], coverage_target: float) -> int:
    visible = [item for item in lemmas if not item.is_hidden]
    total = sum(item.frequency for item in visible)
    for item in lemmas:
        item.in_study_set = False
    if total <= 0:
        return 0
    running = 0
    study_count = 0
    for item in sorted(visible, key=lambda row: (row.rank, row.id)):
        item.in_study_set = True
        study_count += 1
        running += item.frequency
        if running / total >= coverage_target:
            break
    return study_count


async def _family_bank_words(db: AsyncSession, parent_id: int) -> dict[str, int]:
    """Lemma → dictionary_entry_id for words in the family bank."""
    bank = await loop_engine.get_family_bank(db, parent_id)
    if bank is None:
        return {}
    result = await db.execute(
        select(DictionaryEntry.id, DictionaryEntry.word)
        .join(WordListItem, WordListItem.dictionary_entry_id == DictionaryEntry.id)
        .where(WordListItem.word_list_id == bank.id)
    )
    return {word: entry_id for entry_id, word in result.all()}


async def preview_upload(db: AsyncSession, *, parent_id: int, upload: UploadFile) -> Book:
    filename = upload.filename or "book.txt"
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")
    if len(data) > MAX_BOOK_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is too large (max 10 MB)",
        )
    try:
        text = extract_book_text(filename=filename, data=data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No text found in file")

    analysis = analyze_text(text, coverage_target=DEFAULT_COVERAGE_TARGET)
    title, title_source = extract_book_title(filename=filename, data=data, text=text)
    book = Book(
        parent_id=parent_id,
        title=title,
        title_source=title_source,
        original_filename=filename,
        status="preview",
        coverage_target=DEFAULT_COVERAGE_TARGET,
        token_count=analysis.token_count,
        unique_lemma_count=analysis.unique_lemma_count,
        content_lemma_count=analysis.content_lemma_count,
        study_lemma_count=sum(1 for item in analysis.lemmas if item.in_study_set),
        skipped_function_words=analysis.skipped_function_words,
        skipped_proper_nouns=analysis.skipped_proper_nouns,
        coverage_curve_json=json.dumps(analysis.coverage_curve),
        analysis_engine=analysis.engine,
    )
    db.add(book)
    await db.flush()
    _save_book_upload(book.id, filename, data)

    lemmas_to_match = [item.lemma for item in analysis.lemmas]
    bank_words = await _family_bank_words(db, parent_id)
    existing = {lemma: bank_words[lemma] for lemma in lemmas_to_match if lemma in bank_words}

    for item in analysis.lemmas:
        db.add(
            BookLemma(
                book_id=book.id,
                lemma=item.lemma,
                frequency=item.frequency,
                rank=item.rank,
                in_study_set=item.in_study_set,
                dictionary_entry_id=existing.get(item.lemma),
            )
        )
    await db.commit()
    return await _get_book_for_parent(db, book.id, parent_id)


async def confirm_book(
    db: AsyncSession,
    *,
    parent_id: int,
    book_id: int,
    coverage_target: float | None = None,
    title: str | None = None,
) -> Book:
    book = await _get_book_for_parent(db, book_id, parent_id)
    if book.status == "confirmed" and book.word_list_id is not None:
        return book

    if title is not None:
        cleaned = title.strip()
        if not cleaned:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Book title cannot be empty",
            )
        book.title = cleaned[:255]
        book.title_source = "manual"

    target = _normalize_coverage(
        coverage_target if coverage_target is not None else book.coverage_target
    )
    book.coverage_target = target
    book.study_lemma_count = _apply_coverage(list(book.lemmas), target)

    word_list = WordList(
        parent_id=parent_id,
        name=book.title,
        description=f"Book study set ({int(target * 100)}% content coverage).",
        source="book",
        is_active=True,
    )
    db.add(word_list)
    await db.flush()

    placeholder_entries: list[DictionaryEntry] = []
    for lemma in book.lemmas:
        if not lemma.in_study_set or lemma.is_hidden:
            continue
        entry = await _resolve_entry(db, lemma.lemma)
        lemma.dictionary_entry_id = entry.id
        if is_placeholder_definition(entry):
            placeholder_entries.append(entry)
        db.add(
            WordListItem(
                word_list_id=word_list.id,
                dictionary_entry_id=entry.id,
                sort_order=lemma.rank,
            )
        )

    if placeholder_entries:
        await dictionary_service.prefetch_study_set_definitions(db, placeholder_entries)

    book.word_list_id = word_list.id
    book.status = "confirmed"
    book.confirmed_at = datetime.now(UTC)
    await db.commit()
    return await _get_book_for_parent(db, book.id, parent_id)


async def _resolve_entry(db: AsyncSession, lemma: str) -> DictionaryEntry:
    normalized = normalize_word(lemma)
    existing = await dictionary_service.get_entry_by_word(db, normalized)
    if existing:
        return existing
    entry = DictionaryEntry(
        word=normalized,
        definition=PLACEHOLDER_DEFINITION,
        source="placeholder",
        fetched_at=datetime.now(UTC),
    )
    db.add(entry)
    await db.flush()
    return entry


async def update_book_title(db: AsyncSession, *, parent_id: int, book_id: int, title: str) -> Book:
    cleaned = title.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Book title cannot be empty",
        )
    book = await _get_book_for_parent(db, book_id, parent_id)
    book.title = cleaned[:255]
    book.title_source = "manual"
    if book.word_list_id is not None:
        word_list = await db.get(WordList, book.word_list_id)
        if word_list is not None:
            word_list.name = book.title
    await db.commit()
    return await _get_book_for_parent(db, book.id, parent_id)


async def delete_book(db: AsyncSession, *, parent_id: int, book_id: int) -> None:
    book = await _get_book_for_parent(db, book_id, parent_id)
    if book.word_list_id is not None:
        list_id = book.word_list_id
        await db.execute(
            delete(WordListAssignment).where(WordListAssignment.word_list_id == list_id)
        )
        await db.execute(delete(WordListItem).where(WordListItem.word_list_id == list_id))

        cards_result = await db.execute(select(SrsCard).where(SrsCard.word_list_id == list_id))
        for card in cards_result.scalars().all():
            card.word_list_id = None

        sessions_result = await db.execute(
            select(DictationSession).where(DictationSession.word_list_id == list_id)
        )
        for session in sessions_result.scalars().all():
            session.word_list_id = None

        book.word_list_id = None
        await db.flush()

        word_list = await db.get(WordList, list_id)
        if word_list is not None:
            await db.delete(word_list)
    await db.delete(book)
    await db.commit()
    _delete_book_upload(book_id)


async def delete_preview(db: AsyncSession, *, parent_id: int, book_id: int) -> None:
    await delete_book(db, parent_id=parent_id, book_id=book_id)


async def list_books(db: AsyncSession, parent_id: int) -> list[Book]:
    result = await db.execute(
        select(Book).where(Book.parent_id == parent_id).order_by(Book.created_at.desc())
    )
    return list(result.scalars().all())


async def hide_lemma(
    db: AsyncSession, *, parent_id: int, book_id: int, lemma_id: int, hidden: bool
) -> Book:
    book = await _get_book_for_parent(db, book_id, parent_id)
    lemma = next((row for row in book.lemmas if row.id == lemma_id), None)
    if lemma is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")
    lemma.is_hidden = hidden
    book.study_lemma_count = _apply_coverage(list(book.lemmas), book.coverage_target)
    if book.word_list_id is not None and lemma.dictionary_entry_id is not None:
        item_result = await db.execute(
            select(WordListItem).where(
                WordListItem.word_list_id == book.word_list_id,
                WordListItem.dictionary_entry_id == lemma.dictionary_entry_id,
            )
        )
        item = item_result.scalar_one_or_none()
        if hidden and item is not None:
            await db.delete(item)
        elif not hidden and lemma.in_study_set and item is None:
            db.add(
                WordListItem(
                    word_list_id=book.word_list_id,
                    dictionary_entry_id=lemma.dictionary_entry_id,
                    sort_order=lemma.rank,
                )
            )
    await db.commit()
    return await _get_book_for_parent(db, book.id, parent_id)


async def list_suspicious_lemmas(
    db: AsyncSession, *, parent_id: int, book_id: int, include_hidden: bool = False
) -> list[dict]:
    book = await _get_book_for_parent(db, book_id, parent_id)
    rows: list[dict] = []
    for lemma in book.lemmas:
        if lemma.is_hidden and not include_hidden:
            continue
        reason = suspicious_lemma_reason(lemma.lemma)
        if reason is None:
            continue
        rows.append(
            {
                "id": lemma.id,
                "lemma": lemma.lemma,
                "frequency": lemma.frequency,
                "rank": lemma.rank,
                "in_study_set": lemma.in_study_set,
                "is_hidden": lemma.is_hidden,
                "reason": reason,
            }
        )
    rows.sort(key=lambda row: (row["rank"], row["lemma"]))
    return rows


async def bulk_hide_lemmas(
    db: AsyncSession,
    *,
    parent_id: int,
    book_id: int,
    lemma_ids: list[int],
    hidden: bool,
) -> Book:
    book = await _get_book_for_parent(db, book_id, parent_id)
    target_ids = set(lemma_ids)
    if not target_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lemma_ids must not be empty",
        )

    for lemma in book.lemmas:
        if lemma.id not in target_ids:
            continue
        lemma.is_hidden = hidden
        if book.word_list_id is not None and lemma.dictionary_entry_id is not None:
            item_result = await db.execute(
                select(WordListItem).where(
                    WordListItem.word_list_id == book.word_list_id,
                    WordListItem.dictionary_entry_id == lemma.dictionary_entry_id,
                )
            )
            item = item_result.scalar_one_or_none()
            if hidden and item is not None:
                await db.delete(item)
            elif not hidden and lemma.in_study_set and item is None:
                db.add(
                    WordListItem(
                        word_list_id=book.word_list_id,
                        dictionary_entry_id=lemma.dictionary_entry_id,
                        sort_order=lemma.rank,
                    )
                )

    book.study_lemma_count = _apply_coverage(list(book.lemmas), book.coverage_target)
    await db.commit()
    return await _get_book_for_parent(db, book.id, parent_id)


async def activate_for_learner(
    db: AsyncSession, *, parent_id: int, book_id: int, learner_id: int
) -> Book:
    book = await _get_book_for_parent(db, book_id, parent_id)
    if book.status != "confirmed" or book.word_list_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm the parse preview before assigning this book",
        )
    await _parent_learner(db, parent_id=parent_id, learner_id=learner_id)

    other_books = await db.execute(
        select(Book.id, Book.word_list_id).where(
            Book.parent_id == parent_id,
            Book.status == "confirmed",
            Book.word_list_id.is_not(None),
        )
    )
    other_list_ids = [row.word_list_id for row in other_books.all() if row.word_list_id]
    if other_list_ids:
        existing = await db.execute(
            select(WordListAssignment).where(
                WordListAssignment.learner_id == learner_id,
                WordListAssignment.word_list_id.in_(other_list_ids),
            )
        )
        for assignment in existing.scalars().all():
            assignment.is_active = assignment.word_list_id == book.word_list_id

    result = await db.execute(
        select(WordListAssignment).where(
            WordListAssignment.word_list_id == book.word_list_id,
            WordListAssignment.learner_id == learner_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        db.add(
            WordListAssignment(
                word_list_id=book.word_list_id,
                learner_id=learner_id,
                is_active=True,
            )
        )
    else:
        assignment.is_active = True
        assignment.assigned_at = datetime.now(UTC)
    await db.commit()
    return await _get_book_for_parent(db, book.id, parent_id)


async def deactivate_for_learner(
    db: AsyncSession, *, parent_id: int, book_id: int, learner_id: int
) -> None:
    book = await _get_book_for_parent(db, book_id, parent_id)
    await _parent_learner(db, parent_id=parent_id, learner_id=learner_id)
    if book.word_list_id is None:
        return
    result = await db.execute(
        select(WordListAssignment).where(
            WordListAssignment.word_list_id == book.word_list_id,
            WordListAssignment.learner_id == learner_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is not None:
        assignment.is_active = False
        await db.commit()


async def get_active_book_for_learner(db: AsyncSession, learner_id: int) -> Book | None:
    result = await db.execute(
        select(Book)
        .join(WordList, Book.word_list_id == WordList.id)
        .join(WordListAssignment, WordListAssignment.word_list_id == WordList.id)
        .where(
            WordListAssignment.learner_id == learner_id,
            WordListAssignment.is_active.is_(True),
            WordList.is_active.is_(True),
            Book.status == "confirmed",
        )
        .options(selectinload(Book.lemmas))
        .order_by(WordListAssignment.assigned_at.desc(), Book.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def study_entry_ids(db: AsyncSession, book: Book) -> set[int]:
    if book.word_list_id is None:
        return set()
    result = await db.execute(
        select(WordListItem.dictionary_entry_id).where(
            WordListItem.word_list_id == book.word_list_id
        )
    )
    return set(result.scalars().all())


async def assigned_learner_ids(db: AsyncSession, book: Book) -> list[int]:
    if book.word_list_id is None:
        return []
    result = await db.execute(
        select(WordListAssignment.learner_id).where(
            WordListAssignment.word_list_id == book.word_list_id,
            WordListAssignment.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


async def _baseline_known_entry_ids(
    db: AsyncSession, learner_id: int, entry_ids: set[int]
) -> set[int]:
    """Family-bank words the learner already knows — counts as free book progress."""
    if not entry_ids:
        return set()
    cards_result = await db.execute(
        select(SrsCard).where(
            SrsCard.learner_id == learner_id,
            SrsCard.dictionary_entry_id.in_(entry_ids),
            SrsCard.released_at.is_not(None),
        )
    )
    cards = list(cards_result.scalars().all())
    card_ids = [card.id for card in cards if card.id is not None]
    days_map = await loop_engine.distinct_review_days_by_card(db, card_ids)
    known: set[int] = set()
    for card in cards:
        if days_map.get(card.id, 0) >= 1:
            known.add(card.dictionary_entry_id)
    return known


async def _known_entry_ids(db: AsyncSession, learner_id: int, entry_ids: set[int]) -> set[int]:
    return await _baseline_known_entry_ids(db, learner_id, entry_ids)


async def progress_for_learner(db: AsyncSession, book: Book, learner_id: int) -> dict:
    content_ids = {
        lemma.dictionary_entry_id
        for lemma in book.lemmas
        if lemma.dictionary_entry_id is not None and not lemma.is_hidden
    }
    study_ids = {
        lemma.dictionary_entry_id
        for lemma in book.lemmas
        if lemma.dictionary_entry_id is not None and lemma.in_study_set and not lemma.is_hidden
    }
    # Unconfirmed books may not have entry ids yet — fall back to lemma matching.
    if not content_ids:
        lemmas = [lemma.lemma for lemma in book.lemmas if not lemma.is_hidden]
        if lemmas:
            result = await db.execute(
                select(DictionaryEntry.id, DictionaryEntry.word).where(
                    DictionaryEntry.word.in_(lemmas)
                )
            )
            by_word = {word: entry_id for entry_id, word in result.all()}
            content_ids = {by_word[lemma.lemma] for lemma in book.lemmas if lemma.lemma in by_word}
            study_ids = {
                by_word[lemma.lemma]
                for lemma in book.lemmas
                if lemma.in_study_set and lemma.lemma in by_word
            }

    known = await _known_entry_ids(db, learner_id, content_ids)
    study_total = len(study_ids) or book.study_lemma_count
    content_total = len(content_ids) or book.content_lemma_count
    study_known = len(known & study_ids) if study_ids else 0
    page_known = len(known & content_ids) if content_ids else 0
    study_progress = (study_known / study_total) if study_total else 0.0
    page_coverage = (page_known / content_total) if content_total else 0.0
    strength = await loop_engine.strength_counts_for_entry_ids(
        db, learner_id=learner_id, entry_ids=study_ids
    )
    return {
        "learner_id": learner_id,
        "study_known": study_known,
        "study_total": study_total,
        "study_progress_percent": round(study_progress * 100, 1),
        "page_known": page_known,
        "content_total": content_total,
        "page_coverage_percent": round(page_coverage * 100, 1),
        "ready_to_read": page_coverage >= 0.80,
        "days_estimate": math.ceil(max(0, study_total - study_known) / 5) if study_total else 0,
        "learning_count": strength["learning"],
        "familiar_count": strength["familiar"],
        "mastered_count": strength["mastered"],
    }


def book_to_summary(book: Book, *, assigned_learner_ids: list[int] | None = None) -> dict:
    curve = _curve_dict(book.coverage_curve_json)
    study = book.study_lemma_count
    return {
        "id": book.id,
        "title": book.title,
        "title_source": getattr(book, "title_source", "filename"),
        "title_needs_review": getattr(book, "title_source", "filename") == "filename",
        "original_filename": book.original_filename,
        "status": book.status,
        "coverage_target": book.coverage_target,
        "token_count": book.token_count,
        "unique_lemma_count": book.unique_lemma_count,
        "content_lemma_count": book.content_lemma_count,
        "study_lemma_count": study,
        "skipped_function_words": book.skipped_function_words,
        "skipped_proper_nouns": book.skipped_proper_nouns,
        "coverage_curve": curve,
        "days_at_five_new": math.ceil(study / 5) if study else 0,
        "word_list_id": book.word_list_id,
        "assigned_learner_ids": assigned_learner_ids or [],
        "analysis_engine": book.analysis_engine,
        "confirmed_at": book.confirmed_at.isoformat() if book.confirmed_at else None,
        "created_at": book.created_at.isoformat() if book.created_at else None,
    }


def book_to_preview(book: Book, *, assigned_learner_ids: list[int] | None = None) -> dict:
    matched = [
        lemma
        for lemma in book.lemmas
        if lemma.dictionary_entry_id is not None and not lemma.is_hidden
    ]
    baseline_lemmas = {lemma.lemma for lemma in matched}
    study = [lemma for lemma in book.lemmas if lemma.in_study_set and not lemma.is_hidden]
    advanced = [lemma for lemma in book.lemmas if not lemma.in_study_set and not lemma.is_hidden]
    summary = book_to_summary(book, assigned_learner_ids=assigned_learner_ids)
    summary.update(
        {
            "baseline_match_count": len(baseline_lemmas),
            "new_word_count": max(0, book.content_lemma_count - len(baseline_lemmas)),
            "sample_study": [
                {
                    "id": lemma.id,
                    "lemma": lemma.lemma,
                    "frequency": lemma.frequency,
                    "rank": lemma.rank,
                    "in_study_set": lemma.in_study_set,
                    "is_hidden": lemma.is_hidden,
                    "matched_baseline": lemma.dictionary_entry_id is not None,
                }
                for lemma in study[:40]
            ],
            "sample_advanced": [
                {
                    "id": lemma.id,
                    "lemma": lemma.lemma,
                    "frequency": lemma.frequency,
                    "rank": lemma.rank,
                    "in_study_set": lemma.in_study_set,
                    "is_hidden": lemma.is_hidden,
                    "matched_baseline": lemma.dictionary_entry_id is not None,
                }
                for lemma in advanced[:20]
            ],
        }
    )
    return summary


def _placeholder_entry_filter():
    return or_(
        DictionaryEntry.source == "placeholder",
        DictionaryEntry.definition.like("Definition pending%"),
    )


def _missing_zh_filter():
    return or_(
        DictionaryEntry.definition_zh_hant.is_(None),
        func.trim(DictionaryEntry.definition_zh_hant) == "",
    )


def _book_entry_ids_query(parent_id: int):
    return (
        select(WordListItem.dictionary_entry_id)
        .join(WordList, WordList.id == WordListItem.word_list_id)
        .join(Book, Book.word_list_id == WordList.id)
        .where(
            Book.parent_id == parent_id,
            Book.status == "confirmed",
            Book.word_list_id.is_not(None),
            WordList.source == "book",
        )
        .distinct()
    )


def entry_needs_en_refresh(entry: DictionaryEntry) -> bool:
    return is_placeholder_definition(entry)


def entry_needs_definition_refresh(entry: DictionaryEntry) -> bool:
    if is_placeholder_definition(entry):
        return True
    zh = (entry.definition_zh_hant or "").strip()
    return not zh


async def get_books_definitions_summary(db: AsyncSession, parent_id: int) -> dict[str, int]:
    entry_ids = _book_entry_ids_query(parent_id).subquery()

    def _book_entries():
        return select(DictionaryEntry).join(
            entry_ids, DictionaryEntry.id == entry_ids.c.dictionary_entry_id
        )

    missing_en = await db.execute(
        select(func.count()).select_from(
            _book_entries().where(_placeholder_entry_filter()).subquery()
        )
    )
    missing_zh = await db.execute(
        select(func.count()).select_from(
            _book_entries()
            .where(not_(_placeholder_entry_filter()), _missing_zh_filter())
            .subquery()
        )
    )
    needs_refresh = await db.execute(
        select(func.count()).select_from(
            _book_entries()
            .where(or_(_placeholder_entry_filter(), _missing_zh_filter()))
            .subquery()
        )
    )
    return {
        "missing_en_count": int(missing_en.scalar_one()),
        "missing_zh_count": int(missing_zh.scalar_one()),
        "needs_refresh_count": int(needs_refresh.scalar_one()),
    }


async def _list_book_entry_ids_needing_en(db: AsyncSession, parent_id: int) -> list[int]:
    entry_ids = _book_entry_ids_query(parent_id).subquery()
    result = await db.execute(
        select(DictionaryEntry.id)
        .join(entry_ids, DictionaryEntry.id == entry_ids.c.dictionary_entry_id)
        .where(_placeholder_entry_filter())
        .order_by(DictionaryEntry.id)
    )
    return list(result.scalars().all())


def _record_job_failure(job: DefinitionFillJob, *, word: str, entry_id: int) -> None:
    failures: list[dict[str, int | str]] = []
    if job.failed_words_json:
        try:
            raw = json.loads(job.failed_words_json)
            if isinstance(raw, list):
                failures = [row for row in raw if isinstance(row, dict)]
        except json.JSONDecodeError:
            failures = []
    failures.append({"word": word, "entry_id": entry_id})
    if len(failures) > MAX_JOB_FAILED_WORDS:
        failures = failures[-MAX_JOB_FAILED_WORDS:]
    job.failed_words_json = json.dumps(failures)


async def list_book_placeholder_lemmas(
    db: AsyncSession,
    *,
    parent_id: int,
    job_id: int | None = None,
    include_hidden: bool = False,
) -> list[dict]:
    entry_ids_filter: set[int] | None = None
    if job_id is not None:
        job = await db.get(DefinitionFillJob, job_id)
        if job is None or job.parent_id != parent_id or job.scope != BOOK_FILL_SCOPE:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        entry_ids_filter = set()
        if job.failed_words_json:
            try:
                raw = json.loads(job.failed_words_json)
                if isinstance(raw, list):
                    entry_ids_filter = {
                        int(row["entry_id"])
                        for row in raw
                        if isinstance(row, dict) and row.get("entry_id")
                    }
            except (json.JSONDecodeError, TypeError, ValueError):
                entry_ids_filter = set()

    filters = [
        Book.parent_id == parent_id,
        Book.status == "confirmed",
        BookLemma.dictionary_entry_id.is_not(None),
        _placeholder_entry_filter(),
    ]
    if not include_hidden:
        filters.append(BookLemma.is_hidden.is_(False))
    if entry_ids_filter is not None:
        filters.append(DictionaryEntry.id.in_(entry_ids_filter or [-1]))

    result = await db.execute(
        select(
            BookLemma.id,
            BookLemma.book_id,
            Book.title,
            BookLemma.lemma,
            BookLemma.frequency,
            BookLemma.in_study_set,
            BookLemma.is_hidden,
        )
        .join(Book, BookLemma.book_id == Book.id)
        .join(DictionaryEntry, DictionaryEntry.id == BookLemma.dictionary_entry_id)
        .where(*filters)
        .order_by(BookLemma.frequency.desc(), Book.title, BookLemma.lemma)
    )
    return [
        {
            "id": row.id,
            "book_id": row.book_id,
            "book_title": row.title,
            "lemma": row.lemma,
            "frequency": row.frequency,
            "in_study_set": row.in_study_set,
            "is_hidden": row.is_hidden,
        }
        for row in result.all()
    ]


async def get_current_book_definition_fill_job(
    db: AsyncSession, parent_id: int
) -> DefinitionFillJob | None:
    active_result = await db.execute(
        select(DefinitionFillJob)
        .where(
            DefinitionFillJob.parent_id == parent_id,
            DefinitionFillJob.scope == BOOK_FILL_SCOPE,
            DefinitionFillJob.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(DefinitionFillJob.id.desc())
        .limit(1)
    )
    active_job = active_result.scalar_one_or_none()
    if active_job is not None:
        if _book_fill_job_is_stale(active_job):
            active_job.status = "failed"
            active_job.error_message = "Job interrupted — please start again."
            active_job.finished_at = datetime.now(UTC)
            await db.commit()
            await db.refresh(active_job)
        return active_job

    result = await db.execute(
        select(DefinitionFillJob)
        .where(
            DefinitionFillJob.parent_id == parent_id,
            DefinitionFillJob.scope == BOOK_FILL_SCOPE,
        )
        .order_by(DefinitionFillJob.id.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    return job


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _book_fill_job_is_stale(job: DefinitionFillJob) -> bool:
    if job.status not in ACTIVE_JOB_STATUSES:
        return False
    if job.finished_at is not None:
        return True
    if job.status == "running" and job.total == 0:
        return True
    if job.started_at is None:
        return False
    age_seconds = (datetime.now(UTC) - _as_utc(job.started_at)).total_seconds()
    if job.processed == 0 and age_seconds > 120:
        return True
    if (
        job.status == "running"
        and job.total > 0
        and job.processed < job.total
        and age_seconds > 1800
    ):
        return True
    return False


async def _fail_stale_active_book_fill_jobs(db: AsyncSession, parent_id: int) -> None:
    result = await db.execute(
        select(DefinitionFillJob).where(
            DefinitionFillJob.parent_id == parent_id,
            DefinitionFillJob.scope == BOOK_FILL_SCOPE,
            DefinitionFillJob.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    stale_jobs = [job for job in result.scalars().all() if _book_fill_job_is_stale(job)]
    if not stale_jobs:
        return
    for job in stale_jobs:
        job.status = "failed"
        job.error_message = "Job interrupted — please start again."
        job.finished_at = datetime.now(UTC)
    await db.commit()


async def start_book_definition_fill_job(db: AsyncSession, parent_id: int) -> dict:
    await _fail_stale_active_book_fill_jobs(db, parent_id)
    active = await db.execute(
        select(DefinitionFillJob).where(
            DefinitionFillJob.parent_id == parent_id,
            DefinitionFillJob.scope == BOOK_FILL_SCOPE,
            DefinitionFillJob.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    active_jobs = list(active.scalars().all())
    if active_jobs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "JOB_ALREADY_RUNNING",
                "message": "A book definition fill job is already in progress",
            },
        )

    total = (await get_books_definitions_summary(db, parent_id))["missing_en_count"]
    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NO_PLACEHOLDERS",
                "message": "All book words already have English definitions",
            },
        )

    job = DefinitionFillJob(
        parent_id=parent_id,
        scope=BOOK_FILL_SCOPE,
        bank_id=None,
        status="queued",
        total=total,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    asyncio.create_task(run_book_definition_fill_job(job.id))
    return job_to_dict(job)


async def cancel_book_definition_fill_job(db: AsyncSession, parent_id: int, job_id: int) -> dict:
    job = await db.get(DefinitionFillJob, job_id)
    if job is None or job.parent_id != parent_id or job.scope != BOOK_FILL_SCOPE:
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


async def run_book_definition_fill_job(job_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await execute_book_definition_fill_job(db, job_id)


async def _refresh_entry_en(db: AsyncSession, entry: DictionaryEntry) -> None:
    entry_id = entry.id
    if not is_placeholder_definition(entry):
        return
    await db.commit()
    entry = await db.get(DictionaryEntry, entry_id)
    if entry is None:
        return
    await asyncio.wait_for(
        fill_placeholder_definition(db, entry, api_only=True),
        timeout=BOOK_FILL_PER_WORD_TIMEOUT,
    )
    await db.commit()
    await db.refresh(entry)


async def execute_book_definition_fill_job(db: AsyncSession, job_id: int) -> None:
    try:
        job = await db.get(DefinitionFillJob, job_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = datetime.now(UTC)
        await db.commit()

        entry_ids = await _list_book_entry_ids_needing_en(db, job.parent_id)
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
            if entry is None:
                failed += 1
            elif entry_needs_en_refresh(entry):
                try:
                    await _refresh_entry_en(db, entry)
                    refreshed = await db.get(DictionaryEntry, entry_id)
                    if refreshed is not None and not entry_needs_en_refresh(refreshed):
                        filled += 1
                    else:
                        failed += 1
                        if refreshed is not None:
                            _record_job_failure(job, word=refreshed.word, entry_id=refreshed.id)
                except (TimeoutError, Exception):
                    failed += 1
                    if entry is not None:
                        _record_job_failure(job, word=entry.word, entry_id=entry.id)

            processed += 1
            job.processed = processed
            job.filled = filled
            job.failed = failed
            should_commit = (
                processed % BOOK_FILL_COMMIT_BATCH == 0 or processed >= len(entry_ids)
            )
            if not should_commit:
                continue
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
