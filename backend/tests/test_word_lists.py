from unittest.mock import AsyncMock, patch

import pytest

from app.models.dictionary import DictionaryEntry


async def _login(client, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _mock_entry(word: str, entry_id: int = 1) -> DictionaryEntry:
    return DictionaryEntry(
        id=entry_id,
        word=word,
        phonetic=None,
        part_of_speech="noun",
        definition=f"Definition of {word}",
        example_sentence=None,
        synonyms=None,
        source="manual",
        source_url=None,
        audio_path=None,
        fetched_at=None,
    )


@pytest.mark.asyncio
async def test_parent_creates_and_lists_word_list(client) -> None:
    token = await _login(client, "parent", "parent123")
    create = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Weekend Words", "description": "Fun list", "level_tag": "A2"},
    )
    assert create.status_code == 201
    payload = create.json()
    assert payload["name"] == "Weekend Words"
    assert payload["item_count"] == 0

    listing = await client.get(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listing.status_code == 200
    names = {item["name"] for item in listing.json()}
    assert "Weekend Words" in names


@pytest.mark.asyncio
async def test_parent_adds_word_to_list(client) -> None:
    token = await _login(client, "parent", "parent123")
    create = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Animals"},
    )
    list_id = create.json()["id"]

    with patch(
        "app.services.word_list_service.dictionary_service.lookup_word",
        new_callable=AsyncMock,
        return_value=_mock_entry("tiger", 10),
    ):
        add = await client.post(
            f"/api/v1/word-lists/{list_id}/items",
            headers={"Authorization": f"Bearer {token}"},
            json={"word": "tiger"},
        )
    assert add.status_code == 201
    assert add.json()["dictionary_entry"]["word"] == "tiger"


@pytest.mark.asyncio
async def test_duplicate_word_returns_409(client) -> None:
    token = await _login(client, "parent", "parent123")
    create = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Colors"},
    )
    list_id = create.json()["id"]
    entry = _mock_entry("blue", 11)

    with patch(
        "app.services.word_list_service.dictionary_service.lookup_word",
        new_callable=AsyncMock,
        return_value=entry,
    ):
        first = await client.post(
            f"/api/v1/word-lists/{list_id}/items",
            headers={"Authorization": f"Bearer {token}"},
            json={"word": "blue"},
        )
        second = await client.post(
            f"/api/v1/word-lists/{list_id}/items",
            headers={"Authorization": f"Bearer {token}"},
            json={"word": "blue"},
        )
    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_assign_list_to_leo_only(client, db_session) -> None:
    from sqlalchemy import select

    from app.models.learner import Learner
    from app.models.user import User

    parent_token = await _login(client, "parent", "parent123")
    leo = (
        await db_session.execute(select(Learner).join(User).where(User.username == "leo"))
    ).scalar_one()

    create = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"name": "Leo's List", "level_tag": "A2"},
    )
    list_id = create.json()["id"]

    assign = await client.post(
        f"/api/v1/word-lists/{list_id}/assign",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"learner_ids": [leo.id]},
    )
    assert assign.status_code == 201

    mia_lists = await client.get(
        "/api/v1/word-lists/assigned",
        headers={"Authorization": f"Bearer {(await _login(client, 'mia', 'mia'))}"},
    )
    leo_lists = await client.get(
        "/api/v1/word-lists/assigned",
        headers={"Authorization": f"Bearer {(await _login(client, 'leo', 'leo'))}"},
    )
    mia_names = {item["name"] for item in mia_lists.json()["lists"]}
    leo_names = {item["name"] for item in leo_lists.json()["lists"]}
    assert "Leo's List" in leo_names
    assert "Leo's List" not in mia_names


@pytest.mark.asyncio
async def test_learner_can_create_word_list(client) -> None:
    token = await _login(client, "mia", "mia")
    response = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "School Week 5"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "School Week 5"
    assert payload["source"] == "learner"

    assigned = await client.get(
        "/api/v1/word-lists/assigned",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert assigned.status_code == 200
    names = {item["name"] for item in assigned.json()["lists"]}
    assert "School Week 5" in names


@pytest.mark.asyncio
async def test_learner_can_add_word_to_own_list(client) -> None:
    token = await _login(client, "mia", "mia")
    create = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "My Spelling"},
    )
    list_id = create.json()["id"]

    with patch(
        "app.services.word_list_service.dictionary_service.lookup_word",
        new_callable=AsyncMock,
        return_value=_mock_entry("privacy", 20),
    ):
        add = await client.post(
            f"/api/v1/word-lists/{list_id}/items",
            headers={"Authorization": f"Bearer {token}"},
            json={"word": "privacy"},
        )
    assert add.status_code == 201
    assert add.json()["dictionary_entry"]["word"] == "privacy"


@pytest.mark.asyncio
async def test_learner_cannot_add_word_to_parent_list(client, db_session) -> None:
    from sqlalchemy import select

    from app.models.learner import Learner
    from app.models.user import User

    parent_token = await _login(client, "parent", "parent123")
    create = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"name": "Parent Only"},
    )
    list_id = create.json()["id"]

    mia = (
        await db_session.execute(select(Learner).join(User).where(User.username == "mia"))
    ).scalar_one()

    assign = await client.post(
        f"/api/v1/word-lists/{list_id}/assign",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"learner_ids": [mia.id]},
    )
    assert assign.status_code == 201

    mia_token = await _login(client, "mia", "mia")
    with patch(
        "app.services.word_list_service.dictionary_service.lookup_word",
        new_callable=AsyncMock,
        return_value=_mock_entry("tiger", 21),
    ):
        add = await client.post(
            f"/api/v1/word-lists/{list_id}/items",
            headers={"Authorization": f"Bearer {mia_token}"},
            json={"word": "tiger"},
        )
    assert add.status_code == 404


@pytest.mark.asyncio
async def test_catalog_lists_curated_by_level(client, db_session) -> None:
    from sqlalchemy import select

    from app.models.user import User
    from app.services import word_list_service

    parent = (await db_session.execute(select(User).where(User.username == "parent"))).scalar_one()
    await word_list_service.create_word_list(
        db_session,
        parent_id=parent.id,
        name="Catalog A2",
        level_tag="A2",
        source="curated",
    )
    await word_list_service.create_word_list(
        db_session,
        parent_id=parent.id,
        name="Catalog B1",
        level_tag="B1",
        source="curated",
    )
    await db_session.commit()

    token = await _login(client, "parent", "parent123")
    response = await client.get(
        "/api/v1/word-lists/catalog",
        params={"level": "A2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    lists = response.json()["lists"]
    assert all(item["source"] == "curated" for item in lists)
    assert all(item["level_tag"] == "A2" for item in lists)
