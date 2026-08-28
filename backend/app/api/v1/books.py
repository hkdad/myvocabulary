from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_parent
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.book import (
    BookAssignRequest,
    BookConfirmRequest,
    BookDefinitionsSummary,
    BookLemmaBulkHideRequest,
    BookLemmaHideRequest,
    BookListResponse,
    BookProgress,
    BookSummary,
    BookUpdateRequest,
    DefinitionFillJobResponse,
    PlaceholderLemmaListResponse,
    SuspiciousLemmaListResponse,
)
from app.services import book_service
from app.services.word_bank_service import job_to_dict

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


@router.get("/definitions-summary", response_model=BookDefinitionsSummary)
async def books_definitions_summary(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> BookDefinitionsSummary:
    data = await book_service.get_books_definitions_summary(db, parent.id)
    return BookDefinitionsSummary(**data)


@router.post("/fill-definitions", response_model=DefinitionFillJobResponse)
async def start_book_definition_fill(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> DefinitionFillJobResponse:
    data = await book_service.start_book_definition_fill_job(db, parent.id)
    return DefinitionFillJobResponse(**data)


@router.get("/fill-definitions/current", response_model=DefinitionFillJobResponse | None)
async def current_book_definition_fill(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> DefinitionFillJobResponse | None:
    job = await book_service.get_current_book_definition_fill_job(db, parent.id)
    if job is None:
        return None
    return DefinitionFillJobResponse(**job_to_dict(job))


@router.post("/fill-definitions/{job_id}/cancel", response_model=DefinitionFillJobResponse)
async def cancel_book_definition_fill(
    job_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> DefinitionFillJobResponse:
    data = await book_service.cancel_book_definition_fill_job(db, parent.id, job_id)
    return DefinitionFillJobResponse(**data)


@router.get("/placeholder-lemmas", response_model=PlaceholderLemmaListResponse)
async def list_placeholder_lemmas(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
    job_id: int | None = Query(default=None),
    include_hidden: bool = Query(default=False),
) -> PlaceholderLemmaListResponse:
    items = await book_service.list_book_placeholder_lemmas(
        db,
        parent_id=parent.id,
        job_id=job_id,
        include_hidden=include_hidden,
    )
    return PlaceholderLemmaListResponse(items=items, total=len(items))


@router.delete("/{book_id}", status_code=204)
async def delete_book(
    book_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> None:
    await book_service.delete_book(db, parent_id=parent.id, book_id=book_id)


@router.patch("/{book_id}", response_model=BookSummary)
async def update_book(
    book_id: int,
    payload: BookUpdateRequest,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> BookSummary:
    book = await book_service.update_book_title(
        db, parent_id=parent.id, book_id=book_id, title=payload.title
    )
    assigned = await book_service.assigned_learner_ids(db, book)
    return BookSummary(**book_service.book_to_preview(book, assigned_learner_ids=assigned))


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
        db,
        parent_id=parent.id,
        book_id=book_id,
        coverage_target=payload.coverage_target,
        title=payload.title,
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


@router.get("/{book_id}/suspicious-lemmas", response_model=SuspiciousLemmaListResponse)
async def list_suspicious_lemmas(
    book_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
    include_hidden: bool = Query(default=False),
) -> SuspiciousLemmaListResponse:
    items = await book_service.list_suspicious_lemmas(
        db, parent_id=parent.id, book_id=book_id, include_hidden=include_hidden
    )
    return SuspiciousLemmaListResponse(items=items, total=len(items))


@router.post("/{book_id}/lemmas/bulk-hide", response_model=BookSummary)
async def bulk_hide_book_lemmas(
    book_id: int,
    payload: BookLemmaBulkHideRequest,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> BookSummary:
    book = await book_service.bulk_hide_lemmas(
        db,
        parent_id=parent.id,
        book_id=book_id,
        lemma_ids=payload.lemma_ids,
        hidden=payload.hidden,
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
