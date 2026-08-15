from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.sm2 import DEFAULT_EASE_FACTOR
from app.models.daily_challenge import DailyChallengeLog
from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.srs import SrsCard, SrsReviewLog
from app.models.user import User


async def _login(client, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_parent_dashboard_overview(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    leo_result = await db_session.execute(select(SrsCard).where(SrsCard.learner_id == 2))
    leo_cards = leo_result.scalars().all()
    if not leo_cards:
        pytest.skip("No SRS cards for Leo")

    response = await client.get(
        "/api/v1/dashboard/overview",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert response.status_code == 200
    learners = response.json()["learners"]
    assert len(learners) == 3
    names = {item["display_name"] for item in learners}
    assert names == {"Mia", "Leo", "Max"}


@pytest.mark.asyncio
async def test_learner_me_stats(client, db_session) -> None:
    leo_token = await _login(client, "leo", "leo")
    response = await client.get(
        "/api/v1/dashboard/me",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["english_level"] == "A1"
    assert payload["display_name"] == "Leo"
    assert "due_count" in payload
    assert "review_accuracy_percent" in payload
    assert "streak_days" in payload


@pytest.mark.asyncio
async def test_parent_cannot_access_learner_me(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    response = await client.get(
        "/api/v1/dashboard/me",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_learner_activity_after_review(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    leo_token = await _login(client, "leo", "leo")

    card_result = await db_session.execute(select(SrsCard).where(SrsCard.learner_id == 2).limit(1))
    card = card_result.scalar_one_or_none()
    if card is None:
        pytest.skip("No SRS card")

    await client.post(
        f"/api/v1/reviews/{card.id}/answer",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"quality": 4},
    )

    activity = await client.get(
        "/api/v1/dashboard/learners/2/activity",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert activity.status_code == 200
    assert len(activity.json()) >= 1


@pytest.mark.asyncio
async def test_family_trends_aggregates_and_zero_fills(client, db_session) -> None:
    leo = (
        await db_session.execute(select(Learner).join(User).where(User.username == "leo"))
    ).scalar_one()
    mia = (
        await db_session.execute(select(Learner).join(User).where(User.username == "mia"))
    ).scalar_one()

    now = datetime.now(UTC)
    today = now.date()
    two_days_ago = today - timedelta(days=2)
    three_days_ago = today - timedelta(days=3)

    entry = DictionaryEntry(
        word="trend-word",
        definition="A word for trends",
        source="test",
    )
    db_session.add(entry)
    await db_session.flush()

    card = SrsCard(
        learner_id=leo.id,
        dictionary_entry_id=entry.id,
        ease_factor=DEFAULT_EASE_FACTOR,
        interval_days=0,
        repetitions=0,
        due_at=now,
        state="new",
        released_at=datetime.combine(three_days_ago, datetime.min.time(), tzinfo=UTC),
    )
    db_session.add(card)
    await db_session.flush()

    db_session.add_all(
        [
            SrsReviewLog(
                srs_card_id=card.id,
                learner_id=leo.id,
                quality=4,
                reviewed_at=datetime.combine(two_days_ago, datetime.min.time(), tzinfo=UTC)
                + timedelta(hours=10),
            ),
            SrsReviewLog(
                srs_card_id=card.id,
                learner_id=leo.id,
                quality=2,
                reviewed_at=datetime.combine(two_days_ago, datetime.min.time(), tzinfo=UTC)
                + timedelta(hours=11),
            ),
            SrsReviewLog(
                srs_card_id=card.id,
                learner_id=leo.id,
                quality=5,
                reviewed_at=now - timedelta(hours=1),
            ),
            DailyChallengeLog(
                learner_id=leo.id,
                challenge_date=two_days_ago,
                new_count=3,
                retention_count=2,
                completed_at=datetime.combine(two_days_ago, datetime.min.time(), tzinfo=UTC)
                + timedelta(hours=12),
            ),
        ]
    )
    await db_session.commit()

    parent_token = await _login(client, "parent", "parent123")
    response = await client.get(
        "/api/v1/dashboard/trends?days=14",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 14
    assert len(payload["learners"]) == 3

    by_name = {item["display_name"]: item for item in payload["learners"]}
    leo_series = by_name["Leo"]
    mia_series = by_name["Mia"]
    max_series = by_name["Max"]
    assert len(leo_series["days"]) == 14
    assert len(mia_series["days"]) == 14
    assert len(max_series["days"]) == 14
    assert leo_series["days"][0]["date"] == (today - timedelta(days=13)).isoformat()
    assert leo_series["days"][-1]["date"] == today.isoformat()

    leo_by_date = {day["date"]: day for day in leo_series["days"]}
    two_ago = leo_by_date[two_days_ago.isoformat()]
    assert two_ago["reviews"] == 2
    assert two_ago["correct_reviews"] == 1
    assert two_ago["accuracy_percent"] == 50.0
    assert two_ago["challenge_completed"] is True

    three_ago = leo_by_date[three_days_ago.isoformat()]
    assert three_ago["new_words"] == 1
    assert three_ago["reviews"] == 0
    assert three_ago["learning_count"] == 0
    assert three_ago["familiar_count"] == 0
    assert three_ago["mastered_count"] == 0

    today_point = leo_by_date[today.isoformat()]
    assert today_point["reviews"] == 1
    assert today_point["correct_reviews"] == 1
    # Two distinct practice days (two_days_ago + today) → Familiar under 2/3 thresholds.
    assert today_point["learning_count"] == 0
    assert today_point["familiar_count"] >= 1

    # Quiet learner still gets a dense zero-filled series
    assert all(day["reviews"] == 0 for day in mia_series["days"])
    assert mia.id == mia_series["learner_id"]


@pytest.mark.asyncio
async def test_family_trends_clamps_days_and_rejects_learner(client) -> None:
    parent_token = await _login(client, "parent", "parent123")
    clamped = await client.get(
        "/api/v1/dashboard/trends?days=7",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert clamped.status_code == 200
    assert clamped.json()["days"] == 7
    assert all(len(item["days"]) == 7 for item in clamped.json()["learners"])

    leo_token = await _login(client, "leo", "leo")
    forbidden = await client.get(
        "/api/v1/dashboard/trends",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert forbidden.status_code == 403
