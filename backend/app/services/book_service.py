"""Book upload, parse preview, confirm, assignment, and progress."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.book import Book, BookLemma
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
)
from app.services.dictionary_service import is_placeholder_definition, normalize_word

MAX_BOOK_BYTES = 10 * 1024 * 1024
PLACEHOLDER_DEFINITION = loop_engine.PLACEHOLDER_DEFINITION


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
        word_list = await db.get(WordList, list_id)
        if word_list is not None:
            await db.delete(word_list)
    await db.delete(book)
    await db.commit()


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
