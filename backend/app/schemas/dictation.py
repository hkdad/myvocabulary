from datetime import datetime

from pydantic import BaseModel, Field


class DictationSessionCreateRequest(BaseModel):
    word_list_id: int | None = Field(default=None, ge=1)
    source: str = Field(default="word_list", pattern="^(word_list|mistakes|daily_challenge)$")
    mode: str | None = Field(default=None, pattern="^(typed|choice)$")
    max_words: int = Field(default=10, ge=1, le=30)
    entry_ids: list[int] | None = Field(default=None, min_length=1, max_length=30)


class DictationSessionResponse(BaseModel):
    id: int
    word_list_id: int | None
    source: str = "word_list"
    mode: str
    ui_mode_snapshot: str
    total_words: int
    correct_count: int
    completed: bool
    started_at: datetime
    completed_at: datetime | None


class DictationPromptResponse(BaseModel):
    word_index: int
    total_words: int
    mode: str
    choices: list[str] | None = None
    hint: str | None = None
    retries_remaining: int
    session_complete: bool = False


class DictationAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=255)
    hint_used: bool = False


class DictationAnswerResponse(BaseModel):
    is_correct: bool
    expected_word: str | None = None
    syllables: list[str] | None = None
    can_retry: bool = False
    retries_remaining: int
    session_complete: bool
    correct_count: int
    total_words: int


class DictationHistoryItem(BaseModel):
    id: int
    mode: str
    total_words: int
    correct_count: int
    started_at: datetime
    completed_at: datetime | None
    score_percent: float


class DictationHistoryResponse(BaseModel):
    sessions: list[DictationHistoryItem]
