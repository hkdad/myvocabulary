from fastapi import APIRouter

from app.api.v1 import (
    auth,
    challenges,
    dashboard,
    dictation,
    dictionary,
    learners,
    level_assessment,
    loop,
    reviews,
    word_bank,
    word_lists,
)

router = APIRouter()

router.include_router(auth.router)
router.include_router(learners.router)
router.include_router(dictionary.router)
router.include_router(word_lists.router)
router.include_router(word_bank.router)
router.include_router(reviews.router)
router.include_router(loop.router)
router.include_router(dictation.router)
router.include_router(dashboard.router)
router.include_router(level_assessment.router)
router.include_router(challenges.router)


@router.get("/status")
async def api_status() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}
