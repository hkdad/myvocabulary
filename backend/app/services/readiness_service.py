"""Multi-dimensional readiness scoring for level progression."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learner import Learner
from app.services import dashboard_service, performance_analytics

WEIGHT_ACCURACY = 0.30
WEIGHT_VOCABULARY_BREADTH = 0.25
WEIGHT_RETENTION = 0.15
WEIGHT_CONSISTENCY = 0.15
WEIGHT_CATEGORY_BALANCE = 0.15

READY_THRESHOLD = 0.75
PROGRESSING_THRESHOLD = 0.60


async def calculate_readiness_score(
    db: AsyncSession, learner: Learner, parent_id: int, *, level: str | None = None
) -> dict:
    """
    Calculate multi-dimensional readiness score for level progression.

    When ``level`` is set, metrics are scoped to that CEFR band (for per-level
    quest cards). Otherwise uses the learner's current ``english_level``.

    Returns:
    {
        "overall_score": 0.0-1.0,
        ...
    }
    """
    target_level = (level or learner.english_level).strip()
    metrics = await performance_analytics.get_performance_metrics(
        db, learner, parent_id, days=14, level=target_level
    )

    accuracy_score = _calculate_accuracy_score(
        metrics["review_accuracy"], metrics["dictation_accuracy"], metrics["review_samples"]
    )

    vocabulary_breadth_score = metrics["vocabulary_breadth"]["score"]
    retention_score = metrics["retention"]["score"]
    consistency_score = metrics["consistency"]["score"]
    category_balance_score = metrics["category_coverage"]["score"]

    overall_score = (
        accuracy_score * WEIGHT_ACCURACY
        + vocabulary_breadth_score * WEIGHT_VOCABULARY_BREADTH
        + retention_score * WEIGHT_RETENTION
        + consistency_score * WEIGHT_CONSISTENCY
        + category_balance_score * WEIGHT_CATEGORY_BALANCE
    )

    dimensions = {
        "accuracy": {
            "score": round(accuracy_score, 2),
            "weight": WEIGHT_ACCURACY,
            "status": _score_status(accuracy_score),
            "description": (
                f"{metrics['review_accuracy']}% recognition, "
                f"{metrics['dictation_accuracy']}% Listen & Pick / spelling (bonus)"
            ),
        },
        "vocabulary_breadth": {
            "score": round(vocabulary_breadth_score, 2),
            "weight": WEIGHT_VOCABULARY_BREADTH,
            "status": _score_status(vocabulary_breadth_score),
            "description": _vocabulary_breadth_description(
                metrics["vocabulary_breadth"], target_level
            ),
        },
        "retention": {
            "score": round(retention_score, 2),
            "weight": WEIGHT_RETENTION,
            "status": _score_status(retention_score),
            "description": f"{int(metrics['retention']['forgetting_rate'] * 100)}% forgetting rate",
        },
        "consistency": {
            "score": round(consistency_score, 2),
            "weight": WEIGHT_CONSISTENCY,
            "status": _score_status(consistency_score),
            "description": "Performance stability",
        },
        "category_balance": {
            "score": round(category_balance_score, 2),
            "weight": WEIGHT_CATEGORY_BALANCE,
            "status": _score_status(category_balance_score),
            "description": "Weakest released category at mastered strength",
        },
    }

    if overall_score >= READY_THRESHOLD:
        recommendation = "ready"
        estimated_weeks = 0
    elif overall_score >= PROGRESSING_THRESHOLD:
        recommendation = "progressing"
        estimated_weeks = _estimate_weeks_to_ready(overall_score, READY_THRESHOLD)
    else:
        recommendation = "keep_practicing"
        estimated_weeks = _estimate_weeks_to_ready(overall_score, PROGRESSING_THRESHOLD) + 2

    focus_areas = _generate_focus_areas(dimensions, metrics, target_level)

    streak_days = await dashboard_service._review_streak_days(db, learner.id)

    return {
        "overall_score": round(overall_score, 2),
        "dimensions": dimensions,
        "recommendation": recommendation,
        "focus_areas": focus_areas,
        "estimated_weeks_to_ready": estimated_weeks,
        "metadata": {
            "current_level": learner.english_level,
            "streak_days": streak_days,
            "review_samples": metrics["review_samples"],
            "total_mistakes": metrics["mistakes"]["total_mistakes"],
        },
    }


def _vocabulary_breadth_description(breadth: dict, current_level: str) -> str:
    """Human-readable breadth line among released words at the current level."""
    released = breadth.get("released_at_level", breadth.get("total_at_level", 0))
    return (
        f"{breadth['familiar_or_mastered']} familiar, {breadth['mastered']} mastered "
        f"of {released} released at {current_level}"
    )


def _calculate_accuracy_score(
    review_accuracy: float, dictation_accuracy: float, review_samples: int
) -> float:
    """
    Combine recognition and spelling accuracy with confidence adjustment.
    Recognition-first: 80% review, 20% dictation (bonus spelling).
    Low sample count reduces confidence.
    """
    if review_samples < 5:
        confidence_multiplier = 0.5
    elif review_samples < 10:
        confidence_multiplier = 0.7
    else:
        confidence_multiplier = 1.0

    combined = (review_accuracy * 0.8 + dictation_accuracy * 0.2) / 100.0
    return min(1.0, combined * confidence_multiplier)


def _score_status(score: float) -> str:
    """Convert numeric score to status label."""
    if score >= 0.85:
        return "excellent"
    elif score >= 0.75:
        return "strong"
    elif score >= 0.65:
        return "good"
    elif score >= 0.50:
        return "fair"
    else:
        return "weak"


def _estimate_weeks_to_ready(current_score: float, target_score: float) -> int:
    """
    Estimate weeks needed to reach target score.
    Assumes ~0.05 improvement per week with consistent practice.
    """
    gap = max(0, target_score - current_score)
    improvement_per_week = 0.05
    weeks = int((gap / improvement_per_week) + 0.5)
    return max(1, min(weeks, 8))


def _generate_focus_areas(dimensions: dict, metrics: dict, current_level: str) -> list[str]:
    """Generate actionable focus area recommendations."""
    focus_areas = []

    weak_dimensions = [
        (name, dim) for name, dim in dimensions.items() if dim["status"] in ["weak", "fair"]
    ]
    weak_dimensions.sort(key=lambda x: x[1]["score"])

    for name, dim in weak_dimensions[:3]:
        if name == "accuracy":
            focus_areas.append(
                f"Review accuracy at {int(dim['score'] * 100)}% — practice review sessions daily"
            )
        elif name == "vocabulary_breadth":
            breadth = metrics["vocabulary_breadth"]
            released = breadth.get("released_at_level", breadth.get("total_at_level", 0))
            remaining = released - breadth["familiar_or_mastered"]
            focus_areas.append(
                f"Get {remaining} more released {current_level} words to familiar strength"
            )
        elif name == "retention":
            forgetting_rate = int(metrics["retention"]["forgetting_rate"] * 100)
            focus_areas.append(
                f"Retention needs work — {forgetting_rate}% forgetting rate, review mistake book"
            )
        elif name == "consistency":
            focus_areas.append("Build consistency — aim for steady daily practice for 2 weeks")
        elif name == "category_balance":
            categories = metrics["category_coverage"]["categories"]
            weak_cats = [cat for cat, stats in categories.items() if stats["percentage"] < 0.60]
            if weak_cats:
                focus_areas.append(f"Practice {', '.join(weak_cats[:2])} categories")

    if dimensions["consistency"]["status"] in ["good", "strong", "excellent"]:
        focus_areas.append("Keep up the consistent practice — it's working!")

    if not focus_areas:
        focus_areas.append("Great progress across all areas — ready for level-up challenge!")

    return focus_areas[:4]


async def should_suggest_assessment(db: AsyncSession, learner: Learner, parent_id: int) -> dict:
    """
    Determine if an assessment should be auto-suggested to parent.

    Returns:
    {
        "should_suggest": bool,
        "reason": str | None,
        "cooldown_days_remaining": int
    }
    """
    from sqlalchemy import select

    from app.models.challenge import LevelAssessment

    cooldown_days = 7
    dismissed_cooldown_days = 14

    latest_result = await db.execute(
        select(LevelAssessment)
        .where(LevelAssessment.learner_id == learner.id)
        .order_by(LevelAssessment.assessed_at.desc())
        .limit(1)
    )
    latest_assessment = latest_result.scalar_one_or_none()

    if latest_assessment:
        now = datetime.now(UTC)
        assessed_at = latest_assessment.assessed_at
        if assessed_at.tzinfo is None:
            assessed_at = assessed_at.replace(tzinfo=UTC)
        days_since = (now - assessed_at).days

        if latest_assessment.status == "dismissed":
            required_cooldown = dismissed_cooldown_days
        else:
            required_cooldown = cooldown_days

        if days_since < required_cooldown:
            remaining = required_cooldown - days_since
            if latest_assessment.status == "pending":
                reason = (
                    "A suggestion is already pending — Accept or Dismiss it, "
                    "or use Run check anytime"
                )
            elif latest_assessment.status == "accepted":
                reason = (
                    f"Recent level change — next auto-nudge in {remaining} day(s). "
                    "Run check still works anytime"
                )
            else:
                reason = (
                    f"Assessment cooldown active ({remaining} day(s) left). "
                    "Run check still works anytime"
                )
            return {
                "should_suggest": False,
                "reason": reason,
                "cooldown_days_remaining": remaining,
            }

    readiness = await calculate_readiness_score(db, learner, parent_id)

    overall_score = readiness["overall_score"]
    review_samples = readiness["metadata"]["review_samples"]
    streak_days = readiness["metadata"]["streak_days"]

    if review_samples < 10:
        return {
            "should_suggest": False,
            "reason": "Not enough review data yet",
            "cooldown_days_remaining": 0,
        }

    if overall_score >= READY_THRESHOLD and streak_days >= 7:
        return {
            "should_suggest": True,
            "reason": f"Readiness score {int(overall_score * 100)}% with {streak_days}-day streak",
            "cooldown_days_remaining": 0,
        }

    return {
        "should_suggest": False,
        "reason": f"Readiness score {int(overall_score * 100)}% — continue practicing",
        "cooldown_days_remaining": 0,
    }
