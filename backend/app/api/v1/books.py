from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_parent
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.book import (
    BookAssignRequest,
    BookConfirmRequest,
    BookLemmaHideRequest,
    BookListResponse,
    BookProgress,
    BookSummary,
)
from app.services import book_service

router = APIRouter(prefix="/books", tags=["books"])


@router.post("/preview", response_model=BookSummary)
async def preview_book(
    file: UploadFile = File(...),
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> BookSummary:
    limiter.check(key=f"book-preview:{parent.id}", limit=10, window_seconds=60 * 60)
    book = await book_service.preview_upload(db, parent_id=parent.id, upload=file)
    return BookSummary(**book_service.book_to_preview(book))


@router.get("", response_model=BookListResponse)
async def list_books(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> BookListResponse:
    books = await book_service.list_books(db, parent.id)
    summaries: list[BookSummary] = []
    for book in books:
        assigned = await book_service.assigned_learner_ids(db, book)
        summaries.append(
            BookSummary(**book_service.book_to_summary(book, assigned_learner_ids=assigned))
        )
    return BookListResponse(books=summaries)


@router.delete("/{book_id}", status_code=204)
async def delete_book(
    book_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> None:
    await book_service.delete_preview(db, parent_id=parent.id, book_id=book_id)


@router.get("/{book_id}", response_model=BookSummary)
async def get_book(
    book_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> BookSummary:
    book = await book_service._get_book_for_parent(db, book_id, parent.id)
    assigned = await book_service.assigned_learner_ids(db, book)
    return BookSummary(**book_service.book_to_preview(book, assigned_learner_ids=assigned))


@router.post("/{book_id}/confirm", response_model=BookSummary)
async def confirm_book(
    book_id: int,
    payload: BookConfirmRequest,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> BookSummary:
    book = await book_service.confirm_book(
        db, parent_id=parent.id, book_id=book_id, coverage_target=payload.coverage_target
    )
    assigned = await book_service.assigned_learner_ids(db, book)
    return BookSummary(**book_service.book_to_preview(book, assigned_learner_ids=assigned))


@router.post("/{book_id}/assign", response_model=BookSummary)
async def assign_book(
    book_id: int,
    payload: BookAssignRequest,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> BookSummary:
    book = await book_service.activate_for_learner(
        db, parent_id=parent.id, book_id=book_id, learner_id=payload.learner_id
    )
    assigned = await book_service.assigned_learner_ids(db, book)
    return BookSummary(**book_service.book_to_summary(book, assigned_learner_ids=assigned))


@router.delete("/{book_id}/assign/{learner_id}", response_model=BookSummary)
async def unassign_book(
    book_id: int,
    learner_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> BookSummary:
    await book_service.deactivate_for_learner(
        db, parent_id=parent.id, book_id=book_id, learner_id=learner_id
    )
    book = await book_service._get_book_for_parent(db, book_id, parent.id)
    assigned = await book_service.assigned_learner_ids(db, book)
    return BookSummary(**book_service.book_to_summary(book, assigned_learner_ids=assigned))


@router.patch("/{book_id}/lemmas/{lemma_id}", response_model=BookSummary)
async def hide_book_lemma(
    book_id: int,
    lemma_id: int,
    payload: BookLemmaHideRequest,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> BookSummary:
    book = await book_service.hide_lemma(
        db, parent_id=parent.id, book_id=book_id, lemma_id=lemma_id, hidden=payload.hidden
    )
    assigned = await book_service.assigned_learner_ids(db, book)
    return BookSummary(**book_service.book_to_preview(book, assigned_learner_ids=assigned))


@router.get("/{book_id}/progress", response_model=list[BookProgress])
async def book_progress(
    book_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
    learner_id: int | None = Query(default=None),
) -> list[BookProgress]:
    book = await book_service._get_book_for_parent(db, book_id, parent.id)
    if learner_id is not None:
        await book_service._parent_learner(db, parent_id=parent.id, learner_id=learner_id)
        data = await book_service.progress_for_learner(db, book, learner_id)
        return [BookProgress(**data)]
    assigned = await book_service.assigned_learner_ids(db, book)
    results: list[BookProgress] = []
    for assigned_id in assigned:
        data = await book_service.progress_for_learner(db, book, assigned_id)
        results.append(BookProgress(**data))
    return results
