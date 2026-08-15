import pytest
from httpx import AsyncClient


async def _parent_token(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "parent", "password": "parent123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_parent_lists_learners(client: AsyncClient) -> None:
    token = await _parent_token(client)
    response = await client.get(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    names = {row["display_name"] for row in response.json()}
    assert "Mia" in names
    assert "Leo" in names


@pytest.mark.asyncio
async def test_create_learner_with_goals(client: AsyncClient) -> None:
    token = await _parent_token(client)
    response = await client.post(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "mia_test",
            "password": "mia123",
            "display_name": "Mia",
            "age": 11,
            "english_level": "A2",
            "daily_new_word_goal": 6,
            "daily_learning_retention_mix": 2,
            "daily_mastered_retention_mix": 1,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["username"] == "mia_test"
    assert payload["daily_practice_goal"] == 9
    assert payload["daily_new_word_goal"] == 6
    assert payload["daily_learning_retention_mix"] == 2
    assert payload["daily_mastered_retention_mix"] == 1
    assert payload["emoji"] == "🌟"
    assert payload["is_active"] is True


@pytest.mark.asyncio
async def test_create_learner_derives_ui_mode_from_age(client: AsyncClient) -> None:
    token = await _parent_token(client)
    younger = await client.post(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "younger_test",
            "password": "young123",
            "display_name": "Younger",
            "age": 11,
            "english_level": "A2",
        },
    )
    assert younger.status_code == 201
    assert younger.json()["ui_mode"] == "kid"
    assert younger.json()["daily_practice_goal"] == 7
    assert younger.json()["daily_new_word_goal"] == 5
    assert younger.json()["daily_learning_retention_mix"] == 1
    assert younger.json()["daily_mastered_retention_mix"] == 1

    older = await client.post(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "older_test",
            "password": "old123",
            "display_name": "Older",
            "age": 14,
            "english_level": "B1",
        },
    )
    assert older.status_code == 201
    assert older.json()["ui_mode"] == "teen"
    assert older.json()["daily_practice_goal"] == 10
    assert older.json()["daily_new_word_goal"] == 8
    assert older.json()["daily_learning_retention_mix"] == 1
    assert older.json()["daily_mastered_retention_mix"] == 1


@pytest.mark.asyncio
async def test_create_learner_defaults_by_ui_mode(client: AsyncClient) -> None:
    token = await _parent_token(client)
    response = await client.post(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "teen_test",
            "password": "teen123",
            "display_name": "Teen Kid",
            "age": 13,
            "english_level": "B1",
            "ui_mode": "teen",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["daily_practice_goal"] == 10
    assert payload["daily_new_word_goal"] == 8
    assert payload["daily_learning_retention_mix"] == 1
    assert payload["daily_mastered_retention_mix"] == 1


@pytest.mark.asyncio
async def test_create_learner_username_conflict(client: AsyncClient) -> None:
    token = await _parent_token(client)
    response = await client.post(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "mia",
            "password": "xxxxxx",
            "display_name": "Dup",
            "age": 10,
            "english_level": "A1",
            "ui_mode": "kid",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_learner_emoji(client: AsyncClient) -> None:
    token = await _parent_token(client)
    learners = await client.get(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
    )
    leo = next(row for row in learners.json() if row["username"] == "leo")
    assert leo["emoji"] == "🚀"
    response = await client.patch(
        f"/api/v1/learners/{leo['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"emoji": "🦊"},
    )
    assert response.status_code == 200
    assert response.json()["emoji"] == "🦊"

    listed = await client.get(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
    )
    leo_after = next(row for row in listed.json() if row["username"] == "leo")
    assert leo_after["emoji"] == "🦊"


@pytest.mark.asyncio
async def test_update_learner_goals(client: AsyncClient) -> None:
    token = await _parent_token(client)
    learners = await client.get(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
    )
    leo = next(row for row in learners.json() if row["username"] == "leo")
    response = await client.patch(
        f"/api/v1/learners/{leo['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "daily_new_word_goal": 7,
            "daily_learning_retention_mix": 1,
            "daily_mastered_retention_mix": 0,
        },
    )
    assert response.status_code == 200
    assert response.json()["daily_new_word_goal"] == 7
    assert response.json()["daily_learning_retention_mix"] == 1
    assert response.json()["daily_mastered_retention_mix"] == 0
    assert response.json()["daily_practice_goal"] == 8


@pytest.mark.asyncio
async def test_deactivate_learner(client: AsyncClient) -> None:
    token = await _parent_token(client)
    create = await client.post(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "temp_kid",
            "password": "temp123",
            "display_name": "Temp",
            "age": 9,
            "english_level": "A1",
            "ui_mode": "kid",
        },
    )
    learner_id = create.json()["id"]
    delete = await client.delete(
        f"/api/v1/learners/{learner_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete.status_code == 204
    detail = await client.get(
        f"/api/v1/learners/{learner_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.json()["is_active"] is False


@pytest.mark.asyncio
async def test_reset_password(client: AsyncClient) -> None:
    token = await _parent_token(client)
    create = await client.post(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "pw_kid",
            "password": "oldpass",
            "display_name": "PW Kid",
            "age": 10,
            "english_level": "A1",
            "ui_mode": "kid",
        },
    )
    learner_id = create.json()["id"]
    reset = await client.post(
        f"/api/v1/learners/{learner_id}/reset-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "newpass"},
    )
    assert reset.status_code == 204
    old_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "pw_kid", "password": "oldpass"},
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "pw_kid", "password": "newpass"},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_learner_cannot_manage_learners(client: AsyncClient) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "leo", "password": "leo"},
    )
    token = login.json()["access_token"]
    response = await client.post(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "hacker",
            "password": "hack",
            "display_name": "No",
            "age": 10,
            "english_level": "A1",
            "ui_mode": "kid",
        },
    )
    assert response.status_code == 403
