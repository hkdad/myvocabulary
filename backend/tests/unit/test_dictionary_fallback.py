import pytest
from fastapi import HTTPException

from app.services.dictionary_service import _parse_fallback_response, fetch_from_api

LOOK_FALLBACK = {
    "word": "look",
    "meanings": [
        {
            "partOfSpeech": "verb",
            "senses": [{"glosses": ["Pay attention."], "examples": ["Look at the sky."]}],
        },
        {
            "partOfSpeech": "noun",
            "senses": [{"glosses": ["The action of looking."], "examples": []}],
        },
    ],
}

PICTURE_FALLBACK = {
    "word": "picture",
    "meanings": [
        {
            "partOfSpeech": "noun",
            "senses": [
                {
                    "glosses": ["A visual representation of something."],
                    "examples": ["A picture of the family."],
                }
            ],
        }
    ],
}


def test_parse_fallback_prefers_noun_definition() -> None:
    payload = _parse_fallback_response("look", LOOK_FALLBACK)
    assert payload["word"] == "look"
    assert payload["part_of_speech"] == "noun"
    assert "visual" not in payload["definition"].lower()
    assert payload["source"] == "wiktionary"


def test_parse_fallback_picture() -> None:
    payload = _parse_fallback_response("picture", PICTURE_FALLBACK)
    assert payload["word"] == "picture"
    assert "visual" in payload["definition"].lower()
    assert payload["example_sentence"] == "A picture of the family."


def test_parse_fallback_empty_meanings_raises() -> None:
    with pytest.raises(HTTPException) as exc:
        _parse_fallback_response("missing", {"word": "missing", "meanings": []})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_from_api_uses_fallback_when_primary_fails(monkeypatch) -> None:
    async def fail_primary(word: str) -> dict:
        raise HTTPException(status_code=502, detail="upstream down")

    async def succeed_fallback(word: str) -> dict:
        return _parse_fallback_response(word, PICTURE_FALLBACK)

    monkeypatch.setattr("app.services.dictionary_service._fetch_primary", fail_primary)
    monkeypatch.setattr("app.services.dictionary_service._fetch_fallback", succeed_fallback)

    payload = await fetch_from_api("picture")
    assert payload["word"] == "picture"
    assert payload["source"] == "wiktionary"
