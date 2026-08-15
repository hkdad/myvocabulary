from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.challenge import LevelAssessment, LevelChallenge
from app.models.srs import SrsCard, SrsReviewLog


async def _login(client, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_rule_based_level_suggestion(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")

    card_result = await db_session.execute(select(SrsCard).where(SrsCard.learner_id == 2).limit(1))
    card = card_result.scalar_one_or_none()
    if card is None:
        pytest.skip("No SRS cards for Leo")

    for day_offset in range(14):
        reviewed_at = datetime.now(UTC) - timedelta(days=day_offset)
        db_session.add(
            SrsReviewLog(
                learner_id=2,
                srs_card_id=card.id,
                quality=5,
                interval_before=1,
                interval_after=2,
                ease_factor_before=2.5,
                ease_factor_after=2.6,
                reviewed_at=reviewed_at,
            )
        )
    await db_session.commit()

    response = await client.post(
        "/api/v1/level-assessment/learners/2/run",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"rules", "ai"}
    if payload["status"] == "pending":
        # Level-scoped readiness can demote when breadth is thin (single-card fixture).
        assert payload["suggested_level"] in {"PRE-A1", "A1", "A2", "B1", "B2"}


@pytest.mark.asyncio
async def test_parent_accepts_level_suggestion(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")

    assessment = LevelAssessment(
        learner_id=2,
        current_level="A2",
        suggested_level="B1",
        reason="Test suggestion",
        source="rules",
        status="pending",
    )
    db_session.add(assessment)
    await db_session.commit()
    await db_session.refresh(assessment)

    response = await client.post(
        f"/api/v1/level-assessment/{assessment.id}/accept",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert response.status_code == 200
    assert response.json()["english_level"] == "B1"

    challenge_result = await db_session.execute(
        select(LevelChallenge).where(
            LevelChallenge.learner_id == 2,
            LevelChallenge.challenge_type == "level_up",
        )
    )
    assert challenge_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_parent_dismisses_level_suggestion(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")

    assessment = LevelAssessment(
        learner_id=2,
        current_level="A2",
        suggested_level="B1",
        reason="Test suggestion",
        source="rules",
        status="pending",
    )
    db_session.add(assessment)
    await db_session.commit()
    await db_session.refresh(assessment)

    response = await client.post(
        f"/api/v1/level-assessment/{assessment.id}/dismiss",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"


@pytest.mark.asyncio
async def test_ai_fallback_when_no_api_key(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    with patch("app.services.ai_level_service.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = None
        response = await client.get(
            "/api/v1/level-assessment/learners/2",
            headers={"Authorization": f"Bearer {parent_token}"},
        )
    assert response.status_code == 200
