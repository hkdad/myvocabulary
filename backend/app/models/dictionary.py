from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class DictionaryEntry(Base, TimestampMixin):
    __tablename__ = "dictionary_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    phonetic: Mapped[str | None] = mapped_column(String(128), nullable=True)
    part_of_speech: Mapped[str | None] = mapped_column(String(64), nullable=True)
    definition: Mapped[str] = mapped_column(Text)
    definition_zh_hant: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    synonyms: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
