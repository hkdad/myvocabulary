import pytest


@pytest.mark.asyncio
async def test_login_parent(client) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "parent", "password": "parent123"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "access_token" in payload
    assert response.cookies.get("refresh_token")


@pytest.mark.asyncio
async def test_login_invalid_credentials(client) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "parent", "password": "wrong"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_picks_returns_family_accounts(client) -> None:
    response = await client.get("/api/v1/auth/login-picks")
    assert response.status_code == 200
    picks = response.json()
    labels = {pick["label"] for pick in picks}
    assert "Parent" in labels
    assert "Mia" in labels
    assert "Leo" in labels
    assert "Max" in labels
    assert all("username" not in pick for pick in picks)
    leo = next(pick for pick in picks if pick["label"] == "Leo")
    assert leo["emoji"] == "🚀"
    assert leo["role"] == "learner"
    max = next(pick for pick in picks if pick["label"] == "Max")
    assert max["emoji"] == "🐶"
    assert max["role"] == "learner"


@pytest.mark.asyncio
async def test_login_rate_limited(client, monkeypatch) -> None:
    from app.config import get_settings
    from app.core.rate_limit import limiter

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "ci-test-secret-key-not-for-production-use")
    get_settings.cache_clear()
    limiter.reset()
    try:
        for _ in range(10):
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "parent", "password": "wrong"},
            )
            assert response.status_code == 401
        blocked = await client.post(
            "/api/v1/auth/login",
            json={"username": "parent", "password": "wrong"},
        )
        assert blocked.status_code == 429
    finally:
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        get_settings.cache_clear()
        limiter.reset()


@pytest.mark.asyncio
async def test_me_returns_profile(client) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mia", "password": "mia"},
    )
    token = login.json()["access_token"]
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == "mia"
    assert payload["role"] == "learner"
    assert payload["learner"]["ui_mode"] == "teen"
    assert payload["learner"]["emoji"] == "🌸"
    assert payload["learner"]["english_level"] == "A1"


@pytest.mark.asyncio
async def test_refresh_rotates_token(client) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "leo", "password": "leo"},
    )
    assert login.status_code == 200
    refresh = await client.post("/api/v1/auth/refresh")
    assert refresh.status_code == 200
    assert "access_token" in refresh.json()


@pytest.mark.asyncio
async def test_learner_cannot_access_parent_learners(client) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mia", "password": "mia"},
    )
    token = login.json()["access_token"]
    response = await client.get(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_parent_lists_learners(client) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "parent", "password": "parent123"},
    )
    token = login.json()["access_token"]
    response = await client.get(
        "/api/v1/learners",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    learners = response.json()
    assert len(learners) == 3
    usernames = {learner["username"] for learner in learners}
    assert usernames == {"mia", "leo", "max"}
