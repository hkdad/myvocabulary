import asyncio
import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.definition_fill_job import DefinitionFillJob
from app.models.dictionary import DictionaryEntry
from app.services import book_service

FOX_STORY = """
The fox ran to the hill. The fox ran to the hill again.
The rabbit sat on the hill. The rabbit sat and the fox ran.
The carrot sat on the hill. The fox ate the carrot. The rabbit ate the carrot.
The fox ran. The rabbit sat. The carrot sat on the hill.
"""


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


async def _confirm_fox_book(client: AsyncClient, token: str) -> int:
    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    assert preview.status_code == 200
    book_id = preview.json()["id"]
    with patch(
        "app.services.book_service.dictionary_service.prefetch_study_set_definitions",
        new=AsyncMock(),
    ):
        confirm = await client.post(
            f"/api/v1/books/{book_id}/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json={"coverage_target": 0.8},
        )
    assert confirm.status_code == 200
    return book_id


@pytest.mark.asyncio
async def test_books_definitions_summary_counts_placeholders(client: AsyncClient) -> None:
    token = await _login(client, "parent", "parent123")
    await _confirm_fox_book(client, token)

    summary = await client.get(
        "/api/v1/books/definitions-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["needs_refresh_count"] >= 1
    assert payload["missing_en_count"] >= 1


@pytest.mark.asyncio
async def test_book_fill_definitions_job_english_only(client: AsyncClient, db_session) -> None:
    token = await _login(client, "parent", "parent123")
    await _confirm_fox_book(client, token)

    async def fake_fill(db, entry, *, api_only=False):
        assert api_only is True
        entry.definition = "A small wild animal."
        entry.source = "api"

    zh_mock = AsyncMock(return_value="一種小型野生動物")

    with (
        patch("app.services.book_service.asyncio.create_task", side_effect=_schedule_task),
        patch(
            "app.services.book_service.fill_placeholder_definition",
            new=AsyncMock(side_effect=fake_fill),
        ),
        patch(
            "app.services.dictionary_service.translate_definition_to_zh_hant",
            zh_mock,
        ),
    ):
        started = await client.post(
            "/api/v1/books/fill-definitions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert started.status_code == 200
        job_id = started.json()["id"]
        await book_service.execute_book_definition_fill_job(db_session, job_id)

    job = (
        await db_session.execute(select(DefinitionFillJob).where(DefinitionFillJob.id == job_id))
    ).scalar_one()
    assert job.status == "completed"
    assert job.scope == "books"
    assert job.filled >= 1
    zh_mock.assert_not_called()

    entry = (
        await db_session.execute(select(DictionaryEntry).where(DictionaryEntry.word == "fox"))
    ).scalar_one()
    assert entry.definition == "A small wild animal."
    assert not (entry.definition_zh_hant or "").strip()

    summary = await client.get(
        "/api/v1/books/definitions-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert summary.json()["missing_en_count"] == 0


@pytest.mark.asyncio
async def test_book_fill_job_records_failed_words(client: AsyncClient, db_session) -> None:
    token = await _login(client, "parent", "parent123")
    await _confirm_fox_book(client, token)

    async def fake_fill(db, entry, *, api_only=False):
        if entry.word == "fox":
            entry.definition = "A small wild animal."
            entry.source = "api"

    with (
        patch("app.services.book_service.asyncio.create_task", side_effect=_schedule_task),
        patch(
            "app.services.book_service.fill_placeholder_definition",
            new=AsyncMock(side_effect=fake_fill),
        ),
    ):
        started = await client.post(
            "/api/v1/books/fill-definitions",
            headers={"Authorization": f"Bearer {token}"},
        )
        job_id = started.json()["id"]
        await book_service.execute_book_definition_fill_job(db_session, job_id)

    job = (
        await db_session.execute(select(DefinitionFillJob).where(DefinitionFillJob.id == job_id))
    ).scalar_one()
    assert job.failed >= 1
    assert job.failed_words_json
    failures = json.loads(job.failed_words_json)
    assert any(row["word"] != "fox" for row in failures)

    listed = await client.get(
        f"/api/v1/books/placeholder-lemmas?job_id={job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) >= 1
    assert all(item["lemma"] != "fox" for item in items)
