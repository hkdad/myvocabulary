from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_learner
from app.database import get_db
from app.models.user import User
from app.schemas.review import (
    CompleteMistakeChallengeRequest,
    CompleteMistakeChallengeResponse,
    DueCardsResponse,
    InitializeMistakeReviewsResponse,
    InitializeReviewsResponse,
    MistakeCardResponse,
    MistakeCardsResponse,
    ReviewAnswerRequest,
    ReviewAnswerResponse,
    ReviewStatsResponse,
    SrsCardResponse,
)
from app.services import srs_service

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _learner_id(user: User) -> int:
    if user.learner_profile is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Learner profile missing")
    return user.learner_profile.id


def _daily_goal(user: User) -> int:
    if user.learner_profile is None:
        return 7
    from app.services import loop_engine

    return loop_engine.daily_practice_goal(user.learner_profile)


@router.get("/due", response_model=DueCardsResponse)
async def get_due_cards(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
    limit: int | None = Query(default=None, ge=1, le=200),
    word_list_id: int | None = Query(default=None, ge=1),
    mistakes_only: bool = Query(default=False),
    practice_all: bool = Query(default=False),
    daily_challenge: bool = Query(default=False),
) -> DueCardsResponse:
    learner_id = _learner_id(user)
    if daily_challenge:
        from app.services import loop_engine

        learner = user.learner_profile
        parent_id = await loop_engine.get_learner_parent_id(db, learner) if learner else None
        if learner is None or parent_id is None:
            return DueCardsResponse(cards=[], due_count=0, daily_goal=_daily_goal(user))
        data = await loop_engine.get_today_mix_cards(db, learner=learner, parent_id=parent_id)
        return DueCardsResponse(
            cards=[SrsCardResponse(**card) for card in data["cards"]],
            due_count=data["due_count"],
            daily_goal=data["daily_goal"],
        )

    data = await srs_service.get_due_cards(
        db,
        learner_id=learner_id,
        daily_goal=_daily_goal(user),
        limit=limit,
        word_list_id=word_list_id,
        mistakes_only=mistakes_only,
        practice_all=practice_all,
    )
    return DueCardsResponse(
        cards=[SrsCardResponse(**card) for card in data["cards"]],
        due_count=data["due_count"],
        daily_goal=data["daily_goal"],
    )


@router.get("/stats", response_model=ReviewStatsResponse)
async def get_review_stats(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> ReviewStatsResponse:
    learner_id = _learner_id(user)
    data = await srs_service.get_review_stats(
        db, learner_id=learner_id, daily_goal=_daily_goal(user)
    )
    return ReviewStatsResponse(**data)


@router.post("/initialize-mistakes", response_model=InitializeMistakeReviewsResponse)
async def initialize_mistake_reviews(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> InitializeMistakeReviewsResponse:
    learner_id = _learner_id(user)
    data = await srs_service.initialize_mistake_reviews(db, learner_id=learner_id)
    return InitializeMistakeReviewsResponse(**data)


@router.post("/mistakes/complete", response_model=CompleteMistakeChallengeResponse)
async def complete_mistake_challenge(
    payload: CompleteMistakeChallengeRequest,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> CompleteMistakeChallengeResponse:
    learner_id = _learner_id(user)
    data = await srs_service.complete_mistake_challenge(
        db,
        learner_id=learner_id,
        dictionary_entry_ids=payload.dictionary_entry_ids,
    )
    return CompleteMistakeChallengeResponse(**data)


@router.post("/initialize", response_model=InitializeReviewsResponse)
async def initialize_reviews(
    word_list_id: int = Query(..., ge=1),
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> InitializeReviewsResponse:
    learner_id = _learner_id(user)
    data = await srs_service.initialize_from_word_list(
        db, learner_id=learner_id, word_list_id=word_list_id
    )
    return InitializeReviewsResponse(**data)


@router.post("/{card_id}/answer", response_model=ReviewAnswerResponse)
async def answer_review(
    card_id: int,
    payload: ReviewAnswerRequest,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> ReviewAnswerResponse:
    learner_id = _learner_id(user)
    data = await srs_service.answer_card(
        db, learner_id=learner_id, card_id=card_id, quality=payload.quality
    )
    return ReviewAnswerResponse(card=SrsCardResponse(**data["card"]))


@router.get("/mistakes", response_model=MistakeCardsResponse)
async def get_mistake_cards(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> MistakeCardsResponse:
    learner_id = _learner_id(user)
    cards = await srs_service.get_mistake_cards(db, learner_id=learner_id)
    return MistakeCardsResponse(cards=[MistakeCardResponse(**card) for card in cards])
