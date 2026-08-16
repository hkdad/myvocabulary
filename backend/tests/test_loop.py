import io
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.sm2 import DEFAULT_EASE_FACTOR
from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.srs import SrsCard, SrsReviewLog
from app.services import loop_engine


async def _login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


async def _due_card_with_strength(
    db_session,
    *,
    learner_id: int,
    entry_id: int,
    word_list_id: int | None,
    now: datetime,
    distinct_days: int,
) -> SrsCard:
    """Released, due card with N distinct correct review days (sets last_reviewed_at)."""
    result = await db_session.execute(
        select(SrsCard).where(
            SrsCard.learner_id == learner_id,
            SrsCard.dictionary_entry_id == entry_id,
        )
    )
    card = result.scalar_one_or_none()
    if card is None:
        card = SrsCard(
            learner_id=learner_id,
            dictionary_entry_id=entry_id,
            word_list_id=word_list_id,
            ease_factor=DEFAULT_EASE_FACTOR,
            interval_days=10,
            repetitions=distinct_days,
            due_at=now - timedelta(hours=1),
            state="review",
            released_at=now - timedelta(days=10),
            last_reviewed_at=now - timedelta(hours=2),
        )
        db_session.add(card)
        await db_session.flush()
    else:
        card.word_list_id = word_list_id or card.word_list_id
        card.ease_factor = DEFAULT_EASE_FACTOR
        card.interval_days = 10
        card.repetitions = distinct_days
        card.due_at = now - timedelta(hours=1)
        card.state = "review"
        card.released_at = now - timedelta(days=10)
        card.last_reviewed_at = now - timedelta(hours=2)

    for day_offset in range(distinct_days, 0, -1):
        db_session.add(
            SrsReviewLog(
                srs_card_id=card.id,
                learner_id=learner_id,
                quality=4,
                reviewed_at=now - timedelta(days=day_offset),
            )
        )
    return card


async def _complete_listen_and_pick(client: AsyncClient, token: str) -> None:
    """Finish today's Listen & Pick session (choice mode) for daily challenge tests."""
    started = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"source": "daily_challenge", "mode": "choice", "max_words": 30},
    )
    assert started.status_code in (200, 201)
    session_id = started.json()["id"]
    total_words = started.json()["total_words"]
    for _ in range(total_words * 4):
        prompt = await client.get(
            f"/api/v1/dictation/sessions/{session_id}/next",
            headers={"Authorization": f"Bearer {token}"},
        )
        if prompt.status_code != 200:
            break
        data = prompt.json()
        if data.get("session_complete"):
            break
        for choice in data.get("choices", []):
            answer = await client.post(
                f"/api/v1/dictation/sessions/{session_id}/answer",
                headers={"Authorization": f"Bearer {token}"},
                json={"answer": choice, "hint_used": False},
            )
            if answer.status_code != 200:
                continue
            if answer.json().get("session_complete"):
                return
            if answer.json().get("is_correct"):
                break


@pytest.mark.parametrize(
    ("distinct_days", "expected"),
    [
        (0, "learning"),
        (1, "learning"),
        (2, "familiar"),
        (3, "mastered"),
        (4, "mastered"),
        (5, "mastered"),
        (6, "mastered"),
    ],
)
def test_derive_strength(distinct_days: int, expected: str) -> None:
    assert loop_engine.derive_strength(distinct_review_days=distinct_days) == expected


@pytest.mark.asyncio
async def test_import_rejects_missing_level_column(client: AsyncClient, db_session) -> None:
    token = await _login(client, "parent", "parent123")
    csv_content = "word,definition,category\napple,Fruit,Food\n"
    response = await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 400
    assert "level" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_skips_blank_level(client: AsyncClient, db_session) -> None:
    token = await _login(client, "parent", "parent123")
    csv_content = "word,definition,level,category\napple,Fruit,,Food\nbanana,Fruit,A2,Food\n"
    response = await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == 1
    assert data["skipped"] == 1
    assert data["needs_level_count"] == 1

    items = await client.get(
        "/api/v1/word-bank/items",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert items.json()["total"] == 1
    assert items.json()["items"][0]["word"] == "banana"
    assert items.json()["items"][0]["level"] == "A2"


@pytest.mark.asyncio
async def test_import_stores_submitted_levels_and_categories(
    client: AsyncClient, db_session
) -> None:
    token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\ntiger,Big cat,Grade 3,animals\nparis,City,Book 1,travel\n"
    )
    response = await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 200

    items = await client.get(
        "/api/v1/word-bank/items",
        headers={"Authorization": f"Bearer {token}"},
    )
    by_word = {item["word"]: item for item in items.json()["items"]}
    assert by_word["tiger"]["level"] == "Grade 3"
    assert by_word["tiger"]["categories"] == ["Animals"]
    assert by_word["paris"]["level"] == "Book 1"
    assert by_word["paris"]["categories"] == ["Travel"]


@pytest.mark.asyncio
async def test_import_categories_column_splits_on_and(client: AsyncClient, db_session) -> None:
    token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,categories\n"
        "apple,A round fruit,A1,Food and Animals\n"
        "banana,Yellow fruit,A1,Food\n"
    )
    response = await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 200

    summary = await client.get(
        "/api/v1/word-bank",
        headers={"Authorization": f"Bearer {token}"},
    )
    by_category = summary.json()["by_category"]
    assert by_category["Food"] == 2
    assert by_category["Animals"] == 1

    animals_only = await client.get(
        "/api/v1/word-bank/items?category=Animals",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert animals_only.status_code == 200
    assert animals_only.json()["total"] == 1
    assert animals_only.json()["items"][0]["word"] == "apple"
    assert animals_only.json()["items"][0]["categories"] == ["Food", "Animals"]


@pytest.mark.asyncio
async def test_import_family_bank(client: AsyncClient, db_session) -> None:
    token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        "apple,A round fruit,A1,Food\n"
        "banana,Yellow fruit,A1,Food\n"
        "science,Study of nature,B1,Science\n"
    )
    response = await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == 3
    assert data["total_items"] == 3

    summary = await client.get(
        "/api/v1/word-bank",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert summary.status_code == 200
    assert summary.json()["total_items"] == 3


@pytest.mark.asyncio
async def test_daily_mix_caps_new_words(client: AsyncClient, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    words = [f"word{i}" for i in range(12)]
    rows = "\n".join(f"{word},Definition for {word},A1,General" for word in words)
    csv_content = f"word,definition,level,category\n{rows}\n"
    import_response = await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert import_response.status_code == 200

    leo_token = await _login(client, "leo", "leo")
    mix_response = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert mix_response.status_code == 200
    mix = mix_response.json()
    assert mix["daily_new_goal"] == 5
    assert mix["daily_learning_retention_goal"] == 1
    assert mix["daily_mastered_retention_goal"] == 1
    assert mix["daily_retention_goal"] == 2
    assert mix["new_count"] == 5
    assert mix["retention_count"] == 2
    assert mix["new_count"] + mix["retention_count"] == 7
    assert len(mix["cards"]) == 7

    progress = await client.get(
        "/api/v1/loop/progress",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert progress.status_code == 200
    # Drip releases up to new + retention so the challenge can always fill 5+2.
    assert progress.json()["new_released_today"] <= 7


@pytest.mark.asyncio
async def test_daily_mix_picks_random_not_import_order(client: AsyncClient, db_session) -> None:
    from sqlalchemy import select

    from app.models.learner import Learner

    parent_token = await _login(client, "parent", "parent123")
    # CSV row order is alphabetical; drip should not always take the first rows.
    csv_content = (
        "word,definition,level,category\n"
        "apple,Fruit,A1,General\n"
        "banana,Fruit,A1,General\n"
        "cherry,Fruit,A1,General\n"
        "date,Fruit,A1,General\n"
        "elderberry,Fruit,A1,General\n"
        "fig,Fruit,A1,General\n"
        "grape,Fruit,A1,General\n"
        "honeydew,Fruit,A1,General\n"
        "iceberg,Fruit,A1,General\n"
        "jackfruit,Fruit,A1,General\n"
    )
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    leo = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    leo.english_level = "A1"
    await db_session.commit()

    leo_token = await _login(client, "leo", "leo")
    mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert mix.status_code == 200
    payload = mix.json()
    words = [card["dictionary_entry"]["word"] for card in payload["cards"]]
    assert words
    # Drip should not always take CSV import order, and review order is shuffled.
    assert (
        words != ["apple", "banana", "cherry", "date", "elderberry", "fig", "grape"][: len(words)]
    )


@pytest.mark.asyncio
async def test_bank_import_does_not_flood_due_queue(client: AsyncClient, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    rows = "\n".join(f"term{i},Meaning {i},A1,General" for i in range(20))
    csv_content = f"word,definition,level,category\n{rows}\n"
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    leo_token = await _login(client, "leo", "leo")
    stats = await client.get(
        "/api/v1/dashboard/me",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert stats.status_code == 200
    assert stats.json()["due_count"] < 20


@pytest.mark.asyncio
async def test_a1_learner_does_not_get_b1_words(client: AsyncClient, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\neasy,Easy word,A1,General\nhard,Hard word,B1,General\n"
    )
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    leo_token = await _login(client, "leo", "leo")
    mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    words = [card["dictionary_entry"]["word"] for card in mix.json()["cards"]]
    assert "hard" not in words


@pytest.mark.asyncio
async def test_different_learner_levels_get_different_new_words(
    client: AsyncClient, db_session
) -> None:
    from sqlalchemy import select

    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        "alpha,First A2 word,A2,General\n"
        "beta,Second A2 word,A2,General\n"
        "gamma,First B1 word,B1,General\n"
        "delta,Second B1 word,B1,General\n"
    )
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    mia = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Mia"))
    ).scalar_one()
    leo = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    mia.english_level = "B1"
    leo.english_level = "A2"
    await db_session.commit()

    mia_token = await _login(client, "mia", "mia")
    leo_token = await _login(client, "leo", "leo")

    mia_mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {mia_token}"},
    )
    leo_mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    mia_words = {card["dictionary_entry"]["word"] for card in mia_mix.json()["cards"]}
    leo_words = {card["dictionary_entry"]["word"] for card in leo_mix.json()["cards"]}

    bank_words = {"alpha", "beta", "gamma", "delta"}
    mia_bank_words = mia_words & bank_words
    leo_bank_words = leo_words & bank_words

    assert mia_bank_words <= {"gamma", "delta"}
    assert leo_bank_words <= {"alpha", "beta"}
    assert mia_bank_words.isdisjoint(leo_bank_words)


@pytest.mark.asyncio
async def test_complete_daily_challenge_requires_phases(client: AsyncClient, db_session) -> None:
    leo_token = await _login(client, "leo", "leo")
    soft = await client.post(
        "/api/v1/loop/today/complete",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert soft.status_code == 400

    progress = await client.get(
        "/api/v1/loop/progress",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert progress.json()["daily_challenge_completed"] is False


@pytest.mark.asyncio
async def test_daily_challenge_completes_after_srs_recognition(
    client: AsyncClient, db_session
) -> None:
    """SRS recognition then Listen & Pick both required to complete the day."""
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        "apple,A round fruit,A2,Food\n"
        "banana,Yellow fruit,A2,Food\n"
        "cat,A small animal,A2,Animals\n"
        "dog,A loyal pet,A2,Animals\n"
        "easy,Easy word,A2,General\n"
    )
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    leo_token = await _login(client, "leo", "leo")
    mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert mix.status_code == 200
    cards = mix.json()["cards"]
    assert len(cards) > 0

    for card in cards:
        answer = await client.post(
            f"/api/v1/reviews/{card['id']}/answer",
            headers={"Authorization": f"Bearer {leo_token}"},
            json={"quality": 4},
        )
        assert answer.status_code == 200

    srs_done = await client.post(
        "/api/v1/loop/today/srs-complete",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert srs_done.status_code == 200
    assert srs_done.json()["srs_completed"] is True
    assert srs_done.json()["completed"] is False

    progress = await client.get(
        "/api/v1/loop/progress",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert progress.json()["daily_challenge_completed"] is False
    assert progress.json()["daily_challenge_srs_completed"] is True
    assert progress.json()["daily_challenge_dictation_completed"] is False

    dictation = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"source": "daily_challenge", "mode": "choice", "max_words": 30},
    )
    assert dictation.status_code in (200, 201)

    await _complete_listen_and_pick(client, leo_token)

    progress_after = await client.get(
        "/api/v1/loop/progress",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert progress_after.json()["daily_challenge_completed"] is True
    assert progress_after.json()["daily_challenge_dictation_completed"] is True

    # Soft complete endpoint stays idempotent.
    complete = await client.post(
        "/api/v1/loop/today/complete",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert complete.status_code == 200
    assert complete.json()["completed"] is True

    # Isolation: Mia is not marked complete.
    mia_token = await _login(client, "mia", "mia")
    mia_progress = await client.get(
        "/api/v1/loop/progress",
        headers={"Authorization": f"Bearer {mia_token}"},
    )
    assert mia_progress.json()["daily_challenge_completed"] is False


@pytest.mark.asyncio
async def test_daily_challenge_requires_80_percent_correct(client: AsyncClient, db_session) -> None:
    """Soft Daily Challenge does not complete below 80% correct; day is not counted."""
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        + "\n".join(f"word{i},Definition {i},A1,General" for i in range(12))
        + "\n"
    )
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    leo_token = await _login(client, "leo", "leo")
    mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    cards = mix.json()["cards"]
    assert len(cards) >= 5

    # Review all cards but keep accuracy at ~60% — below 80%.
    correct_target = max(1, int(len(cards) * 0.6))
    for index, card in enumerate(cards):
        quality = 4 if index < correct_target else 1
        answer = await client.post(
            f"/api/v1/reviews/{card['id']}/answer",
            headers={"Authorization": f"Bearer {leo_token}"},
            json={"quality": quality},
        )
        assert answer.status_code == 200

    fail = await client.post(
        "/api/v1/loop/today/srs-complete",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert fail.status_code == 400
    detail = fail.json()["detail"]
    assert detail["code"] == "SRS_ACCURACY_BELOW"

    progress = await client.get(
        "/api/v1/loop/progress",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert progress.json()["daily_challenge_completed"] is False

    # Correct the remaining cards so accuracy reaches ≥80%, then complete.
    for card in cards[correct_target:]:
        answer = await client.post(
            f"/api/v1/reviews/{card['id']}/answer",
            headers={"Authorization": f"Bearer {leo_token}"},
            json={"quality": 4},
        )
        assert answer.status_code == 200

    success = await client.post(
        "/api/v1/loop/today/srs-complete",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert success.status_code == 200
    assert success.json()["srs_completed"] is True
    assert success.json()["completed"] is False

    await _complete_listen_and_pick(client, leo_token)

    progress_after = await client.get(
        "/api/v1/loop/progress",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert progress_after.json()["daily_challenge_completed"] is True


@pytest.mark.asyncio
async def test_daily_challenge_uses_latest_review_quality(client: AsyncClient, db_session) -> None:
    """Earlier correct + later wrong on the same card must not count as a pass."""
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        + "\n".join(f"late{i},Definition {i},A1,General" for i in range(12))
        + "\n"
    )
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    leo_token = await _login(client, "leo", "leo")
    mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    cards = mix.json()["cards"]
    assert len(cards) >= 5

    # First pass: all correct (would be 100% under "any correct today").
    for card in cards:
        answer = await client.post(
            f"/api/v1/reviews/{card['id']}/answer",
            headers={"Authorization": f"Bearer {leo_token}"},
            json={"quality": 4},
        )
        assert answer.status_code == 200

    # Second pass: all wrong — latest quality is fail for every card.
    for card in cards:
        answer = await client.post(
            f"/api/v1/reviews/{card['id']}/answer",
            headers={"Authorization": f"Bearer {leo_token}"},
            json={"quality": 1},
        )
        assert answer.status_code == 200

    fail = await client.post(
        "/api/v1/loop/today/srs-complete",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert fail.status_code == 400
    assert fail.json()["detail"]["code"] == "SRS_ACCURACY_BELOW"

    progress = await client.get(
        "/api/v1/loop/progress",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert progress.json()["daily_challenge_completed"] is False


@pytest.mark.asyncio
async def test_distinct_review_days_count_correct_only(db_session) -> None:
    """Wrong-only days do not advance Learning/Familiar; correct days do."""
    from sqlalchemy import select

    from app.models.srs import SrsReviewLog

    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    entry = DictionaryEntry(word="strength_gate", definition="test", source="manual")
    db_session.add(entry)
    await db_session.flush()

    now = datetime.now(UTC)
    card = SrsCard(
        learner_id=learner.id,
        dictionary_entry_id=entry.id,
        ease_factor=DEFAULT_EASE_FACTOR,
        interval_days=1,
        repetitions=1,
        due_at=now + timedelta(days=1),
        state="review",
        released_at=now - timedelta(days=5),
    )
    db_session.add(card)
    await db_session.flush()

    # Three wrong-only days — must not count toward strength.
    for day_offset in (4, 3, 2):
        db_session.add(
            SrsReviewLog(
                srs_card_id=card.id,
                learner_id=learner.id,
                quality=1,
                reviewed_at=now - timedelta(days=day_offset),
            )
        )
    await db_session.commit()

    days_map = await loop_engine.distinct_review_days_by_card(db_session, [card.id])
    assert days_map.get(card.id, 0) == 0

    # Two days with at least one correct review → Familiar.
    for day_offset in (1, 0):
        db_session.add(
            SrsReviewLog(
                srs_card_id=card.id,
                learner_id=learner.id,
                quality=4,
                reviewed_at=now - timedelta(days=day_offset, hours=1),
            )
        )
        # Wrong on the same day still leaves the day counted once.
        db_session.add(
            SrsReviewLog(
                srs_card_id=card.id,
                learner_id=learner.id,
                quality=1,
                reviewed_at=now - timedelta(days=day_offset, minutes=30),
            )
        )
    await db_session.commit()

    days_map = await loop_engine.distinct_review_days_by_card(db_session, [card.id])
    assert days_map[card.id] == 2
    assert loop_engine.derive_strength(distinct_review_days=days_map[card.id]) == "familiar"


@pytest.mark.asyncio
async def test_deck_frozen_after_srs_completion(client: AsyncClient, db_session) -> None:
    """Bonus dictation after re-entering the page must use the reviewed deck."""
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        + "\n".join(f"word{i},Definition {i},A1,General" for i in range(12))
        + "\n"
    )
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    leo_token = await _login(client, "leo", "leo")
    mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    original_ids = [card["id"] for card in mix.json()["cards"]]
    original_words = {card["dictionary_entry"]["word"] for card in mix.json()["cards"]}
    assert original_ids

    for card_id in original_ids:
        await client.post(
            f"/api/v1/reviews/{card_id}/answer",
            headers={"Authorization": f"Bearer {leo_token}"},
            json={"quality": 4},
        )
    srs_done = await client.post(
        "/api/v1/loop/today/srs-complete",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert srs_done.json()["completed"] is False

    # Re-entering the page (GET /loop/today) must not reshuffle the deck.
    again = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert again.json()["completed_today"] is False
    assert again.json()["srs_completed"] is True
    assert [card["id"] for card in again.json()["cards"]] == original_ids

    await _complete_listen_and_pick(client, leo_token)

    completed = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert completed.json()["completed_today"] is True

    # Bonus typed dictation must dictate exactly the reviewed words.
    dictation = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"source": "daily_challenge", "mode": "typed", "max_words": 30},
    )
    assert dictation.status_code in (200, 201)
    assert dictation.json()["total_words"] == len(original_ids)
    session_id = dictation.json()["id"]
    dictated_words = set()
    for _ in range(len(original_ids)):
        give_up = await client.post(
            f"/api/v1/dictation/sessions/{session_id}/give-up",
            headers={"Authorization": f"Bearer {leo_token}"},
        )
        assert give_up.status_code == 200
        if give_up.json().get("expected_word"):
            dictated_words.add(give_up.json()["expected_word"])
        if give_up.json()["session_complete"]:
            break
    assert dictated_words <= original_words


@pytest.mark.asyncio
async def test_progress_summary_counts(db_session) -> None:
    from sqlalchemy import select

    from app.models.srs import SrsReviewLog
    from app.models.word_list import WordList, WordListItem, WordListItemCategory

    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    bank = WordList(parent_id=1, name="Bank", source="bank", is_active=True)
    db_session.add(bank)
    await db_session.flush()

    entry = DictionaryEntry(word="familiar", definition="test", source="manual")
    db_session.add(entry)
    await db_session.flush()
    item = WordListItem(
        word_list_id=bank.id,
        dictionary_entry_id=entry.id,
        sort_order=0,
        level="A1",
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(WordListItemCategory(word_list_item_id=item.id, category="General"))

    now = datetime.now(UTC)
    card = SrsCard(
        learner_id=learner.id,
        dictionary_entry_id=entry.id,
        word_list_id=bank.id,
        ease_factor=DEFAULT_EASE_FACTOR,
        interval_days=30,
        repetitions=3,
        due_at=now + timedelta(days=10),
        state="review",
        released_at=now - timedelta(days=5),
    )
    db_session.add(card)
    await db_session.flush()
    for day_offset in (2, 1):
        db_session.add(
            SrsReviewLog(
                srs_card_id=card.id,
                learner_id=learner.id,
                quality=4,
                reviewed_at=now - timedelta(days=day_offset),
            )
        )
    await db_session.commit()

    summary = await loop_engine.progress_summary(db_session, learner_id=learner.id, now=now)
    level_counts = await loop_engine.strength_counts_for_level(
        db_session,
        learner_id=learner.id,
        parent_id=1,
        level=learner.english_level,
    )
    assert summary["familiar_count"] == level_counts["familiar"]
    assert summary["familiar_count"] >= 1


@pytest.mark.asyncio
async def test_daily_mix_mastered_is_current_level_only(client: AsyncClient, db_session) -> None:
    """Mastered slot is current CEFR; learning/familiar may be any released level."""
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        "a1mastered,A1 mastered,A1,General\n"
        "a1familiar,A1 familiar,A1,General\n"
        "a2mastered,A2 mastered,A2,General\n"
        "b1familiar,B1 familiar,B1,General\n"
        + "".join(f"a2new{i},A2 new {i},A2,General\n" for i in range(1, 9))
    )
    imported = await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert imported.status_code == 200

    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    learner.english_level = "A2"
    await db_session.commit()

    parent_id = await loop_engine.get_learner_parent_id(db_session, learner)
    assert parent_id is not None
    bank = await loop_engine.get_family_bank(db_session, parent_id)
    assert bank is not None

    entries = {
        entry.word: entry
        for entry in (
            await db_session.execute(
                select(DictionaryEntry).where(
                    DictionaryEntry.word.in_(
                        ["a1mastered", "a1familiar", "a2mastered", "b1familiar"]
                    )
                )
            )
        )
        .scalars()
        .all()
    }
    now = datetime.now(UTC)
    a1_mastered = await _due_card_with_strength(
        db_session,
        learner_id=learner.id,
        entry_id=entries["a1mastered"].id,
        word_list_id=bank.id,
        now=now,
        distinct_days=3,
    )
    a2_mastered = await _due_card_with_strength(
        db_session,
        learner_id=learner.id,
        entry_id=entries["a2mastered"].id,
        word_list_id=bank.id,
        now=now,
        distinct_days=3,
    )
    a1_familiar = await _due_card_with_strength(
        db_session,
        learner_id=learner.id,
        entry_id=entries["a1familiar"].id,
        word_list_id=bank.id,
        now=now,
        distinct_days=2,
    )
    b1_familiar = await _due_card_with_strength(
        db_session,
        learner_id=learner.id,
        entry_id=entries["b1familiar"].id,
        word_list_id=bank.id,
        now=now,
        distinct_days=2,
    )
    await db_session.commit()

    current_level_ids = await loop_engine._entry_ids_at_learner_level(
        db_session, learner=learner, parent_id=parent_id
    )
    mastered_cards = await loop_engine.pick_retention(
        db_session,
        learner=learner,
        limit=1,
        now=now,
        entry_id_allowlist=current_level_ids,
        strength_in={"mastered"},
    )
    assert [card.id for card in mastered_cards] == [a2_mastered.id]

    learning_cards = await loop_engine.pick_retention(
        db_session,
        learner=learner,
        limit=1,
        now=now,
        strength_in={"learning", "familiar"},
    )
    assert len(learning_cards) == 1
    assert learning_cards[0].id in {a1_familiar.id, b1_familiar.id}

    mix = await loop_engine.build_daily_mix(
        db_session, learner=learner, parent_id=parent_id, now=now
    )
    mix_ids = {card["id"] for card in mix["cards"]}
    assert a2_mastered.id in mix_ids
    assert a1_mastered.id not in mix_ids
    assert mix_ids & {a1_familiar.id, b1_familiar.id}


@pytest.mark.asyncio
async def test_daily_challenge_mix_is_new_goal_plus_retention(
    client: AsyncClient, db_session
) -> None:
    from sqlalchemy import select

    from app.models.srs import SrsCard

    parent_token = await _login(client, "parent", "parent123")
    rows = ["word,definition,level,category\n"]
    for index in range(1, 13):
        rows.append(f"term{index},Meaning {index},A1,General\n")
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO("".join(rows).encode()), "text/csv")},
    )

    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    # Turn 3 already-seeded bank placeholders into due retention cards from yesterday.
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
    assert len(retention_cards) >= 3
    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)
    for card in retention_cards:
        card.released_at = yesterday
        card.due_at = now - timedelta(hours=1)
        card.state = "review"
        card.interval_days = 5
        card.repetitions = 1
    await db_session.commit()

    leo_token = await _login(client, "leo", "leo")
    mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert mix.status_code == 200
    payload = mix.json()
    assert payload["daily_new_goal"] == 5
    assert payload["daily_learning_retention_goal"] == 1
    assert payload["daily_mastered_retention_goal"] == 1
    assert payload["daily_retention_goal"] == 2
    assert payload["new_count"] == 5
    assert payload["retention_count"] == 2
    assert len(payload["cards"]) == 7

    # After SRS completion the deck is frozen but keeps full size and counts.
    for card in payload["cards"]:
        await client.post(
            f"/api/v1/reviews/{card['id']}/answer",
            headers={"Authorization": f"Bearer {leo_token}"},
            json={"quality": 4},
        )
    await client.post(
        "/api/v1/loop/today/srs-complete",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    again = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert again.status_code == 200
    assert again.json()["completed_today"] is False
    assert again.json()["srs_completed"] is True
    assert len(again.json()["cards"]) == 7
    assert again.json()["new_count"] == 5
    assert again.json()["retention_count"] == 2

    await _complete_listen_and_pick(client, leo_token)

    done = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert done.json()["completed_today"] is True


@pytest.mark.asyncio
async def test_daily_challenge_due_and_dictation_sources(client: AsyncClient, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        "apple,A round fruit,A2,Food\n"
        "banana,Yellow fruit,A2,Food\n"
        "cat,A small animal,A2,Animals\n"
        "dog,A loyal pet,A2,Animals\n"
        "easy,Easy word,A2,General\n"
    )
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    leo_token = await _login(client, "leo", "leo")
    mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    mix_ids = {card["id"] for card in mix.json()["cards"]}
    assert mix_ids

    due = await client.get(
        "/api/v1/reviews/due?daily_challenge=1",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert due.status_code == 200
    assert {card["id"] for card in due.json()["cards"]} == mix_ids

    dictation = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"source": "daily_challenge", "mode": "typed", "max_words": 30},
    )
    assert dictation.status_code in (200, 201)
    assert dictation.json()["source"] == "daily_challenge"
    assert dictation.json()["total_words"] == len(mix_ids)


@pytest.mark.asyncio
async def test_list_learner_words_filters_and_facets(client: AsyncClient, db_session) -> None:
    from sqlalchemy import select

    from app.models.srs import SrsReviewLog

    parent_token = await _login(client, "parent", "parent123")
    rows = ["word,definition,level,category\n"]
    for index in range(1, 9):
        category = "Food" if index <= 4 else "Science"
        level = "A1" if index <= 5 else "A2"
        rows.append(f"term{index},Meaning {index},{level},{category}\n")
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO("".join(rows).encode()), "text/csv")},
    )

    leo_token = await _login(client, "leo", "leo")
    mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert mix.status_code == 200
    assert len(mix.json()["cards"]) >= 5

    words = await client.get(
        "/api/v1/loop/words",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert words.status_code == 200
    payload = words.json()
    assert payload["total"] >= 5
    assert payload["by_strength"]["new"] + payload["by_strength"]["learning"] >= 1
    assert "by_level" in payload
    assert "by_category" in payload

    search = await client.get(
        "/api/v1/loop/words?q=term1",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert search.status_code == 200
    assert search.json()["total"] >= 1
    assert all("term1" in item["word"] for item in search.json()["items"])

    food = await client.get(
        "/api/v1/loop/words?category=Food",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert food.status_code == 200
    assert food.json()["total"] >= 1
    assert all("Food" in item["categories"] for item in food.json()["items"])

    learner = (
        await db_session.execute(select(Learner).where(Learner.display_name == "Leo"))
    ).scalar_one()
    card = (
        (
            await db_session.execute(
                select(SrsCard).where(
                    SrsCard.learner_id == learner.id, SrsCard.released_at.is_not(None)
                )
            )
        )
        .scalars()
        .first()
    )
    assert card is not None
    card.state = "review"
    card.interval_days = 21
    card.repetitions = 3
    now = datetime.now(UTC)
    for day_offset in (2, 1):
        db_session.add(
            SrsReviewLog(
                srs_card_id=card.id,
                learner_id=learner.id,
                quality=4,
                ease_factor_before=DEFAULT_EASE_FACTOR,
                ease_factor_after=DEFAULT_EASE_FACTOR,
                interval_before=1,
                interval_after=21,
                reviewed_at=now - timedelta(days=day_offset),
            )
        )
    await db_session.commit()

    familiar = await client.get(
        "/api/v1/loop/words?strength=familiar",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert familiar.status_code == 200
    assert familiar.json()["total"] >= 1
    assert all(item["strength"] == "familiar" for item in familiar.json()["items"])
    familiar_item = next(item for item in familiar.json()["items"] if item["card_id"] == card.id)
    assert familiar_item["distinct_review_days"] == 2
    assert familiar_item["repetitions"] == 3
    assert familiar_item["interval_days"] == 21

    page = await client.get(
        "/api/v1/loop/words?page=1&page_size=2",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert page.status_code == 200
    assert len(page.json()["items"]) <= 2
    assert page.json()["page_size"] == 2


@pytest.mark.asyncio
async def test_list_bank_items_paginated_and_filtered(client, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        "apple,A round fruit,A1,Food\n"
        "banana,Yellow fruit,A1,Food\n"
        "science,Study,A2,Science\n"
    )
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    all_items = await client.get(
        "/api/v1/word-bank/items?page=1&page_size=2",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert all_items.status_code == 200
    payload = all_items.json()
    assert payload["total"] == 3
    assert len(payload["items"]) == 2

    food_only = await client.get(
        "/api/v1/word-bank/items?category=Food",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert food_only.status_code == 200
    assert food_only.json()["total"] == 2
    assert all("Food" in item["categories"] for item in food_only.json()["items"])


@pytest.mark.asyncio
async def test_delete_family_bank(client: AsyncClient, db_session) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\napple,A round fruit,A1,Food\nbanana,Yellow fruit,A1,Food\n"
    )
    import_response = await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert import_response.status_code == 200

    delete_response = await client.delete(
        "/api/v1/word-bank",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert delete_response.status_code == 200
    data = delete_response.json()
    assert data["deleted_items"] == 2

    summary = await client.get(
        "/api/v1/word-bank",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert summary.status_code == 200
    assert summary.json()["total_items"] == 0

    missing = await client.delete(
        "/api/v1/word-bank",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_challenge_options_and_regenerate_category(client: AsyncClient) -> None:
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        + "\n".join(f"food{i},Food word {i},A1,Food" for i in range(8))
        + "\n"
        + "\n".join(f"animal{i},Animal word {i},A1,Animals" for i in range(8))
        + "\n"
    )
    imported = await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert imported.status_code == 200

    leo_token = await _login(client, "leo", "leo")
    options = await client.get(
        "/api/v1/loop/today/options",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert options.status_code == 200
    payload = options.json()
    assert payload["can_regenerate"] is True
    names = {item["name"] for item in payload["categories"]}
    assert "Food" in names
    assert "Animals" in names

    await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    regen = await client.post(
        "/api/v1/loop/today/regenerate",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"mode": "category", "category": "Animals"},
    )
    assert regen.status_code == 200
    mix = regen.json()
    assert mix["can_regenerate"] is True
    assert mix["source_kind"] == "category"
    assert mix["source_ref"] == "Animals"
    assert len(mix["cards"]) > 0
    words = {card["dictionary_entry"]["word"] for card in mix["cards"]}
    assert all(word.startswith("animal") for word in words)


@pytest.mark.asyncio
async def test_regenerate_own_list(client: AsyncClient, db_session) -> None:
    from unittest.mock import AsyncMock, patch

    leo_token = await _login(client, "leo", "leo")
    created = await client.post(
        "/api/v1/word-lists",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"name": "My Challenge List"},
    )
    assert created.status_code == 201
    list_id = created.json()["id"]

    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf"]
    for word in words:
        entry = DictionaryEntry(
            word=word,
            phonetic=None,
            part_of_speech="noun",
            definition=f"Definition of {word}",
            source="manual",
        )
        db_session.add(entry)
        await db_session.flush()
        with patch(
            "app.services.word_list_service.dictionary_service.lookup_word",
            new_callable=AsyncMock,
            return_value=entry,
        ):
            add = await client.post(
                f"/api/v1/word-lists/{list_id}/items",
                headers={"Authorization": f"Bearer {leo_token}"},
                json={"word": word},
            )
        assert add.status_code == 201

    options = await client.get(
        "/api/v1/loop/today/options",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert options.status_code == 200
    assert any(item["id"] == list_id for item in options.json()["my_lists"])

    regen = await client.post(
        "/api/v1/loop/today/regenerate",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"mode": "list", "word_list_id": list_id},
    )
    assert regen.status_code == 200
    mix = regen.json()
    assert mix["source_kind"] == "list"
    assert mix["source_ref"] == str(list_id)
    assert len(mix["cards"]) > 0
    mix_words = {card["dictionary_entry"]["word"] for card in mix["cards"]}
    assert mix_words.issubset(set(words))


@pytest.mark.asyncio
async def test_regenerate_resets_mid_session_and_blocks_after_srs_complete(
    client: AsyncClient,
) -> None:
    """Regenerate works mid-session; the window closes once either phase completes."""
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        + "\n".join(f"word{i},Definition {i},A1,General" for i in range(12))
        + "\n"
    )
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    leo_token = await _login(client, "leo", "leo")
    await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    # Mid-session (some cards answered, SRS not marked complete): regenerate resets.
    due = await client.get(
        "/api/v1/reviews/due?daily_challenge=1",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    cards = due.json()["cards"]
    assert cards
    await client.post(
        f"/api/v1/reviews/{cards[0]['id']}/answer",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"quality": 4},
    )
    random_regen = await client.post(
        "/api/v1/loop/today/regenerate",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"mode": "random"},
    )
    assert random_regen.status_code == 200
    assert random_regen.json()["srs_completed"] is False
    assert random_regen.json()["can_regenerate"] is True

    # Finish SRS: the day completes and regenerate is blocked.
    due2 = await client.get(
        "/api/v1/reviews/due?daily_challenge=1",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    for card in due2.json()["cards"]:
        await client.post(
            f"/api/v1/reviews/{card['id']}/answer",
            headers={"Authorization": f"Bearer {leo_token}"},
            json={"quality": 4},
        )
    srs_done = await client.post(
        "/api/v1/loop/today/srs-complete",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert srs_done.status_code == 200
    assert srs_done.json()["srs_completed"] is True
    assert srs_done.json()["completed"] is False

    progress = await client.get(
        "/api/v1/loop/progress",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert progress.json()["daily_challenge_completed"] is False

    blocked = await client.post(
        "/api/v1/loop/today/regenerate",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"mode": "random"},
    )
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_regenerate_blocks_after_dictation_complete(client: AsyncClient) -> None:
    """Listen & Pick completion locks the deck before recognition review."""
    parent_token = await _login(client, "parent", "parent123")
    csv_content = (
        "word,definition,level,category\n"
        + "\n".join(f"word{i},Definition {i},A1,General" for i in range(12))
        + "\n"
    )
    await client.post(
        "/api/v1/word-bank/import",
        headers={"Authorization": f"Bearer {parent_token}"},
        files={"file": ("bank.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    leo_token = await _login(client, "leo", "leo")
    await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )

    dictation = await client.post(
        "/api/v1/dictation/sessions",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"source": "daily_challenge", "mode": "choice", "max_words": 30},
    )
    assert dictation.status_code in (200, 201)
    await _complete_listen_and_pick(client, leo_token)

    progress = await client.get(
        "/api/v1/loop/progress",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert progress.json()["daily_challenge_dictation_completed"] is True
    assert progress.json()["daily_challenge_srs_completed"] is False
    assert progress.json()["daily_challenge_completed"] is False

    mix = await client.get(
        "/api/v1/loop/today",
        headers={"Authorization": f"Bearer {leo_token}"},
    )
    assert mix.json()["can_regenerate"] is False

    blocked = await client.post(
        "/api/v1/loop/today/regenerate",
        headers={"Authorization": f"Bearer {leo_token}"},
        json={"mode": "random"},
    )
    assert blocked.status_code == 409
