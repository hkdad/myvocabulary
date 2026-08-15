from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_parent_learner, require_learner, require_parent
from app.database import get_db
from app.models.learner import Learner
from app.models.user import User
from app.schemas.dashboard import (
    ActivityItem,
    DashboardOverviewResponse,
    FamilyTrendsResponse,
    LearnerDetailResponse,
    LearnerMeStatsResponse,
    LearnerProgressSummary,
)
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverviewResponse)
async def dashboard_overview(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> DashboardOverviewResponse:
    data = await dashboard_service.get_overview(db, parent_id=parent.id)
    return DashboardOverviewResponse(
        learners=[LearnerProgressSummary(**item) for item in data["learners"]]
    )


@router.get("/trends", response_model=FamilyTrendsResponse)
async def dashboard_family_trends(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
    days: int = Query(default=14, ge=7, le=30),
) -> FamilyTrendsResponse:
    data = await dashboard_service.get_family_trends(db, parent_id=parent.id, days=days)
    return FamilyTrendsResponse(**data)


@router.get("/learners/{learner_id}", response_model=LearnerDetailResponse)
async def dashboard_learner_detail(
    learner: Learner = Depends(get_parent_learner),
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> LearnerDetailResponse:
    data = await dashboard_service.get_learner_detail(
        db, parent_id=parent.id, learner_id=learner.id
    )
    return LearnerDetailResponse(**data)


@router.get("/learners/{learner_id}/activity", response_model=list[ActivityItem])
async def dashboard_learner_activity(
    learner: Learner = Depends(get_parent_learner),
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ActivityItem]:
    items = await dashboard_service.get_activity(
        db, parent_id=parent.id, learner_id=learner.id, limit=limit
    )
    return [ActivityItem(**item) for item in items]


@router.get("/me", response_model=LearnerMeStatsResponse)
async def dashboard_me(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> LearnerMeStatsResponse:
    if user.learner_profile is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Learner profile missing")
    data = await dashboard_service.get_learner_me_stats(db, learner_id=user.learner_profile.id)
    return LearnerMeStatsResponse(**data)
