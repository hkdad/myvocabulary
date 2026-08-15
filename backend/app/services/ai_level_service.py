import json
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.cefr import CEFR_LEVELS, next_level, previous_level
from app.models.challenge import LevelAssessment
from app.models.dictation import DictationSession
from app.models.learner import Learner
from app.models.user import User
from app.services import dashboard_service
from app.services.readiness_service import READY_THRESHOLD

PROMOTE_MIN_SAMPLES = 10
DEMOTE_THRESHOLD = 0.45


async def _learner_for_parent(db: AsyncSession, *, learner_id: int, parent_id: int) -> Learner:
    result = await db.execute(
        select(Learner)
        .join(User, Learner.user_id == User.id)
        .where(Learner.id == learner_id, User.parent_id == parent_id)
    )
    learner = result.scalar_one_or_none()
    if learner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learner not found")
    return learner


async def _dictation_accuracy(db: AsyncSession, learner_id: int, days: int) -> tuple[float, int]:
    since = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(DictationSession.correct_count, DictationSession.total_words).where(
            DictationSession.learner_id == learner_id,
            DictationSession.completed_at.is_not(None),
            DictationSession.completed_at >= since,
        )
    )
    rows = result.all()
    total_words = sum(row[1] for row in rows)
    if total_words == 0:
        return 0.0, 0
    correct_words = sum(row[0] for row in rows)
    return round((correct_words / total_words) * 100, 1), len(rows)


def _clamp_adjacent_level(current_level: str, suggested_level: str) -> str | None:
    """Return suggested only if it is exactly next or previous CEFR step."""
    suggested = suggested_level.strip().upper()
    if suggested not in CEFR_LEVELS:
        return None
    promoted = next_level(current_level)
    demoted = previous_level(current_level)
    if promoted and suggested == promoted.upper():
        return promoted
    if demoted and suggested == demoted.upper():
        return demoted
    return None


def _rule_based_suggestion_enhanced(
    *,
    current_level: str,
    review_samples: int,
    readiness: dict,
) -> dict | None:
    """Readiness-gated adjacent CEFR suggestion. No streak/dictation shortcuts."""
    promoted = next_level(current_level)
    demoted = previous_level(current_level)

    overall_score = readiness["overall_score"]
    dimensions = readiness["dimensions"]

    if overall_score >= READY_THRESHOLD and promoted and review_samples >= PROMOTE_MIN_SAMPLES:
        focus_areas = readiness.get("focus_areas", [])
        return {
            "suggested_level": promoted,
            "confidence": min(0.95, overall_score),
            "reason": (
                f"Readiness score {int(overall_score * 100)}% — "
                f"strong performance across all dimensions."
            ),
            "source": "rules",
            "focus_areas": focus_areas[:2],
        }

    if overall_score < DEMOTE_THRESHOLD and demoted and review_samples >= PROMOTE_MIN_SAMPLES:
        weak_areas = [name for name, dim in dimensions.items() if dim["status"] in ["weak", "fair"]]
        return {
            "suggested_level": demoted,
            "confidence": 0.75,
            "reason": (
                f"Readiness score {int(overall_score * 100)}% — "
                f"consider reinforcing {demoted} material. "
                f"Focus on: {', '.join(weak_areas[:2])}"
            ),
            "source": "rules",
            "focus_areas": readiness.get("focus_areas", [])[:2],
        }

    return None


async def _ai_narrative(
    *,
    learner_name: str,
    current_level: str,
    review_accuracy: float,
    dictation_accuracy: float,
    streak_days: int,
    review_samples: int,
    learner_age: int | None = None,
    ui_mode: str = "kid",
    readiness_metrics: dict | None = None,
) -> dict | None:
    """Ask AI for reason/focus text only. Target level is decided by rules."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    system = """You are an expert English vocabulary coach for children aged 8-14.
Explain readiness for CEFR level progression using these principles:

1. **Accuracy alone is not enough** — consistency and breadth matter
2. **Different pacing for different ages** — younger children need more time
3. **Gaps are red flags** — category imbalances suggest rushed progression
4. **Trend matters** — improving performance is better than plateauing

Suggest only the adjacent CEFR step (next or previous), never skip levels.
Reply with JSON only (no markdown):
{
  "suggested_level": "PRE-A1|A1|A2|B1|B2|C1|C2",
  "confidence": 0.0-1.0,
  "reasoning": {
    "strengths": ["list of 2-3 strengths"],
    "concerns": ["list of 0-3 concerns"],
    "recommendation": "ready|wait_1_week|wait_2_weeks|needs_focus"
  },
  "focus_areas": ["list of 1-3 specific actionable tips"],
  "estimated_ready_in_days": 0-60
}"""

    metrics_data = readiness_metrics or {}
    dimensions = metrics_data.get("dimensions", {})
    category_coverage = metrics_data.get("category_coverage", {})

    prompt = {
        "learner": {
            "name": learner_name,
            "age": learner_age,
            "ui_mode": ui_mode,
            "current_level": current_level,
        },
        "performance": {
            "review_accuracy_14d": review_accuracy,
            "dictation_accuracy_30d": dictation_accuracy,
            "review_samples": review_samples,
            "streak_days": streak_days,
        },
    }

    if dimensions:
        prompt["performance"]["consistency_score"] = dimensions.get("consistency", {}).get(
            "score", 0.5
        )
        prompt["performance"]["vocabulary_breadth"] = dimensions.get("vocabulary_breadth", {}).get(
            "score", 0.5
        )
        prompt["performance"]["retention_strength"] = dimensions.get("retention", {}).get(
            "score", 0.5
        )

    if category_coverage:
        prompt["category_coverage"] = {
            cat: stats["percentage"] for cat, stats in category_coverage.items()
        }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.openai_api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(prompt)},
                    ],
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            content_clean = content.strip()
            if content_clean.startswith("```"):
                lines = content_clean.split("\n")
                content_clean = "\n".join(lines[1:-1]) if len(lines) > 2 else content_clean

            payload = json.loads(content_clean)
            suggested_raw = str(payload.get("suggested_level", current_level)).upper()
            clamped = _clamp_adjacent_level(current_level, suggested_raw)

            reasoning = payload.get("reasoning", {})
            focus_areas = payload.get("focus_areas", [])
            estimated_days = payload.get("estimated_ready_in_days", 0)

            strengths = reasoning.get("strengths", []) if isinstance(reasoning, dict) else []
            concerns = reasoning.get("concerns", []) if isinstance(reasoning, dict) else []
            recommendation = (
                reasoning.get("recommendation", "ready") if isinstance(reasoning, dict) else "ready"
            )

            reason_parts = []
            if strengths:
                reason_parts.append("Strengths: " + ", ".join(strengths[:2]))
            if concerns:
                reason_parts.append("Concerns: " + ", ".join(concerns[:2]))

            reason_text = (
                ". ".join(reason_parts)
                if reason_parts
                else "AI assessment based on performance metrics."
            )

            return {
                "suggested_level": clamped,
                "confidence": float(payload.get("confidence", 0.8)),
                "reason": reason_text,
                "source": "ai",
                "focus_areas": focus_areas[:3] if isinstance(focus_areas, list) else [],
                "recommendation": recommendation,
                "estimated_ready_in_days": min(60, max(0, int(estimated_days))),
            }
    except Exception:
        return None


async def run_assessment(db: AsyncSession, *, learner_id: int, parent_id: int) -> dict:
    from app.services import performance_analytics, readiness_service

    learner = await _learner_for_parent(db, learner_id=learner_id, parent_id=parent_id)
    streak_days = await dashboard_service._review_streak_days(db, learner.id)

    metrics = await performance_analytics.get_performance_metrics(db, learner, parent_id)
    readiness = await readiness_service.calculate_readiness_score(db, learner, parent_id)

    # Level-scoped recognition accuracy (same scope as readiness).
    review_accuracy = float(metrics["review_accuracy"])
    review_samples = int(metrics["review_samples"])
    dictation_accuracy, _ = await _dictation_accuracy(db, learner.id, days=30)

    rule = _rule_based_suggestion_enhanced(
        current_level=learner.english_level,
        review_samples=review_samples,
        readiness=readiness,
    )

    ai = await _ai_narrative(
        learner_name=learner.display_name,
        current_level=learner.english_level,
        review_accuracy=review_accuracy,
        dictation_accuracy=dictation_accuracy,
        streak_days=streak_days,
        review_samples=review_samples,
        learner_age=learner.age,
        ui_mode=learner.ui_mode,
        readiness_metrics={
            "dimensions": readiness["dimensions"],
            "category_coverage": metrics["category_coverage"]["categories"],
        },
    )

    # Rules own the target level; AI may only rewrite narrative.
    if rule is None:
        reason = "Keep practicing — not enough data for a level change yet."
        if readiness.get("focus_areas"):
            reason = readiness["focus_areas"][0]
        elif ai and ai.get("reason"):
            reason = str(ai["reason"])
        return {
            "id": None,
            "learner_id": learner.id,
            "current_level": learner.english_level,
            "suggested_level": learner.english_level,
            "reason": reason,
            "source": "rules",
            "confidence": None,
            "status": "none",
            "assessed_at": None,
        }

    suggestion = dict(rule)
    if ai and ai.get("reason"):
        suggestion["reason"] = ai["reason"]
        suggestion["source"] = "ai"
        if ai.get("focus_areas"):
            suggestion["focus_areas"] = ai["focus_areas"]
        if ai.get("confidence") is not None:
            suggestion["confidence"] = ai["confidence"]

    if suggestion["suggested_level"].upper() == learner.english_level.upper():
        return {
            "id": None,
            "learner_id": learner.id,
            "current_level": learner.english_level,
            "suggested_level": learner.english_level,
            "reason": suggestion["reason"],
            "source": suggestion["source"],
            "confidence": suggestion.get("confidence"),
            "status": "none",
            "assessed_at": None,
        }

    pending = await db.execute(
        select(LevelAssessment).where(
            LevelAssessment.learner_id == learner.id,
            LevelAssessment.status == "pending",
        )
    )
    for existing in pending.scalars().all():
        existing.status = "dismissed"
        existing.resolved_at = datetime.now(UTC)

    assessment = LevelAssessment(
        learner_id=learner.id,
        current_level=learner.english_level,
        suggested_level=suggestion["suggested_level"],
        reason=suggestion["reason"],
        source=suggestion["source"],
        status="pending",
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)

    return {
        "id": assessment.id,
        "learner_id": learner.id,
        "current_level": assessment.current_level,
        "suggested_level": assessment.suggested_level,
        "reason": assessment.reason,
        "source": assessment.source,
        "confidence": suggestion.get("confidence"),
        "status": assessment.status,
        "assessed_at": assessment.assessed_at,
    }


async def get_latest_suggestion(db: AsyncSession, *, learner_id: int, parent_id: int) -> dict:
    await _learner_for_parent(db, learner_id=learner_id, parent_id=parent_id)
    result = await db.execute(
        select(LevelAssessment)
        .where(LevelAssessment.learner_id == learner_id)
        .order_by(LevelAssessment.assessed_at.desc())
        .limit(1)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None or assessment.status != "pending":
        learner_result = await db.execute(select(Learner).where(Learner.id == learner_id))
        learner = learner_result.scalar_one()
        return {
            "id": None,
            "learner_id": learner_id,
            "current_level": learner.english_level,
            "suggested_level": learner.english_level,
            "reason": None,
            "source": "rules",
            "confidence": None,
            "status": "none",
            "assessed_at": None,
        }

    return {
        "id": assessment.id,
        "learner_id": assessment.learner_id,
        "current_level": assessment.current_level,
        "suggested_level": assessment.suggested_level,
        "reason": assessment.reason,
        "source": assessment.source,
        "confidence": None,
        "status": assessment.status,
        "assessed_at": assessment.assessed_at,
    }


async def _get_assessment_for_parent(
    db: AsyncSession, *, assessment_id: int, parent_id: int
) -> LevelAssessment:
    result = await db.execute(
        select(LevelAssessment)
        .join(Learner, LevelAssessment.learner_id == Learner.id)
        .join(User, Learner.user_id == User.id)
        .where(LevelAssessment.id == assessment_id, User.parent_id == parent_id)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return assessment


async def accept_assessment(db: AsyncSession, *, assessment_id: int, parent_id: int) -> dict:
    from app.services import challenge_service

    assessment = await _get_assessment_for_parent(
        db, assessment_id=assessment_id, parent_id=parent_id
    )
    if assessment.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Assessment is not pending"
        )

    learner_result = await db.execute(select(Learner).where(Learner.id == assessment.learner_id))
    learner = learner_result.scalar_one()
    learner.english_level = assessment.suggested_level
    assessment.status = "accepted"
    assessment.resolved_at = datetime.now(UTC)

    await challenge_service.assign_catalog_lists_for_level(
        db, learner_id=learner.id, parent_id=parent_id, level=assessment.suggested_level
    )
    await challenge_service.create_level_up_challenge(
        db,
        learner_id=learner.id,
        target_level=assessment.suggested_level,
    )

    await db.commit()
    return {
        "assessment_id": assessment.id,
        "learner_id": learner.id,
        "english_level": learner.english_level,
        "status": assessment.status,
    }


async def dismiss_assessment(db: AsyncSession, *, assessment_id: int, parent_id: int) -> dict:
    assessment = await _get_assessment_for_parent(
        db, assessment_id=assessment_id, parent_id=parent_id
    )
    if assessment.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Assessment is not pending"
        )

    assessment.status = "dismissed"
    assessment.resolved_at = datetime.now(UTC)
    await db.commit()
    return {
        "assessment_id": assessment.id,
        "learner_id": assessment.learner_id,
        "english_level": assessment.current_level,
        "status": assessment.status,
    }
