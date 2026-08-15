from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_parent
from app.database import get_db
from app.models.user import User
from app.schemas.level_assessment import (
    AssessmentSuggestionResponse,
    LevelAssessmentActionResponse,
    LevelSuggestionResponse,
    ReadinessResponse,
)
from app.services import ai_level_service

router = APIRouter(prefix="/level-assessment", tags=["level-assessment"])


@router.get("/learners/{learner_id}", response_model=LevelSuggestionResponse)
async def get_level_suggestion(
    learner_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> LevelSuggestionResponse:
    data = await ai_level_service.get_latest_suggestion(
        db, learner_id=learner_id, parent_id=parent.id
    )
    return LevelSuggestionResponse(**data)


@router.post("/learners/{learner_id}/run", response_model=LevelSuggestionResponse)
async def run_level_assessment(
    learner_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> LevelSuggestionResponse:
    data = await ai_level_service.run_assessment(db, learner_id=learner_id, parent_id=parent.id)
    return LevelSuggestionResponse(**data)


@router.post("/{assessment_id}/accept", response_model=LevelAssessmentActionResponse)
async def accept_level_suggestion(
    assessment_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> LevelAssessmentActionResponse:
    data = await ai_level_service.accept_assessment(
        db, assessment_id=assessment_id, parent_id=parent.id
    )
    return LevelAssessmentActionResponse(**data)


@router.post("/{assessment_id}/dismiss", response_model=LevelAssessmentActionResponse)
async def dismiss_level_suggestion(
    assessment_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> LevelAssessmentActionResponse:
    data = await ai_level_service.dismiss_assessment(
        db, assessment_id=assessment_id, parent_id=parent.id
    )
    return LevelAssessmentActionResponse(**data)


@router.get("/learners/{learner_id}/readiness", response_model=ReadinessResponse)
async def get_learner_readiness(
    learner_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> ReadinessResponse:
    from sqlalchemy import select

    from app.models.learner import Learner
    from app.models.user import User as UserModel
    from app.services import readiness_service

    result = await db.execute(
        select(Learner)
        .join(UserModel, Learner.user_id == UserModel.id)
        .where(Learner.id == learner_id, UserModel.parent_id == parent.id)
    )
    learner = result.scalar_one_or_none()
    if learner is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learner not found")

    data = await readiness_service.calculate_readiness_score(db, learner, parent.id)
    return ReadinessResponse(**data)


@router.get("/learners/{learner_id}/should-suggest", response_model=AssessmentSuggestionResponse)
async def should_suggest_assessment(
    learner_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> AssessmentSuggestionResponse:
    from sqlalchemy import select

    from app.models.learner import Learner
    from app.models.user import User as UserModel
    from app.services import readiness_service

    result = await db.execute(
        select(Learner)
        .join(UserModel, Learner.user_id == UserModel.id)
        .where(Learner.id == learner_id, UserModel.parent_id == parent.id)
    )
    learner = result.scalar_one_or_none()
    if learner is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learner not found")

    data = await readiness_service.should_suggest_assessment(db, learner, parent.id)
    return AssessmentSuggestionResponse(**data)
