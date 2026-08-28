import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.definition_fill_job import DefinitionFillJob
from app.models.dictionary import DictionaryEntry
from app.services import word_bank_service


async def _login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _schedule_task(coro):
    asyncio.get_running_loop().create_task(coro)
    return MagicMock()


@pytest.mark.asyncio
async def test_bank_summary_includes_placeholder_count(client: AsyncClient) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = "word,definition,level,category\napple,,A1,Food\nbanana,A yellow fruit,A1,Food\n"
    imported = await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert imported.status_code == 200

    summary = await client.get(
        "/api/v1/word-bank",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["placeholder_count"] >= 1


@pytest.mark.asyncio
async def test_placeholders_only_filter(client: AsyncClient) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = "word,definition,level,category\ncherry,,A1,Food\ndate,An edible fruit,A1,Food\n"
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    items = await client.get(
        "/api/v1/word-bank/items?placeholders_only=true",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert items.status_code == 200
    words = {row["word"] for row in items.json()["items"]}
    assert "cherry" in words
    assert "date" not in words


@pytest.mark.asyncio
async def test_fill_definitions_job_progress(client: AsyncClient, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = "word,definition,level,category\nmango,,A1,Food\n"
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    async def fake_fill(db, entry):
        entry.definition = "A sweet tropical fruit."
        entry.source = "api"

    with (
        patch("app.services.word_bank_service.asyncio.create_task", side_effect=_schedule_task),
        patch(
            "app.services.word_bank_service.fill_placeholder_definition",
            new=AsyncMock(side_effect=fake_fill),
        ),
    ):
        started = await client.post(
            "/api/v1/word-bank/fill-definitions",
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert started.status_code == 200
        job_id = started.json()["id"]
        await word_bank_service.execute_definition_fill_job(db_session, job_id)

    job = (
        await db_session.execute(select(DefinitionFillJob).where(DefinitionFillJob.id == job_id))
    ).scalar_one()
    assert job.status == "completed"
    assert job.filled >= 1

    entry = (
        await db_session.execute(select(DictionaryEntry).where(DictionaryEntry.word == "mango"))
    ).scalar_one()
    assert entry.definition == "A sweet tropical fruit."

    summary = await client.get(
        "/api/v1/word-bank",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert summary.json()["placeholder_count"] == 0


@pytest.mark.asyncio
async def test_fill_definitions_rejects_concurrent_job(client: AsyncClient) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = "word,definition,level,category\npeach,,A1,Food\n"
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    with patch(
        "app.services.word_bank_service.asyncio.create_task",
        side_effect=_schedule_task,
    ):
        first = await client.post(
            "/api/v1/word-bank/fill-definitions",
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert first.status_code == 200
        second = await client.post(
            "/api/v1/word-bank/fill-definitions",
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert second.status_code == 409
