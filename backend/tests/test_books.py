import io
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.srs import SrsCard, SrsReviewLog
from app.models.word_list import WordList, WordListItem

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


@pytest.mark.asyncio
async def test_book_preview_and_confirm(client: AsyncClient, db_session) -> None:
    token = await _login(client, "parent", "parent123")
    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    assert preview.status_code == 200
    data = preview.json()
    assert data["status"] == "preview"
    assert data["content_lemma_count"] >= 4
    assert data["study_lemma_count"] >= 1
    assert data["skipped_function_words"] > 0
    assert "80" in data["coverage_curve"]
    book_id = data["id"]

    confirm = await client.post(
        f"/api/v1/books/{book_id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
        json={"coverage_target": 0.8},
    )
    assert confirm.status_code == 200
    confirmed = confirm.json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["word_list_id"] is not None
    assert confirmed["coverage_target"] == 0.8

    word_list = (
        await db_session.execute(select(WordList).where(WordList.id == confirmed["word_list_id"]))
    ).scalar_one()
    assert word_list.source == "book"
    items = (
        (
            await db_session.execute(
                select(WordListItem).where(WordListItem.word_list_id == word_list.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(items) == confirmed["study_lemma_count"]


@pytest.mark.asyncio
async def test_book_mode_new_from_book_retention_from_bank(client: AsyncClient, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    rows = "\n".join(f"bank{i},Meaning {i},A1,General" for i in range(1, 8))
    csv_content = f"word,definition,level,category\n{rows}\n"
    imported = await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert imported.status_code == 200

    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    retention_cards = (
        (
            await db_session.execute(
                select(SrsCard)
                .where(SrsCard.learner_id == learner.id, SrsCard.released_at.is_(None))
                .limit(3)
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)
    for card in retention_cards:
        card.released_at = yesterday
        card.due_at = now - timedelta(hours=1)
        card.state = "review"
        card.interval_days = 5
        card.repetitions = 1
        db_session.add(
            SrsReviewLog(
                srs_card_id=card.id,
                learner_id=learner.id,
                quality=4,
                reviewed_at=yesterday,
            )
        )
    await db_session.commit()
    retention_words = set()
    for card in retention_cards:
        entry = (
            await db_session.execute(
                select(DictionaryEntry).where(DictionaryEntry.id == card.dictionary_entry_id)
            )
        ).scalar_one()
        retention_words.add(entry.word)

    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    assert preview.status_code == 200
    book_id = preview.json()["id"]
    confirm = await client.post(
        f"/api/v1/books/{book_id}/confirm",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"coverage_target": 0.8},
    )
    assert confirm.status_code == 200
    assign = await client.post(
        f"/api/v1/books/{book_id}/assign",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"learner_id": learner.id},
    )
    assert assign.status_code == 200
    assert learner.id in assign.json()["assigned_learner_ids"]

    leo_token = await _login(client, "leo", "leo")
    with (
        patch("app.services.dictionary_service.generate_kid_definition", return_value=None),
        patch(
            "app.services.dictionary_service.fetch_from_api",
            side_effect=Exception("offline"),
        ),
    ):
        mix = await client.get(
            "/api/v1/loop/today",
            headers={"Authorization": f"Bearer {leo_token}"},
        )
    assert mix.status_code == 200
    payload = mix.json()
    assert payload["source_kind"] == "book"
    assert payload["book_title"]
    mix_words = {card["dictionary_entry"]["word"] for card in payload["cards"]}
    book_list_id = confirm.json()["word_list_id"]
    book_entry_ids = set(
        (
            await db_session.execute(
                select(WordListItem.dictionary_entry_id).where(
                    WordListItem.word_list_id == book_list_id
                )
            )
        )
        .scalars()
        .all()
    )
    new_cards = [
        card
        for card in payload["cards"]
        if card["dictionary_entry"]["id"] in book_entry_ids
        and card["dictionary_entry"]["word"] not in retention_words
    ]
    assert payload["new_count"] >= 1
    assert any(card["dictionary_entry"]["id"] in book_entry_ids for card in payload["cards"])
    assert mix_words & retention_words or payload["retention_count"] >= 1
    assert new_cards or payload["new_count"] >= 1

    words = await client.get(
        "/api/v1/loop/words",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert words.status_code == 200
    book_title = confirm.json()["title"]
    assert book_title in words.json()["by_level"]
    assert words.json()["by_level"][book_title] >= 1


@pytest.mark.asyncio
async def test_closing_book_restores_bank_drip(client: AsyncClient, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = "word,definition,level,category\napple,Fruit,A1,Food\nbanana,Fruit,A1,Food\n"
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    book_id = preview.json()["id"]
    await client.post(
        f"/api/v1/books/{book_id}/confirm",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"coverage_target": 0.8},
    )
    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    await client.post(
        f"/api/v1/books/{book_id}/assign",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"learner_id": learner.id},
    )
    closed = await client.delete(
        f"/api/v1/books/{book_id}/assign/{learner.id}",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert closed.status_code == 200
    assert learner.id not in closed.json()["assigned_learner_ids"]

    leo_token = await _login(client, "leo", "leo")
    mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert mix.status_code == 200
    assert mix.json()["source_kind"] != "book"


@pytest.mark.asyncio
async def test_mid_day_unassign_resets_source_kind(client: AsyncClient, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    book_id = preview.json()["id"]
    await client.post(
        f"/api/v1/books/{book_id}/confirm",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"coverage_target": 0.8},
    )
    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    await client.post(
        f"/api/v1/books/{book_id}/assign",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"learner_id": learner.id},
    )
    leo_token = await _login(client, "leo", "leo")
    with patch("app.services.dictionary_service.prefetch_challenge_definitions", return_value=None):
        while_book = await client.get(
            "/api/v1/loop/today",
            headers={"Authorization": f"Bearer {leo_token}"},
        )
    assert while_book.status_code == 200
    assert while_book.json()["source_kind"] == "book"

    await client.delete(
        f"/api/v1/books/{book_id}/assign/{learner.id}",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    after_close = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert after_close.status_code == 200
    assert after_close.json()["source_kind"] != "book"


@pytest.mark.asyncio
async def test_delete_preview_book(client: AsyncClient) -> None:
    token = await _login(client, "parent", "parent123")
    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    book_id = preview.json()["id"]
    deleted = await client.delete(
        f"/api/v1/books/{book_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 204
    missing = await client.get(
        f"/api/v1/books/{book_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_hide_lemma_updates_study_set(client: AsyncClient) -> None:
    token = await _login(client, "parent", "parent123")
    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    book_id = preview.json()["id"]
    detail = await client.get(
        f"/api/v1/books/{book_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    lemma_id = detail.json()["sample_study"][0]["id"]
    before_count = detail.json()["study_lemma_count"]
    hidden = await client.patch(
        f"/api/v1/books/{book_id}/lemmas/{lemma_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"hidden": True},
    )
    assert hidden.status_code == 200
    assert hidden.json()["study_lemma_count"] <= before_count


@pytest.mark.asyncio
async def test_baseline_match_counts_family_bank_only(client: AsyncClient, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    db_session.add(
        DictionaryEntry(
            word="fox",
            definition="A wild canine (not in bank).",
            source="manual",
        )
    )
    await db_session.commit()

    csv_content = "word,definition,level,category\nhill,A small mountain,A1,Nature\n"
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    data = preview.json()
    assert data["baseline_match_count"] == 1
    matched = [row for row in data["sample_study"] if row["matched_baseline"]]
    assert len(matched) == 1
    assert matched[0]["lemma"] == "hill"


@pytest.mark.asyncio
async def test_update_book_title(client: AsyncClient) -> None:
    token = await _login(client, "parent", "parent123")
    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    book_id = preview.json()["id"]
    updated = await client.patch(
        f"/api/v1/books/{book_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "The Fox and the Hill"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "The Fox and the Hill"
    assert updated.json()["title_needs_review"] is False


@pytest.mark.asyncio
async def test_delete_confirmed_book(client: AsyncClient, db_session) -> None:
    token = await _login(client, "parent", "parent123")
    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    book_id = preview.json()["id"]
    await client.post(
        f"/api/v1/books/{book_id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
        json={"coverage_target": 0.8, "title": "Fox Story"},
    )
    deleted = await client.delete(
        f"/api/v1/books/{book_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 204
    missing = await client.get(
        f"/api/v1/books/{book_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_progress_credits_baseline_srs(client: AsyncClient, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = "word,definition,level,category\nfox,A wild animal,A1,Animals\n"
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    fox_entry = (
        await db_session.execute(select(DictionaryEntry).where(DictionaryEntry.word == "fox"))
    ).scalar_one()
    card = (
        await db_session.execute(
            select(SrsCard).where(
                SrsCard.learner_id == learner.id,
                SrsCard.dictionary_entry_id == fox_entry.id,
            )
        )
    ).scalar_one()
    yesterday = datetime.now(UTC) - timedelta(days=1)
    card.released_at = yesterday
    db_session.add(
        SrsReviewLog(
            srs_card_id=card.id,
            learner_id=learner.id,
            quality=4,
            reviewed_at=yesterday,
        )
    )
    await db_session.commit()

    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    book_id = preview.json()["id"]
    await client.post(
        f"/api/v1/books/{book_id}/confirm",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"coverage_target": 0.8},
    )
    await client.post(
        f"/api/v1/books/{book_id}/assign",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"learner_id": learner.id},
    )
    progress = await client.get(
        f"/api/v1/books/{book_id}/progress?learner_id={learner.id}",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert progress.status_code == 200
    row = progress.json()[0]
    assert row["study_known"] >= 1
    assert row["study_progress_percent"] > 0
    assert row["learning_count"] >= 1
    assert row["familiar_count"] >= 0
    assert row["mastered_count"] >= 0


@pytest.mark.asyncio
async def test_learner_words_overlap_shows_bank_level_and_book(
    client: AsyncClient, db_session
) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = "word,definition,level,category\nfox,A wild animal,A1,Animals\n"
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    fox_entry = (
        await db_session.execute(select(DictionaryEntry).where(DictionaryEntry.word == "fox"))
    ).scalar_one()
    card = (
        await db_session.execute(
            select(SrsCard).where(
                SrsCard.learner_id == learner.id,
                SrsCard.dictionary_entry_id == fox_entry.id,
            )
        )
    ).scalar_one()
    card.released_at = datetime.now(UTC)
    db_session.add(
        SrsReviewLog(
            srs_card_id=card.id,
            learner_id=learner.id,
            quality=4,
            reviewed_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    preview = await client.post(
        "/api/v1/books/preview",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("fox.txt", io.BytesIO(FOX_STORY.encode()), "text/plain")},
    )
    book_id = preview.json()["id"]
    confirm = await client.post(
        f"/api/v1/books/{book_id}/confirm",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"coverage_target": 0.8, "title": "Fox Story"},
    )
    book_title = confirm.json()["title"]
    await client.post(
        f"/api/v1/books/{book_id}/assign",
        headers={"Authorization": f"Bearer {parent_token}"},
        json={"learner_id": learner.id},
    )

    leo_token = await _login(client, "leo", "leo")
    words = await client.get(
        "/api/v1/loop/words",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert words.status_code == 200
    payload = words.json()
    fox_row = next(item for item in payload["items"] if item["word"] == "fox")
    assert "A1" in fox_row["levels"]
    assert book_title in fox_row["levels"]
    assert payload["by_bank_level"].get("A1", 0) >= 1
    assert payload["by_book"].get(book_title, 0) >= 1
    assert payload["by_level"].get("A1", 0) >= 1
    assert book_title not in payload["by_level"]

    by_a1 = await client.get(
        "/api/v1/loop/words?level=A1",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert any(item["word"] == "fox" for item in by_a1.json()["items"])

    by_book = await client.get(
        f"/api/v1/loop/words?level={book_title}",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert any(item["word"] == "fox" for item in by_book.json()["items"])
