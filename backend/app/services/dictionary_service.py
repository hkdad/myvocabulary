import json
import re
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.dictionary import DictionaryEntry

CACHE_DAYS = 30
_PREFERRED_POS = ("noun", "verb", "adjective", "adverb")


def normalize_word(word: str) -> str:
    return word.strip().lower()


def _escape_fts_query(query: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", " ", query.strip().lower())
    tokens = [token for token in cleaned.split() if token]
    if not tokens:
        return ""
    return " ".join(f'"{token}"*' for token in tokens)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            insert = curr[j - 1] + 1
            delete = prev[j] + 1
            replace = prev[j - 1] + (0 if ca == cb else 1)
            curr.append(min(insert, delete, replace))
        prev = curr
    return prev[-1]


def max_edit_distance(query: str) -> int:
    length = len(query)
    if length <= 4:
        return 1
    if length <= 7:
        return 2
    return 3


def entry_to_dict(entry: DictionaryEntry) -> dict:
    return {
        "id": entry.id,
        "word": entry.word,
        "phonetic": entry.phonetic,
        "part_of_speech": entry.part_of_speech,
        "definition": entry.definition,
        "definition_zh_hant": entry.definition_zh_hant,
        "example_sentence": entry.example_sentence,
        "synonyms": json.loads(entry.synonyms) if entry.synonyms else [],
        "source": entry.source,
        "audio_path": entry.audio_path,
        "has_audio": entry.audio_path is not None,
    }


def _row_to_dict(row: dict) -> dict:
    synonyms_raw = row.get("synonyms")
    if isinstance(synonyms_raw, str):
        try:
            synonyms = json.loads(synonyms_raw)
        except json.JSONDecodeError:
            synonyms = []
    elif isinstance(synonyms_raw, list):
        synonyms = synonyms_raw
    else:
        synonyms = []
    return {
        "id": row["id"],
        "word": row["word"],
        "phonetic": row.get("phonetic"),
        "part_of_speech": row.get("part_of_speech"),
        "definition": row["definition"],
        "definition_zh_hant": row.get("definition_zh_hant"),
        "example_sentence": row.get("example_sentence"),
        "synonyms": synonyms,
        "source": row["source"],
        "audio_path": row.get("audio_path"),
        "has_audio": row.get("audio_path") is not None,
    }


async def get_entry_by_word(db: AsyncSession, word: str) -> DictionaryEntry | None:
    normalized = normalize_word(word)
    result = await db.execute(select(DictionaryEntry).where(DictionaryEntry.word == normalized))
    return result.scalar_one_or_none()


def _is_cache_fresh(entry: DictionaryEntry) -> bool:
    if entry.fetched_at is None:
        return entry.source == "manual"
    fetched = entry.fetched_at
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    return fetched > datetime.now(UTC) - timedelta(days=CACHE_DAYS)


def _build_entry_payload(
    word: str,
    *,
    definition: str,
    part_of_speech: str | None,
    example_sentence: str | None,
    phonetic: str | None,
    synonyms: list[str],
    source: str,
    source_url: str,
) -> dict:
    return {
        "word": normalize_word(word),
        "phonetic": phonetic,
        "part_of_speech": part_of_speech,
        "definition": definition,
        "example_sentence": example_sentence,
        "synonyms": json.dumps(synonyms[:10]) if synonyms else None,
        "source": source,
        "source_url": source_url,
        "fetched_at": datetime.now(UTC),
    }


def _parse_api_response(word: str, payload: list[dict]) -> dict:
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")
    item = payload[0]
    phonetic = item.get("phonetic")
    meanings = item.get("meanings") or []
    definition = ""
    part_of_speech = None
    example_sentence = None
    synonyms: list[str] = []

    for meaning in meanings:
        part_of_speech = part_of_speech or meaning.get("partOfSpeech")
        for defn in meaning.get("definitions") or []:
            if not definition:
                definition = defn.get("definition", "")
                example_sentence = defn.get("example")
            for syn in defn.get("synonyms") or []:
                if syn not in synonyms:
                    synonyms.append(syn)
        if definition:
            break

    if not definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")

    settings = get_settings()
    return _build_entry_payload(
        item.get("word") or word,
        definition=definition,
        part_of_speech=part_of_speech,
        example_sentence=example_sentence,
        phonetic=phonetic,
        synonyms=synonyms,
        source="freedictionary",
        source_url=f"{settings.dictionary_api_url}/{normalize_word(word)}",
    )


def _is_usable_gloss(gloss: str) -> bool:
    cleaned = gloss.strip()
    if len(cleaned) < 3:
        return False
    skip_prefixes = ("troponym", "as a ", "as an ", "see also")
    lowered = cleaned.lower()
    return not any(lowered.startswith(prefix) for prefix in skip_prefixes)


def _pick_suvankar_sense(meanings: list[dict]) -> tuple[str, str | None, str | None]:
    ordered = sorted(
        meanings,
        key=lambda meaning: (
            _PREFERRED_POS.index(meaning["partOfSpeech"])
            if meaning.get("partOfSpeech") in _PREFERRED_POS
            else len(_PREFERRED_POS)
        ),
    )
    for meaning in ordered:
        part_of_speech = meaning.get("partOfSpeech")
        for sense in meaning.get("senses") or []:
            for gloss in sense.get("glosses") or []:
                if not _is_usable_gloss(gloss):
                    continue
                example = None
                examples = sense.get("examples") or []
                if examples:
                    example = str(examples[0]).split("\n")[0].strip()
                return gloss.strip(), part_of_speech, example
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")


def _parse_fallback_response(word: str, payload: dict) -> dict:
    meanings = payload.get("meanings") or []
    if not meanings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")

    definition, part_of_speech, example_sentence = _pick_suvankar_sense(meanings)
    settings = get_settings()
    source_url = f"{settings.dictionary_fallback_api_url}/{normalize_word(word)}?compact=true"
    return _build_entry_payload(
        payload.get("word") or word,
        definition=definition,
        part_of_speech=part_of_speech,
        example_sentence=example_sentence,
        phonetic=None,
        synonyms=[],
        source="wiktionary",
        source_url=source_url,
    )


async def _fetch_primary(word: str) -> dict:
    settings = get_settings()
    url = f"{settings.dictionary_api_url}/{normalize_word(word)}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url)
    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")
    return _parse_api_response(word, payload)


async def _fetch_fallback(word: str) -> dict:
    settings = get_settings()
    url = f"{settings.dictionary_fallback_api_url}/{normalize_word(word)}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params={"compact": "true"})
    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")
    return _parse_fallback_response(word, payload)


async def fetch_from_api(word: str) -> dict:
    try:
        return await _fetch_primary(word)
    except (HTTPException, httpx.HTTPError):
        return await _fetch_fallback(word)


_CJK_RE = re.compile(r"[\u3400-\u9FFF]+")
_PLACEHOLDER_ZH = {"...", "…", "—", "-", "<gloss>", "TRANSLATION_HERE"}


def _is_usable_zh(zh: str) -> bool:
    cleaned = zh.strip()
    if not cleaned or cleaned in _PLACEHOLDER_ZH:
        return False
    cjk_chars = "".join(_CJK_RE.findall(cleaned))
    return len(cjk_chars) >= 2


def _extract_zh_hant(text: str) -> str | None:
    """Pull a Traditional Chinese gloss out of model output (JSON, plain, or reasoning)."""
    cleaned = text.strip()
    if not cleaned:
        return None

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    candidate = fence.group(1) if fence else cleaned

    # Prefer the last JSON object — reasoning transcripts often repeat the
    # prompt example {"zh_hant":"..."} before the real answer.
    json_matches = list(re.finditer(r"\{[^{}]*\"zh_hant\"[^{}]*\}", candidate, re.DOTALL))
    for match in reversed(json_matches):
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        zh = str(payload.get("zh_hant", "")).strip()
        if _is_usable_zh(zh):
            return zh

    try:
        payload = json.loads(candidate)
        zh = str(payload.get("zh_hant", "")).strip()
        if _is_usable_zh(zh):
            return zh
    except json.JSONDecodeError:
        pass

    for line in reversed(cleaned.splitlines()):
        line = line.strip().strip("`\"'")
        line = re.sub(r"^(zh_hant|翻譯|譯文)\s*[:：]\s*", "", line, flags=re.IGNORECASE)
        if _is_usable_zh(line):
            compact = re.sub(r"\s+", "", line)
            cjk_chars = "".join(_CJK_RE.findall(line))
            if len(cjk_chars) >= len(compact) * 0.5:
                return line

    runs = _CJK_RE.findall(cleaned)
    if not runs:
        return None
    best = max(runs, key=len)
    return best if _is_usable_zh(best) else None


def _build_translation_context(
    *,
    definition: str,
    word: str | None = None,
    part_of_speech: str | None = None,
    example_sentence: str | None = None,
) -> str:
    lines = []
    if word and word.strip():
        lines.append(f"Word: {word.strip()}")
    if part_of_speech and part_of_speech.strip():
        lines.append(f"Part of speech: {part_of_speech.strip()}")
    lines.append(f"Definition: {definition.strip()}")
    if example_sentence and example_sentence.strip():
        lines.append(f"Example: {example_sentence.strip()}")
    return "\n".join(lines)


async def translate_definition_to_zh_hant(
    definition: str,
    *,
    word: str | None = None,
    part_of_speech: str | None = None,
    example_sentence: str | None = None,
) -> str | None:
    """Translate an English gloss to Traditional Chinese. Returns None if unavailable."""
    settings = get_settings()
    cleaned = definition.strip()
    if not cleaned or not settings.openai_api_key:
        return None

    user_content = _build_translation_context(
        definition=cleaned,
        word=word,
        part_of_speech=part_of_speech,
        example_sentence=example_sentence,
    )

    api_base = settings.openai_api_base.rstrip("/")
    # Only local Ollama — do not treat every ".../v1" provider (e.g. OpenCode) as Ollama.
    is_ollama = ":11434" in api_base or api_base.startswith("http://127.0.0.1:11434")
    ollama_root = api_base[: -len("/v1")] if api_base.endswith("/v1") else api_base

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            # Local Ollama/MLX: /api/generate returns Chinese quickly. The OpenAI-compat
            # chat endpoint often parks the answer in "reasoning" and leaves content empty.
            if is_ollama:
                gen = await client.post(
                    f"{ollama_root}/api/generate",
                    json={
                        "model": settings.openai_model,
                        "prompt": (
                            "Translate the meaning of this English dictionary entry into "
                            "Traditional Chinese (繁體中文). Match THIS definition only — "
                            "do not use other senses of the word. "
                            "Reply with ONLY the Chinese gloss:\n"
                            f"{user_content}"
                        ),
                        "stream": False,
                        "options": {"temperature": 0.2, "num_predict": 80},
                    },
                )
                if gen.status_code == 200:
                    zh = _extract_zh_hant(str(gen.json().get("response") or ""))
                    if zh:
                        return zh

            system = (
                "You translate English dictionary definitions into Traditional Chinese "
                "(繁體中文) for Hong Kong / Taiwan learners. "
                'Reply with JSON only in this exact shape: {"zh_hant":"<gloss>"}. '
                "Translate the meaning of THIS definition only — do not pick other senses "
                "of the word. Short, natural gloss; no pinyin; no English."
            )
            response = await client.post(
                f"{api_base}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1024,
                },
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            content = str(message.get("content") or "").strip()
            zh = _extract_zh_hant(content) if content else None
            if zh:
                return zh

            reasoning = str(message.get("reasoning") or "").strip()
            return _extract_zh_hant(reasoning) if reasoning else None
    except Exception:
        return None


def _translation_kwargs(entry: DictionaryEntry) -> dict[str, str | None]:
    return {
        "word": entry.word,
        "part_of_speech": entry.part_of_speech,
        "example_sentence": entry.example_sentence,
    }


async def ensure_zh_hant(db: AsyncSession, entry: DictionaryEntry) -> DictionaryEntry:
    if entry.definition_zh_hant and entry.definition_zh_hant.strip():
        return entry
    zh = await translate_definition_to_zh_hant(entry.definition, **_translation_kwargs(entry))
    if not zh:
        return entry
    entry.definition_zh_hant = zh
    await db.commit()
    await db.refresh(entry)
    return entry


async def clear_zh_hant(db: AsyncSession, entry_id: int) -> DictionaryEntry:
    result = await db.execute(select(DictionaryEntry).where(DictionaryEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")
    entry.definition_zh_hant = None
    await db.commit()
    await db.refresh(entry)
    return entry


async def ensure_zh_for_entry_ids(
    db: AsyncSession, entry_ids: list[int]
) -> list[dict[str, int | str | None]]:
    """Lazily translate missing Traditional Chinese glosses for the given entries.

    Skips ids that already have a gloss. Translates missing entries one-by-one —
    local LLMs (Ollama/MLX) choke when 3–4 chat calls run in parallel.
    Returns only entries that have a gloss after this call (cached or newly filled).
    """
    unique_ids = list(dict.fromkeys(entry_id for entry_id in entry_ids if entry_id > 0))
    if not unique_ids:
        return []

    result = await db.execute(select(DictionaryEntry).where(DictionaryEntry.id.in_(unique_ids)))
    entries = {entry.id: entry for entry in result.scalars().all()}

    missing = [
        entry
        for entry_id in unique_ids
        if (entry := entries.get(entry_id)) is not None
        and not (entry.definition_zh_hant and entry.definition_zh_hant.strip())
    ]
    for entry in missing:
        zh = await translate_definition_to_zh_hant(entry.definition, **_translation_kwargs(entry))
        if zh:
            entry.definition_zh_hant = zh
    if missing:
        await db.commit()
        for entry in missing:
            await db.refresh(entry)

    filled: list[dict[str, int | str | None]] = []
    for entry_id in unique_ids:
        entry = entries.get(entry_id)
        if entry is None:
            continue
        if entry.definition_zh_hant and entry.definition_zh_hant.strip():
            filled.append(
                {
                    "id": entry.id,
                    "definition_zh_hant": entry.definition_zh_hant,
                }
            )
    return filled


async def lookup_word(db: AsyncSession, word: str) -> DictionaryEntry:
    normalized = normalize_word(word)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Word is required")

    existing = await get_entry_by_word(db, normalized)
    if existing and _is_cache_fresh(existing):
        return await ensure_zh_hant(db, existing)

    data = await fetch_from_api(normalized)
    if existing:
        if existing.definition != data["definition"]:
            existing.definition_zh_hant = None
        existing.phonetic = data["phonetic"]
        existing.part_of_speech = data["part_of_speech"]
        existing.definition = data["definition"]
        existing.example_sentence = data["example_sentence"]
        existing.synonyms = data["synonyms"]
        existing.source = data["source"]
        existing.source_url = data["source_url"]
        existing.fetched_at = data["fetched_at"]
        await db.commit()
        await db.refresh(existing)
        return await ensure_zh_hant(db, existing)

    entry = DictionaryEntry(**data)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return await ensure_zh_hant(db, entry)


async def create_manual_entry(
    db: AsyncSession,
    *,
    word: str,
    definition: str,
    phonetic: str | None = None,
    part_of_speech: str | None = None,
    example_sentence: str | None = None,
) -> DictionaryEntry:
    normalized = normalize_word(word)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Word is required")

    existing = await get_entry_by_word(db, normalized)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Word already exists")

    entry = DictionaryEntry(
        word=normalized,
        phonetic=phonetic,
        part_of_speech=part_of_speech,
        definition=definition.strip(),
        example_sentence=example_sentence,
        synonyms=None,
        source="manual",
        source_url=None,
        fetched_at=datetime.now(UTC),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return await ensure_zh_hant(db, entry)


async def search_words(db: AsyncSession, query: str, *, limit: int = 20) -> list[dict]:
    fts_query = _escape_fts_query(query)
    if not fts_query:
        return []

    sql = text(
        """
        SELECT d.id, d.word, d.phonetic, d.part_of_speech, d.definition,
               d.definition_zh_hant, d.example_sentence, d.synonyms, d.source, d.audio_path,
               bm25(dictionary_entries_fts) AS rank
        FROM dictionary_entries_fts
        JOIN dictionary_entries d ON d.id = dictionary_entries_fts.rowid
        WHERE dictionary_entries_fts MATCH :query
        ORDER BY rank
        LIMIT :limit
        """
    )
    result = await db.execute(sql, {"query": fts_query, "limit": limit})
    rows = result.mappings().all()
    return [_row_to_dict(dict(row)) for row in rows]


async def suggest_words(db: AsyncSession, query: str, *, limit: int = 5) -> list[dict]:
    """Prefix/FTS matches plus near-miss typo candidates from the local cache."""
    normalized = normalize_word(query)
    if not normalized:
        return []

    fts_hits = await search_words(db, normalized, limit=limit)
    by_word = {item["word"]: item for item in fts_hits}

    max_dist = max_edit_distance(normalized)
    min_len = max(1, len(normalized) - max_dist)
    max_len = len(normalized) + max_dist
    first = normalized[0]

    result = await db.execute(
        select(DictionaryEntry)
        .where(
            func.length(DictionaryEntry.word).between(min_len, max_len),
            DictionaryEntry.word.like(f"{first}%"),
        )
        .limit(200)
    )
    candidates = result.scalars().all()
    scored: list[tuple[int, DictionaryEntry]] = []
    for entry in candidates:
        if entry.word == normalized:
            continue
        distance = levenshtein(normalized, entry.word)
        if distance <= max_dist:
            scored.append((distance, entry))

    scored.sort(key=lambda item: (item[0], item[1].word))
    for distance, entry in scored:
        if entry.word in by_word:
            continue
        by_word[entry.word] = entry_to_dict(entry)
        if len(by_word) >= limit:
            break

    # Prefer exact-prefix FTS order, then typo fills
    ordered: list[dict] = []
    seen: set[str] = set()
    for item in fts_hits:
        if item["word"] not in seen:
            ordered.append(item)
            seen.add(item["word"])
    for item in by_word.values():
        if item["word"] not in seen:
            ordered.append(item)
            seen.add(item["word"])
        if len(ordered) >= limit:
            break
    return ordered[:limit]
