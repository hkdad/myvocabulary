from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_parent
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.loop import (
    WordBankDeleteResponse,
    WordBankImportResponse,
    WordBankItemsResponse,
    WordBankSummaryResponse,
)
from app.services import word_bank_service

router = APIRouter(prefix="/word-bank", tags=["word-bank"])


@router.post("/import", response_model=WordBankImportResponse)
async def import_word_bank(
    file: UploadFile = File(...),
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> WordBankImportResponse:
    limiter.check(key=f"bank-import:{parent.id}", limit=3, window_seconds=60 * 60)
    result = await word_bank_service.import_csv(db, parent_id=parent.id, upload=file)
    return WordBankImportResponse(**result)


@router.get("", response_model=WordBankSummaryResponse)
async def get_word_bank(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> WordBankSummaryResponse:
    data = await word_bank_service.get_bank_summary(db, parent.id)
    return WordBankSummaryResponse(**data)


@router.get("/items", response_model=WordBankItemsResponse)
async def list_word_bank_items(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
    level: str | None = Query(default=None, max_length=32),
    category: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, max_length=128),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> WordBankItemsResponse:
    data = await word_bank_service.list_bank_items(
        db,
        parent.id,
        level=level,
        category=category,
        query=q,
        page=page,
        page_size=page_size,
    )
    return WordBankItemsResponse(**data)


@router.delete("", response_model=WordBankDeleteResponse)
async def delete_word_bank(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> WordBankDeleteResponse:
    data = await word_bank_service.delete_bank(db, parent.id)
    return WordBankDeleteResponse(**data)
