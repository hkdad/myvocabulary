from pathlib import Path

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_learner
from app.database import get_db
from app.models.user import User
from app.schemas.dictation import (
    DictationAnswerRequest,
    DictationAnswerResponse,
    DictationHistoryItem,
    DictationHistoryResponse,
    DictationPromptResponse,
    DictationSessionCreateRequest,
    DictationSessionResponse,
)
from app.services import dictation_service

router = APIRouter(prefix="/dictation", tags=["dictation"])


def _learner_profile(user: User):
    if user.learner_profile is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Learner profile missing")
    return user.learner_profile


@router.post(
    "/sessions", response_model=DictationSessionResponse, status_code=status.HTTP_201_CREATED
)
async def start_dictation_session(
    payload: DictationSessionCreateRequest,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> DictationSessionResponse:
    learner = _learner_profile(user)
    data = await dictation_service.start_session(
        db,
        learner=learner,
        word_list_id=payload.word_list_id,
        source=payload.source,
        mode=payload.mode,
        max_words=payload.max_words,
        entry_ids=payload.entry_ids,
    )
    return DictationSessionResponse(**data)


@router.get("/sessions/{session_id}", response_model=DictationSessionResponse)
async def get_dictation_session(
    session_id: int,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> DictationSessionResponse:
    learner = _learner_profile(user)
    data = await dictation_service.get_session(db, learner_id=learner.id, session_id=session_id)
    return DictationSessionResponse(**data)


@router.get("/sessions/{session_id}/next", response_model=DictationPromptResponse)
async def get_next_dictation_prompt(
    session_id: int,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> DictationPromptResponse:
    learner = _learner_profile(user)
    data = await dictation_service.get_next_prompt(db, learner_id=learner.id, session_id=session_id)
    return DictationPromptResponse(**data)


@router.get("/sessions/{session_id}/hint")
async def get_dictation_hint(
    session_id: int,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    learner = _learner_profile(user)
    return await dictation_service.get_hint(db, learner_id=learner.id, session_id=session_id)


@router.get("/sessions/{session_id}/audio")
async def get_dictation_audio(
    session_id: int,
    slow: bool = Query(default=False),
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    learner = _learner_profile(user)
    _session, path = await dictation_service.get_current_audio_path(
        db, learner_id=learner.id, session_id=session_id, slow=slow
    )
    return FileResponse(
        path=Path(path),
        media_type="audio/mpeg",
        filename="dictation.mp3",
        headers={"Cache-Control": "no-store, private"},
    )


@router.post("/sessions/{session_id}/answer", response_model=DictationAnswerResponse)
async def submit_dictation_answer(
    session_id: int,
    payload: DictationAnswerRequest,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> DictationAnswerResponse:
    learner = _learner_profile(user)
    data = await dictation_service.submit_answer(
        db,
        learner_id=learner.id,
        session_id=session_id,
        answer=payload.answer,
        hint_used=payload.hint_used,
    )
    return DictationAnswerResponse(**data)


@router.post("/sessions/{session_id}/give-up", response_model=DictationAnswerResponse)
async def give_up_dictation(
    session_id: int,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> DictationAnswerResponse:
    learner = _learner_profile(user)
    data = await dictation_service.give_up(db, learner_id=learner.id, session_id=session_id)
    return DictationAnswerResponse(**data)


@router.post("/sessions/{session_id}/complete", response_model=DictationSessionResponse)
async def complete_dictation_session(
    session_id: int,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> DictationSessionResponse:
    learner = _learner_profile(user)
    data = await dictation_service.complete_session(
        db, learner_id=learner.id, session_id=session_id
    )
    return DictationSessionResponse(**data)


@router.get("/history", response_model=DictationHistoryResponse)
async def get_dictation_history(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> DictationHistoryResponse:
    learner = _learner_profile(user)
    sessions = await dictation_service.list_history(db, learner_id=learner.id, limit=limit)
    return DictationHistoryResponse(
        sessions=[DictationHistoryItem(**session) for session in sessions]
    )
