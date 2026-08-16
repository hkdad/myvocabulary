from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_parent_learner, require_parent
from app.core.security import hash_password
from app.database import get_db
from app.models.learner import Learner
from app.models.srs import SrsReviewLog
from app.models.user import RefreshToken, User
from app.schemas.learner import (
    LearnerCreateRequest,
    LearnerResponse,
    LearnerUpdateRequest,
    ResetPasswordRequest,
)
from app.schemas.loop import QuestsSummaryResponse
from app.services import achievement_service, loop_engine
from app.services.learner_profile import resolve_learner_emoji

router = APIRouter(prefix="/learners", tags=["learners"])


def _ui_mode_for_age(age: int) -> str:
    return "teen" if age >= 13 else "kid"


def _default_goals_for_ui_mode(ui_mode: str) -> tuple[int, int, int]:
    if ui_mode == "teen":
        return 8, 1, 1
    return 5, 1, 1


def learner_to_response(learner: Learner) -> LearnerResponse:
    return LearnerResponse(
        id=learner.id,
        user_id=learner.user_id,
        username=learner.user.username,
        display_name=learner.display_name,
        age=learner.age,
        english_level=learner.english_level,
        ui_mode=learner.ui_mode,
        emoji=resolve_learner_emoji(learner.emoji, learner.display_name),
        avatar_url=learner.avatar_url,
        daily_practice_goal=loop_engine.daily_practice_goal(learner),
        daily_new_word_goal=loop_engine.daily_new_goal(learner),
        daily_learning_retention_mix=loop_engine.daily_learning_retention_goal(learner),
        daily_mastered_retention_mix=loop_engine.daily_mastered_retention_goal(learner),
        is_active=learner.user.is_active,
    )


@router.get("", response_model=list[LearnerResponse])
async def list_learners(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> list[LearnerResponse]:
    result = await db.execute(
        select(Learner)
        .join(User, Learner.user_id == User.id)
        .options(selectinload(Learner.user))
        .where(User.parent_id == parent.id)
        .order_by(Learner.display_name)
    )
    return [learner_to_response(learner) for learner in result.scalars().all()]


@router.post("", response_model=LearnerResponse, status_code=status.HTTP_201_CREATED)
async def create_learner(
    payload: LearnerCreateRequest,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> LearnerResponse:
    existing = await db.execute(select(User).where(User.username == payload.username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role="learner",
        parent_id=parent.id,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    ui_mode = payload.ui_mode or _ui_mode_for_age(payload.age)
    (
        new_default,
        learning_retention_default,
        mastered_retention_default,
    ) = _default_goals_for_ui_mode(ui_mode)
    new_goal = payload.daily_new_word_goal or new_default
    learning_retention_goal = (
        payload.daily_learning_retention_mix
        if payload.daily_learning_retention_mix is not None
        else learning_retention_default
    )
    mastered_retention_goal = (
        payload.daily_mastered_retention_mix
        if payload.daily_mastered_retention_mix is not None
        else mastered_retention_default
    )
    learner = Learner(
        user_id=user.id,
        display_name=payload.display_name,
        age=payload.age,
        english_level=payload.english_level,
        ui_mode=ui_mode,
        emoji=resolve_learner_emoji(payload.emoji, payload.display_name),
        daily_review_goal=new_goal + learning_retention_goal + mastered_retention_goal,
        daily_new_word_goal=new_goal,
        daily_learning_retention_mix=learning_retention_goal,
        daily_mastered_retention_mix=mastered_retention_goal,
    )
    db.add(learner)
    await db.commit()
    await db.refresh(learner)
    await db.refresh(user, attribute_names=["username", "is_active"])
    learner.user = user
    return learner_to_response(learner)


@router.get("/{learner_id}", response_model=LearnerResponse)
async def get_learner(learner: Learner = Depends(get_parent_learner)) -> LearnerResponse:
    return learner_to_response(learner)


@router.get("/{learner_id}/quests", response_model=QuestsSummaryResponse)
async def get_learner_quests(
    learner: Learner = Depends(get_parent_learner),
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> QuestsSummaryResponse:
    data = await achievement_service.get_quests_summary(db, learner=learner, parent_id=parent.id)
    data["newly_earned_badges"] = []
    return QuestsSummaryResponse(**data)


@router.patch("/{learner_id}", response_model=LearnerResponse)
async def update_learner(
    payload: LearnerUpdateRequest,
    learner: Learner = Depends(get_parent_learner),
    db: AsyncSession = Depends(get_db),
) -> LearnerResponse:
    if payload.display_name is not None:
        learner.display_name = payload.display_name
    if payload.age is not None:
        learner.age = payload.age
    if payload.english_level is not None:
        learner.english_level = payload.english_level
    if payload.ui_mode is not None:
        learner.ui_mode = payload.ui_mode
    if payload.emoji is not None:
        cleaned = payload.emoji.strip()
        if cleaned:
            learner.emoji = cleaned
    if payload.daily_new_word_goal is not None:
        learner.daily_new_word_goal = payload.daily_new_word_goal
    if payload.daily_learning_retention_mix is not None:
        learner.daily_learning_retention_mix = payload.daily_learning_retention_mix
    if payload.daily_mastered_retention_mix is not None:
        learner.daily_mastered_retention_mix = payload.daily_mastered_retention_mix
    if (
        payload.daily_new_word_goal is not None
        or payload.daily_learning_retention_mix is not None
        or payload.daily_mastered_retention_mix is not None
    ):
        learner.daily_review_goal = loop_engine.daily_practice_goal(learner)
    if payload.is_active is not None:
        learner.user.is_active = payload.is_active
    await db.commit()
    result = await db.execute(
        select(Learner).options(selectinload(Learner.user)).where(Learner.id == learner.id)
    )
    learner = result.scalar_one()
    return learner_to_response(learner)


@router.delete("/{learner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_learner(
    learner: Learner = Depends(get_parent_learner),
    db: AsyncSession = Depends(get_db),
) -> None:
    user_id = learner.user_id
    learner_id = learner.id
    try:
        await db.execute(delete(SrsReviewLog).where(SrsReviewLog.learner_id == learner_id))
        learner_result = await db.execute(delete(Learner).where(Learner.id == learner_id))
        if learner_result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learner not found")
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not delete learner because related records still exist",
        ) from exc


@router.post("/{learner_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordRequest,
    learner: Learner = Depends(get_parent_learner),
    db: AsyncSession = Depends(get_db),
) -> None:
    learner.user.password_hash = hash_password(payload.password)
    await db.commit()


@router.post("/{learner_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_sessions(
    learner: Learner = Depends(get_parent_learner),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == learner.user_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    now = datetime.now(UTC)
    for token in result.scalars().all():
        token.revoked_at = now
    await db.commit()
