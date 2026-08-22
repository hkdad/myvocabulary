from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_learner
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.book import BookProgress
from app.schemas.loop import (
    ChallengeSourceOptionsResponse,
    DailyChallengeCompleteResponse,
    DailyChallengePhaseResponse,
    DailyMixResponse,
    LearnerWordsResponse,
    LoopProgressResponse,
    QuestsSummaryResponse,
    QuestStrengthSummary,
    RegenerateDailyMixRequest,
)
from app.services import achievement_service, book_service, loop_engine

router = APIRouter(prefix="/loop", tags=["loop"])


@router.get("/today", response_model=DailyMixResponse)
async def get_daily_mix(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> DailyMixResponse:
    learner = user.learner_profile
    if learner is None:
        return DailyMixResponse(
            cards=[],
            new_count=0,
            retention_count=0,
            daily_new_goal=5,
            daily_learning_retention_goal=1,
            daily_mastered_retention_goal=1,
            daily_retention_goal=2,
            new_released_today=0,
            completed_today=False,
            suggested=True,
            can_regenerate=False,
        )
    parent_id = await loop_engine.get_learner_parent_id(db, learner)
    if parent_id is None:
        return DailyMixResponse(
            cards=[],
            new_count=0,
            retention_count=0,
            daily_new_goal=learner.daily_new_word_goal or 5,
            daily_learning_retention_goal=learner.daily_learning_retention_mix or 1,
            daily_mastered_retention_goal=learner.daily_mastered_retention_mix or 1,
            daily_retention_goal=loop_engine.daily_retention_goal(learner),
            new_released_today=0,
            completed_today=False,
            suggested=True,
            can_regenerate=False,
        )
    data = await loop_engine.build_daily_mix(db, learner=learner, parent_id=parent_id)
    return DailyMixResponse(**data)


@router.get("/today/options", response_model=ChallengeSourceOptionsResponse)
async def get_challenge_source_options(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> ChallengeSourceOptionsResponse:
    learner = user.learner_profile
    if learner is None:
        return ChallengeSourceOptionsResponse(
            english_level="A1",
            categories=[],
            my_lists=[],
            can_regenerate=False,
        )
    parent_id = await loop_engine.get_learner_parent_id(db, learner)
    if parent_id is None:
        return ChallengeSourceOptionsResponse(
            english_level=learner.english_level,
            categories=[],
            my_lists=[],
            can_regenerate=False,
        )
    data = await loop_engine.challenge_source_options(db, learner=learner, parent_id=parent_id)
    return ChallengeSourceOptionsResponse(**data)


@router.post("/today/regenerate", response_model=DailyMixResponse)
async def regenerate_daily_mix(
    body: RegenerateDailyMixRequest,
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> DailyMixResponse:
    learner = user.learner_profile
    if learner is None:
        return DailyMixResponse(
            cards=[],
            new_count=0,
            retention_count=0,
            daily_new_goal=5,
            daily_learning_retention_goal=1,
            daily_mastered_retention_goal=1,
            daily_retention_goal=2,
            new_released_today=0,
            completed_today=False,
            suggested=True,
            can_regenerate=False,
        )
    parent_id = await loop_engine.get_learner_parent_id(db, learner)
    if parent_id is None:
        return DailyMixResponse(
            cards=[],
            new_count=0,
            retention_count=0,
            daily_new_goal=learner.daily_new_word_goal or 5,
            daily_learning_retention_goal=learner.daily_learning_retention_mix or 1,
            daily_mastered_retention_goal=learner.daily_mastered_retention_mix or 1,
            daily_retention_goal=loop_engine.daily_retention_goal(learner),
            new_released_today=0,
            completed_today=False,
            suggested=True,
            can_regenerate=False,
        )
    limiter.check(
        key=f"regen:{learner.id}",
        limit=5,
        window_seconds=24 * 60 * 60,
    )
    data = await loop_engine.regenerate_daily_mix(
        db,
        learner=learner,
        parent_id=parent_id,
        mode=body.mode,
        category=body.category,
        word_list_id=body.word_list_id,
    )
    return DailyMixResponse(**data)


@router.post("/today/srs-complete", response_model=DailyChallengePhaseResponse)
async def complete_srs_phase(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> DailyChallengePhaseResponse:
    learner = user.learner_profile
    if learner is None:
        return DailyChallengePhaseResponse(
            srs_completed=False,
            dictation_completed=False,
            completed=False,
            completed_at=None,
        )
    result = await loop_engine.mark_srs_phase_complete(db, learner_id=learner.id)
    completed_at = result["completed_at"]
    return DailyChallengePhaseResponse(
        srs_completed=result["srs_completed"],
        dictation_completed=result["dictation_completed"],
        completed=result["completed"],
        completed_at=completed_at.isoformat() if completed_at else None,
    )


@router.post("/today/complete", response_model=DailyChallengeCompleteResponse)
async def complete_daily_challenge(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> DailyChallengeCompleteResponse:
    learner = user.learner_profile
    if learner is None:
        return DailyChallengeCompleteResponse(completed=False, completed_at=None)
    result = await loop_engine.complete_daily_challenge(db, learner_id=learner.id)
    log = await loop_engine.get_today_challenge_log(db, learner_id=learner.id)
    completed_at = result["completed_at"]
    return DailyChallengeCompleteResponse(
        completed=result["completed"],
        completed_at=completed_at.isoformat() if completed_at else None,
        srs_completed=bool(log and log.srs_completed_at),
        dictation_completed=bool(log and log.dictation_completed_at),
    )


@router.get("/progress", response_model=LoopProgressResponse)
async def get_loop_progress(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> LoopProgressResponse:
    learner = user.learner_profile
    if learner is None:
        return LoopProgressResponse(
            learning_count=0,
            familiar_count=0,
            mastered_count=0,
            due_count=0,
            new_released_today=0,
            daily_new_goal=5,
            new_remaining_today=5,
            bank_total=0,
            bank_at_level=0,
            daily_challenge_completed=False,
        )
    data = await loop_engine.progress_summary(db, learner_id=learner.id)
    return LoopProgressResponse(**data)


@router.get("/book-progress", response_model=BookProgress | None)
async def get_book_progress(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> BookProgress | None:
    learner = user.learner_profile
    if learner is None:
        return None
    book = await book_service.get_active_book_for_learner(db, learner.id)
    if book is None:
        return None
    data = await book_service.progress_for_learner(db, book, learner.id)
    return BookProgress(**data)


@router.get("/words", response_model=LearnerWordsResponse)
async def get_learner_words(
    q: str | None = Query(default=None),
    level: str | None = Query(default=None),
    category: str | None = Query(default=None),
    strength: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> LearnerWordsResponse:
    learner = user.learner_profile
    if learner is None:
        return LearnerWordsResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
        )
    parent_id = await loop_engine.get_learner_parent_id(db, learner)
    data = await loop_engine.list_learner_words(
        db,
        learner=learner,
        parent_id=parent_id,
        query=q,
        level=level,
        category=category,
        strength=strength,
        page=page,
        page_size=page_size,
    )
    return LearnerWordsResponse(**data)


@router.get("/quests", response_model=QuestsSummaryResponse)
async def get_quests(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> QuestsSummaryResponse:
    learner = user.learner_profile
    if learner is None:
        empty_strength = QuestStrengthSummary(
            bank_total=0,
            released=0,
            learning=0,
            familiar=0,
            mastered=0,
        )
        return QuestsSummaryResponse(
            english_level="A1",
            overall=empty_strength,
            levels=[],
            packs=[],
            packs_by_level={},
            earned_pack_badges=0,
            earned_milestone_badges=0,
            total_pack_quests=0,
            completed_pack_quests=0,
        )
    parent_id = await loop_engine.get_learner_parent_id(db, learner)
    newly_earned = await achievement_service.sync_achievements(
        db, learner=learner, parent_id=parent_id
    )
    data = await achievement_service.get_quests_summary(db, learner=learner, parent_id=parent_id)
    data["newly_earned_badges"] = newly_earned
    return QuestsSummaryResponse(**data)
