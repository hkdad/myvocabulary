from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import get_settings

ELEPHANT_FETCH = {
    "word": "elephant",
    "phonetic": "/ˈɛlɪfənt/",
    "part_of_speech": "noun",
    "definition": "A large mammal with a trunk.",
    "example_sentence": "The elephant walked slowly.",
    "synonyms": '["pachyderm"]',
    "source": "freedictionary",
    "source_url": "https://api.dictionaryapi.dev/api/v2/entries/en/elephant",
    "fetched_at": None,
}


async def _mock_fetch(word: str) -> dict:
    from datetime import UTC, datetime

    payload = dict(ELEPHANT_FETCH)
    payload["word"] = word
    payload["fetched_at"] = datetime.now(UTC)
    return payload


async def _login(client, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_dictionary_search_requires_auth(client) -> None:
    response = await client.get("/api/v1/dictionary/search", params={"q": "elephant"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_lookup_elephant_returns_definition(client) -> None:
    token = await _login(client, "mia", "mia")

    with (
        patch(
            "app.services.dictionary_service.fetch_from_api",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "app.services.dictionary_service.translate_definition_to_zh_hant",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        response = await client.get(
            "/api/v1/dictionary/words/elephant",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["word"] == "elephant"
    assert "trunk" in payload["definition"].lower()
    assert payload["part_of_speech"] == "noun"
    assert payload["definition_zh_hant"] is None


@pytest.mark.asyncio
async def test_lookup_does_not_auto_fill_zh_hant(client) -> None:
    """Dictionary GET returns cached gloss only; zh is filled via ensure-zh."""
    token = await _login(client, "mia", "mia")

    with (
        patch(
            "app.services.dictionary_service.fetch_from_api",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "app.services.dictionary_service.translate_definition_to_zh_hant",
            new_callable=AsyncMock,
            return_value="一種有象鼻的大型哺乳動物。",
        ),
    ):
        lookup = await client.get(
            "/api/v1/dictionary/words/elephant",
            headers={"Authorization": f"Bearer {token}"},
        )
        ensure = await client.post(
            "/api/v1/dictionary/ensure-zh",
            headers={"Authorization": f"Bearer {token}"},
            json={"entry_ids": [lookup.json()["id"]]},
        )

    assert lookup.status_code == 200
    assert lookup.json()["definition_zh_hant"] is None
    assert ensure.status_code == 200
    items = ensure.json()["items"]
    assert len(items) == 1
    assert items[0]["definition_zh_hant"] == "一種有象鼻的大型哺乳動物。"


def test_extract_zh_hant_from_json_and_reasoning() -> None:
    from app.services.dictionary_service import _extract_zh_hant

    assert _extract_zh_hant('{"zh_hant":"美麗的"}') == "美麗的"
    assert (
        _extract_zh_hant(
            'Example {"zh_hant":"..."}\n'
            'JSON format: `{"zh_hant":"具有血紅色或成熟番茄的顏色"}`\n'
            "More notes"
        )
        == "具有血紅色或成熟番茄的顏色"
    )
    assert _extract_zh_hant('{"zh_hant":"..."}') is None
    assert _extract_zh_hant("呈血紅色或熟番茄色") == "呈血紅色或熟番茄色"
    assert _extract_zh_hant("") is None
    assert _extract_zh_hant("no chinese here") is None


def test_build_translation_context_includes_word_and_pos() -> None:
    from app.services.dictionary_service import _build_translation_context

    text = _build_translation_context(
        word="line",
        part_of_speech="noun",
        definition="A long thin mark on a surface.",
        example_sentence="Draw a line on the paper.",
    )
    assert "Word: line" in text
    assert "Part of speech: noun" in text
    assert "A long thin mark on a surface." in text
    assert "Draw a line on the paper." in text


@pytest.mark.asyncio
async def test_translate_includes_word_context_in_chat_request() -> None:
    from app.services.dictionary_service import translate_definition_to_zh_hant

    captured: dict = {}

    async def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"zh_hant":"細長的線條"}'}}]
        }
        return response

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=fake_post)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.dictionary_service.get_settings") as mock_settings,
        patch("app.services.dictionary_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.return_value.openai_api_key = "test-key"
        mock_settings.return_value.openai_api_base = "https://api.example.com/v1"
        mock_settings.return_value.openai_model = "test-model"

        zh = await translate_definition_to_zh_hant(
            "A long thin mark on a surface.",
            word="line",
            part_of_speech="noun",
        )

    assert zh == "細長的線條"
    user_message = captured["json"]["messages"][1]["content"]
    assert "Word: line" in user_message
    assert "Part of speech: noun" in user_message
    assert "A long thin mark on a surface." in user_message


@pytest.mark.asyncio
async def test_translate_falls_back_to_mymemory_without_api_key() -> None:
    from app.services.dictionary_service import translate_definition_to_zh_hant

    async def fake_get(url: str, **kwargs):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "responseData": {"translatedText": "有輪子的圓形物體，使車輛能夠移動。"}
        }
        return response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.dictionary_service.get_settings") as mock_settings,
        patch("app.services.dictionary_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.return_value.openai_api_key = None
        mock_settings.return_value.openai_api_base = "https://api.example.com/v1"
        mock_settings.return_value.openai_model = "test-model"

        zh = await translate_definition_to_zh_hant(
            "a circular object that turns and allows vehicles to move",
            word="wheel",
        )

    assert zh is not None
    assert "輪" in zh


@pytest.mark.asyncio
async def test_ensure_zh_passes_entry_context_to_translate(client, db_session) -> None:
    from app.models.dictionary import DictionaryEntry

    token = await _login(client, "leo", "leo")
    entry = DictionaryEntry(
        word="line",
        part_of_speech="noun",
        definition="A long thin mark on a surface.",
        source="test",
        definition_zh_hant=None,
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)

    with patch(
        "app.services.dictionary_service.translate_definition_to_zh_hant",
        new_callable=AsyncMock,
        return_value="細長的線條",
    ) as mock_translate:
        response = await client.post(
            "/api/v1/dictionary/ensure-zh",
            headers={"Authorization": f"Bearer {token}"},
            json={"entry_ids": [entry.id]},
        )

    assert response.status_code == 200
    mock_translate.assert_awaited_once_with(
        "A long thin mark on a surface.",
        word="line",
        part_of_speech="noun",
        example_sentence=None,
    )


@pytest.mark.asyncio
async def test_clear_zh_hant_clears_cache(client, db_session) -> None:
    from app.models.dictionary import DictionaryEntry

    token = await _login(client, "leo", "leo")
    entry = DictionaryEntry(
        word="line",
        definition="A long thin mark on a surface.",
        source="test",
        definition_zh_hant="錯誤翻譯",
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)

    response = await client.delete(
        f"/api/v1/dictionary/entries/{entry.id}/zh-hant",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"id": entry.id, "definition_zh_hant": None}

    await db_session.refresh(entry)
    assert entry.definition_zh_hant is None


@pytest.mark.asyncio
async def test_clear_zh_hant_parent_can_clear(client, db_session) -> None:
    from app.models.dictionary import DictionaryEntry

    token = await _login(client, "parent", "parent123")
    entry = DictionaryEntry(
        word="line",
        definition="A long thin mark on a surface.",
        source="test",
        definition_zh_hant="錯誤翻譯",
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)

    response = await client.delete(
        f"/api/v1/dictionary/entries/{entry.id}/zh-hant",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_lookup_does_not_refill_cleared_zh(client, db_session) -> None:
    from datetime import UTC, datetime

    from app.models.dictionary import DictionaryEntry

    token = await _login(client, "leo", "leo")
    entry = DictionaryEntry(
        word="e2eline",
        definition="A long thin mark on a surface.",
        source="e2e",
        fetched_at=datetime.now(UTC),
        definition_zh_hant="錯誤翻譯",
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)

    cleared = await client.delete(
        f"/api/v1/dictionary/entries/{entry.id}/zh-hant",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cleared.status_code == 200

    with patch(
        "app.services.dictionary_service.translate_definition_to_zh_hant",
        new_callable=AsyncMock,
        return_value="表面上有一個細長的痕跡。",
    ):
        lookup = await client.get(
            "/api/v1/dictionary/words/e2eline",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert lookup.status_code == 200
    assert lookup.json()["definition_zh_hant"] is None


@pytest.mark.asyncio
async def test_clear_zh_hant_404(client) -> None:
    token = await _login(client, "leo", "leo")
    response = await client.delete(
        "/api/v1/dictionary/entries/99999/zh-hant",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ensure_zh_lazy_fills_missing_gloss(client, db_session) -> None:
    from app.models.dictionary import DictionaryEntry

    token = await _login(client, "leo", "leo")
    entry = DictionaryEntry(
        word="beautiful",
        definition="very attractive and pleasing to look at",
        source="test",
        definition_zh_hant=None,
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)

    with patch(
        "app.services.dictionary_service.translate_definition_to_zh_hant",
        new_callable=AsyncMock,
        return_value="美麗的；好看的",
    ):
        response = await client.post(
            "/api/v1/dictionary/ensure-zh",
            headers={"Authorization": f"Bearer {token}"},
            json={"entry_ids": [entry.id]},
        )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == entry.id
    assert items[0]["definition_zh_hant"] == "美麗的；好看的"

    await db_session.refresh(entry)
    assert entry.definition_zh_hant == "美麗的；好看的"


@pytest.mark.asyncio
async def test_suggest_finds_prefix_and_typo(client) -> None:
    token = await _login(client, "parent", "parent123")
    with patch(
        "app.services.dictionary_service.translate_definition_to_zh_hant",
        new_callable=AsyncMock,
        return_value=None,
    ):
        for word, definition in (
            ("elephant", "A large mammal with a trunk."),
            ("elegant", "Graceful and stylish."),
            ("element", "A basic part of something."),
        ):
            created = await client.post(
                "/api/v1/dictionary/words",
                headers={"Authorization": f"Bearer {token}"},
                json={"word": word, "definition": definition},
            )
            assert created.status_code == 201

        prefix = await client.get(
            "/api/v1/dictionary/suggest",
            params={"q": "ele"},
            headers={"Authorization": f"Bearer {token}"},
        )
        typo = await client.get(
            "/api/v1/dictionary/suggest",
            params={"q": "elefant"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert prefix.status_code == 200
    prefix_words = {item["word"] for item in prefix.json()["suggestions"]}
    assert "elephant" in prefix_words

    assert typo.status_code == 200
    typo_words = [item["word"] for item in typo.json()["suggestions"]]
    assert "elephant" in typo_words


@pytest.mark.asyncio
async def test_lookup_uses_cache_on_second_request(client) -> None:
    token = await _login(client, "mia", "mia")
    mock_fetch = AsyncMock(side_effect=_mock_fetch)

    with (
        patch("app.services.dictionary_service.fetch_from_api", mock_fetch),
        patch(
            "app.services.dictionary_service.translate_definition_to_zh_hant",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        first = await client.get(
            "/api/v1/dictionary/words/elephant",
            headers={"Authorization": f"Bearer {token}"},
        )
        second = await client.get(
            "/api/v1/dictionary/words/elephant",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert mock_fetch.call_count == 1


@pytest.mark.asyncio
async def test_parent_can_create_manual_word(client) -> None:
    token = await _login(client, "parent", "parent123")
    with patch(
        "app.services.dictionary_service.translate_definition_to_zh_hant",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.post(
            "/api/v1/dictionary/words",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "word": "familyspecial",
                "definition": "A word only our family uses.",
                "part_of_speech": "noun",
            },
        )
    assert response.status_code == 201
    payload = response.json()
    assert payload["word"] == "familyspecial"
    assert payload["source"] == "manual"


@pytest.mark.asyncio
async def test_learner_cannot_create_manual_word(client) -> None:
    token = await _login(client, "leo", "leo")
    response = await client.post(
        "/api/v1/dictionary/words",
        headers={"Authorization": f"Bearer {token}"},
        json={"word": "blocked", "definition": "Should not be allowed."},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_search_finds_word_by_definition(client) -> None:
    token = await _login(client, "parent", "parent123")
    with patch(
        "app.services.dictionary_service.translate_definition_to_zh_hant",
        new_callable=AsyncMock,
        return_value=None,
    ):
        create = await client.post(
            "/api/v1/dictionary/words",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "word": "aurora",
                "definition": "A shimmering polar light in the night sky.",
                "example_sentence": "We watched the aurora dance above the snow.",
            },
        )
    assert create.status_code == 201

    search = await client.get(
        "/api/v1/dictionary/search",
        params={"q": "polar light"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert search.status_code == 200
    results = search.json()["results"]
    assert any(item["word"] == "aurora" for item in results)


@pytest.mark.asyncio
async def test_audio_endpoint_returns_mp3(client, tmp_path, monkeypatch) -> None:
    token = await _login(client, "mia", "mia")
    monkeypatch.setenv("AUDIO_DIR", str(tmp_path))
    get_settings.cache_clear()

    async def fake_save(path: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake-mp3-data")

    mock_fetch = AsyncMock(side_effect=_mock_fetch)
    with (
        patch("app.services.dictionary_service.fetch_from_api", mock_fetch),
        patch(
            "app.services.dictionary_service.translate_definition_to_zh_hant",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.services.tts_service.edge_tts.Communicate") as mock_communicate,
    ):
        mock_instance = MagicMock()
        mock_instance.save = AsyncMock(side_effect=fake_save)
        mock_communicate.return_value = mock_instance

        response = await client.get(
            "/api/v1/dictionary/words/elephant/audio",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/mpeg")
        assert mock_communicate.call_count == 1

        cached = await client.get(
            "/api/v1/dictionary/words/elephant/audio",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert cached.status_code == 200
        assert mock_communicate.call_count == 1

    get_settings.cache_clear()
