import asyncio
import hashlib
from pathlib import Path

import edge_tts
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.dictionary import DictionaryEntry
from app.services import dictionary_service

SLOW_RATE = "-45%"
_PATH_LOCKS: dict[str, asyncio.Lock] = {}
_PATH_LOCKS_GUARD = asyncio.Lock()


def _audio_filename(*, slow: bool = False) -> str:
    voice = get_settings().tts_voice.lower().replace("_", "-")
    return f"{voice}-slow.mp3" if slow else f"{voice}.mp3"


def audio_path_for_word(word: str, *, slow: bool = False) -> Path:
    settings = get_settings()
    digest = hashlib.sha256(word.encode()).hexdigest()[:16]
    return settings.audio_dir / digest / _audio_filename(slow=slow)


async def _lock_for_path(path: Path) -> asyncio.Lock:
    key = str(path.resolve()) if path.exists() else str(path)
    async with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _PATH_LOCKS[key] = lock
        return lock


async def ensure_audio(db: AsyncSession, entry: DictionaryEntry, *, slow: bool = False) -> Path:
    settings = get_settings()
    settings.audio_dir.mkdir(parents=True, exist_ok=True)

    path = audio_path_for_word(entry.word, slow=slow)
    lock = await _lock_for_path(path)
    async with lock:
        if path.exists() and path.stat().st_size > 0:
            if not slow and entry.audio_path != str(path):
                entry.audio_path = str(path)
                await db.commit()
            return path

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        if tmp_path.exists():
            tmp_path.unlink()
        communicate = edge_tts.Communicate(
            entry.word,
            settings.tts_voice,
            rate=SLOW_RATE if slow else "+0%",
        )
        await communicate.save(str(tmp_path))
        tmp_path.replace(path)

        if not slow:
            entry.audio_path = str(path)
            await db.commit()
            await db.refresh(entry)
        return path


async def get_audio_for_word(db: AsyncSession, word: str, *, slow: bool = False) -> Path:
    # Prefer cached entry; avoid AI translation work on the audio hot path.
    entry = await dictionary_service.get_entry_by_word(db, word)
    if entry is None:
        entry = await dictionary_service.lookup_word(db, word)
    return await ensure_audio(db, entry, slow=slow)
