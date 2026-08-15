"""Unit tests for readiness-gated level suggestion rules."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services import ai_level_service


def _readiness(*, overall: float, focus_areas: list[str] | None = None) -> dict:
    return {
        "overall_score": overall,
        "dimensions": {
            "accuracy": {"score": overall, "status": "strong" if overall >= 0.75 else "weak"},
            "vocabulary_breadth": {
                "score": overall,
                "status": "strong" if overall >= 0.75 else "fair",
            },
            "retention": {"score": overall, "status": "good"},
            "consistency": {"score": overall, "status": "good"},
            "category_balance": {"score": overall, "status": "fair"},
        },
        "focus_areas": focus_areas or ["Practice daily"],
    }


def test_clamp_adjacent_level_allows_next_and_previous() -> None:
    assert ai_level_service._clamp_adjacent_level("A1", "A2") == "A2"
    assert ai_level_service._clamp_adjacent_level("A2", "A1") == "A1"
    assert ai_level_service._clamp_adjacent_level("A1", "B1") is None
    assert ai_level_service._clamp_adjacent_level("A1", "PRE-A1") == "PRE-A1"
    assert ai_level_service._clamp_adjacent_level("A1", "C2") is None


def test_rules_promote_when_ready() -> None:
    suggestion = ai_level_service._rule_based_suggestion_enhanced(
        current_level="A1",
        review_samples=12,
        readiness=_readiness(overall=0.80),
    )
    assert suggestion is not None
    assert suggestion["suggested_level"] == "A2"
    assert suggestion["source"] == "rules"


def test_rules_no_promote_below_ready_even_with_samples() -> None:
    suggestion = ai_level_service._rule_based_suggestion_enhanced(
        current_level="A1",
        review_samples=50,
        readiness=_readiness(overall=0.74),
    )
    assert suggestion is None


def test_rules_no_promote_without_enough_samples() -> None:
    suggestion = ai_level_service._rule_based_suggestion_enhanced(
        current_level="A1",
        review_samples=9,
        readiness=_readiness(overall=0.90),
    )
    assert suggestion is None


def test_rules_demote_when_very_low() -> None:
    suggestion = ai_level_service._rule_based_suggestion_enhanced(
        current_level="A2",
        review_samples=15,
        readiness=_readiness(overall=0.40),
    )
    assert suggestion is not None
    assert suggestion["suggested_level"] == "A1"


def test_rules_no_demote_at_floor() -> None:
    suggestion = ai_level_service._rule_based_suggestion_enhanced(
        current_level="PRE-A1",
        review_samples=20,
        readiness=_readiness(overall=0.20),
    )
    assert suggestion is None


@pytest.mark.asyncio
async def test_run_assessment_ignores_ai_skip_level(db_session) -> None:
    """AI narrative cannot invent a skip; rules own the target (none when not ready)."""
    from app.core.security import hash_password
    from app.models.learner import Learner
    from app.models.user import User

    parent = User(
        username="parent_ai_clamp",
        password_hash=hash_password("parent123"),
        role="parent",
        is_active=True,
    )
    db_session.add(parent)
    await db_session.flush()
    user = User(
        username="learner_ai_clamp",
        password_hash=hash_password("x"),
        role="learner",
        parent_id=parent.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    learner = Learner(
        user_id=user.id,
        display_name="Clamp",
        age=10,
        english_level="A1",
        ui_mode="kid",
    )
    db_session.add(learner)
    await db_session.commit()
    await db_session.refresh(learner)
    await db_session.refresh(parent)

    fake_metrics = {
        "review_accuracy": 95.0,
        "review_samples": 50,
        "dictation_accuracy": 90.0,
        "category_coverage": {"categories": {}},
        "vocabulary_breadth": {"score": 0.5},
        "retention": {"score": 0.5, "forgetting_rate": 0.1},
        "consistency": {"score": 0.5},
        "mistakes": {"total_mistakes": 0},
    }
    fake_readiness = _readiness(overall=0.50)

    with (
        patch(
            "app.services.performance_analytics.get_performance_metrics",
            new=AsyncMock(return_value=fake_metrics),
        ),
        patch(
            "app.services.readiness_service.calculate_readiness_score",
            new=AsyncMock(return_value=fake_readiness),
        ),
        patch(
            "app.services.dashboard_service._review_streak_days",
            new=AsyncMock(return_value=14),
        ),
        patch(
            "app.services.ai_level_service._dictation_accuracy",
            new=AsyncMock(return_value=(90.0, 3)),
        ),
        patch(
            "app.services.ai_level_service._ai_narrative",
            new=AsyncMock(
                return_value={
                    "suggested_level": None,  # clamp rejected B1 skip
                    "reason": "Strengths: streak. Concerns: breadth",
                    "source": "ai",
                    "focus_areas": ["More breadth"],
                    "confidence": 0.9,
                }
            ),
        ),
    ):
        result = await ai_level_service.run_assessment(
            db_session, learner_id=learner.id, parent_id=parent.id
        )

    assert result["status"] == "none"
    assert result["suggested_level"] == "A1"


@pytest.mark.asyncio
async def test_run_assessment_promotes_from_rules_with_ai_reason(db_session) -> None:
    from app.core.security import hash_password
    from app.models.learner import Learner
    from app.models.user import User

    parent = User(
        username="parent_ai_promote",
        password_hash=hash_password("parent123"),
        role="parent",
        is_active=True,
    )
    db_session.add(parent)
    await db_session.flush()
    user = User(
        username="learner_ai_promote",
        password_hash=hash_password("x"),
        role="learner",
        parent_id=parent.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    learner = Learner(
        user_id=user.id,
        display_name="Promote",
        age=10,
        english_level="A1",
        ui_mode="kid",
    )
    db_session.add(learner)
    await db_session.commit()
    await db_session.refresh(learner)
    await db_session.refresh(parent)

    fake_metrics = {
        "review_accuracy": 95.0,
        "review_samples": 20,
        "dictation_accuracy": 50.0,
        "category_coverage": {"categories": {}},
        "vocabulary_breadth": {"score": 0.9},
        "retention": {"score": 0.9, "forgetting_rate": 0.0},
        "consistency": {"score": 0.9},
        "mistakes": {"total_mistakes": 0},
    }
    fake_readiness = _readiness(overall=0.82)

    with (
        patch(
            "app.services.performance_analytics.get_performance_metrics",
            new=AsyncMock(return_value=fake_metrics),
        ),
        patch(
            "app.services.readiness_service.calculate_readiness_score",
            new=AsyncMock(return_value=fake_readiness),
        ),
        patch(
            "app.services.dashboard_service._review_streak_days",
            new=AsyncMock(return_value=10),
        ),
        patch(
            "app.services.ai_level_service._dictation_accuracy",
            new=AsyncMock(return_value=(50.0, 1)),
        ),
        patch(
            "app.services.ai_level_service._ai_narrative",
            new=AsyncMock(
                return_value={
                    "suggested_level": "A2",
                    "reason": "Strengths: strong recognition",
                    "source": "ai",
                    "focus_areas": ["Keep it up"],
                    "confidence": 0.88,
                }
            ),
        ),
    ):
        result = await ai_level_service.run_assessment(
            db_session, learner_id=learner.id, parent_id=parent.id
        )

    assert result["status"] == "pending"
    assert result["suggested_level"] == "A2"
    assert result["source"] == "ai"
    assert "strong recognition" in (result["reason"] or "")
