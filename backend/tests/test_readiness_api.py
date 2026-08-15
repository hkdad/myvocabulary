"""Integration tests for readiness API endpoints."""

import pytest
from sqlalchemy import select

from app.models.learner import Learner


async def _login(client, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_get_readiness_endpoint(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    leo = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()

    response = await client.get(
        f"/api/v1/level-assessment/learners/{leo.id}/readiness",
        headers={"Authorization": f"Bearer {parent_token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert "overall_score" in data
    assert "dimensions" in data
    assert "recommendation" in data
    assert "focus_areas" in data
    assert "estimated_weeks_to_ready" in data
    assert "metadata" in data

    assert isinstance(data["overall_score"], float)
    assert 0.0 <= data["overall_score"] <= 1.0
    assert data["recommendation"] in {"ready", "progressing", "keep_practicing"}

    for key in (
        "accuracy",
        "vocabulary_breadth",
        "retention",
        "consistency",
        "category_balance",
    ):
        assert key in data["dimensions"]


@pytest.mark.asyncio
async def test_should_suggest_assessment_endpoint(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    leo = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()

    response = await client.get(
        f"/api/v1/level-assessment/learners/{leo.id}/should-suggest",
        headers={"Authorization": f"Bearer {parent_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "should_suggest" in data
    assert "reason" in data
    assert "cooldown_days_remaining" in data
    assert isinstance(data["should_suggest"], bool)
    assert isinstance(data["cooldown_days_remaining"], int)


@pytest.mark.asyncio
async def test_readiness_endpoint_not_found(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    response = await client.get(
        "/api/v1/level-assessment/learners/99999/readiness",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_readiness_requires_parent_auth(client, db_session) -> None:
    leo_token = await _login(client, "leo", "leo")
    leo = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()

    response = await client.get(
        f"/api/v1/level-assessment/learners/{leo.id}/readiness",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert response.status_code == 403
