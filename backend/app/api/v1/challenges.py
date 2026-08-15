from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_learner
from app.database import get_db
from app.models.user import User
from app.schemas.challenge import (
    AvailableChallengesResponse,
    ChallengeHistoryResponse,
    ChallengeSessionResponse,
    ChallengeStartRequest,
    ChallengeSubmitRequest,
    ChallengeSubmitResponse,
    LearnerBadgesResponse,
)
from app.services import challenge_service

router = APIRouter(prefix="/challenges", tags=["challenges"])


def _learner_profile(user: User):
    if user.learner_profile is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Learner profile missing")
    return user.learner_profile


@router.get("/available", response_model=AvailableChallengesResponse)
async def list_available_challenges(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> AvailableChallengesResponse:
    learner = _learner_profile(user)
    challenges = await challenge_service.get_available_challenges(db, learner=learner)
    return AvailableChallengesResponse(challenges=challenges)


@router.post("/start", response_model=ChallengeSessionResponse)
async def start_challenge(
    payload: ChallengeStartRequest,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> ChallengeSessionResponse:
    learner = _learner_profile(user)
    data = await challenge_service.start_challenge(
        db,
        learner=learner,
        challenge_type=payload.challenge_type,
        challenge_id=payload.challenge_id,
        target_level=payload.target_level,
    )
    return ChallengeSessionResponse(**data)


@router.post("/{challenge_id}/submit", response_model=ChallengeSubmitResponse)
async def submit_challenge(
    challenge_id: int,
    payload: ChallengeSubmitRequest,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> ChallengeSubmitResponse:
    learner = _learner_profile(user)
    data = await challenge_service.submit_challenge(
        db,
        learner=learner,
        challenge_id=challenge_id,
        answers=[item.model_dump() for item in payload.answers],
    )
    return ChallengeSubmitResponse(**data)


@router.get("/history", response_model=ChallengeHistoryResponse)
async def challenge_history(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> ChallengeHistoryResponse:
    learner = _learner_profile(user)
    items = await challenge_service.get_history(db, learner_id=learner.id)
    return ChallengeHistoryResponse(items=items)


@router.get("/badges", response_model=LearnerBadgesResponse)
async def learner_badges(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> LearnerBadgesResponse:
    learner = _learner_profile(user)
    badges = await challenge_service.get_badges(db, learner_id=learner.id)
    return LearnerBadgesResponse(badges=badges)
