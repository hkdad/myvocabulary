from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_parent
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.dictionary import (
    ClearZhResponse,
    DictionaryEntryResponse,
    DictionarySearchResponse,
    DictionarySuggestResponse,
    EnsureZhRequest,
    EnsureZhResponse,
    ManualWordCreateRequest,
)
from app.services import dictionary_service, tts_service

router = APIRouter(prefix="/dictionary", tags=["dictionary"])


def _to_response(data: dict) -> DictionaryEntryResponse:
    return DictionaryEntryResponse(**data)


@router.get("/search", response_model=DictionarySearchResponse)
async def search_dictionary(
    q: str = Query(min_length=1, max_length=128),
    limit: int = Query(default=20, ge=1, le=50),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DictionarySearchResponse:
    results = await dictionary_service.search_words(db, q, limit=limit)
    return DictionarySearchResponse(
        query=q,
        results=[_to_response(item) for item in results],
    )


@router.get("/suggest", response_model=DictionarySuggestResponse)
async def suggest_dictionary(
    q: str = Query(min_length=1, max_length=128),
    limit: int = Query(default=5, ge=1, le=20),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DictionarySuggestResponse:
    suggestions = await dictionary_service.suggest_words(db, q, limit=limit)
    return DictionarySuggestResponse(
        query=q,
        suggestions=[_to_response(item) for item in suggestions],
    )


@router.get("/words/{word}", response_model=DictionaryEntryResponse)
async def get_word(
    word: str,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DictionaryEntryResponse:
    entry = await dictionary_service.lookup_word(db, word)
    return _to_response(dictionary_service.entry_to_dict(entry))


@router.post("/ensure-zh", response_model=EnsureZhResponse)
async def ensure_zh_hant(
    payload: EnsureZhRequest,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EnsureZhResponse:
    """Lazily fill Traditional Chinese glosses for dictionary entries.

    Safe to call repeatedly — already-translated entries are returned from cache.
    Intended for review/challenge cards so session load stays fast.
    """
    items = await dictionary_service.ensure_zh_for_entry_ids(db, payload.entry_ids)
    return EnsureZhResponse(
        items=[
            {"id": int(item["id"]), "definition_zh_hant": str(item["definition_zh_hant"])}
            for item in items
            if item.get("definition_zh_hant")
        ]
    )


@router.delete("/entries/{entry_id}/zh-hant", response_model=ClearZhResponse)
async def clear_zh_hant(
    entry_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClearZhResponse:
    """Clear cached Traditional Chinese gloss so it can be re-translated later."""
    limiter.check(
        key=f"clear-zh:{user.id}",
        limit=20,
        window_seconds=60 * 60,
    )
    entry = await dictionary_service.clear_zh_hant(db, entry_id)
    return ClearZhResponse(id=entry.id, definition_zh_hant=None)


@router.post("/words", response_model=DictionaryEntryResponse, status_code=201)
async def create_word(
    payload: ManualWordCreateRequest,
    _parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> DictionaryEntryResponse:
    entry = await dictionary_service.create_manual_entry(
        db,
        word=payload.word,
        definition=payload.definition,
        phonetic=payload.phonetic,
        part_of_speech=payload.part_of_speech,
        example_sentence=payload.example_sentence,
    )
    return _to_response(dictionary_service.entry_to_dict(entry))


@router.get("/words/{word}/audio")
async def get_word_audio(
    word: str,
    slow: bool = Query(default=False),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    path = await tts_service.get_audio_for_word(db, word, slow=slow)
    return FileResponse(
        path=Path(path),
        media_type="audio/mpeg",
        filename=f"{dictionary_service.normalize_word(word)}.mp3",
        headers={"Cache-Control": "no-store, private"},
    )
