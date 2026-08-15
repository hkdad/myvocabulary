from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.word_list import DictionaryEntrySummary


class SrsCardResponse(BaseModel):
    id: int
    dictionary_entry: DictionaryEntrySummary
    ease_factor: float
    interval_days: int
    repetitions: int
    due_at: datetime
    last_reviewed_at: datetime | None
    last_quality: int | None
    state: str
    word_list_id: int | None


class DueCardsResponse(BaseModel):
    cards: list[SrsCardResponse]
    due_count: int
    daily_goal: int


class ReviewStatsResponse(BaseModel):
    reviewed_today: int
    due_count: int
    daily_goal: int
    total_cards: int


class ReviewAnswerRequest(BaseModel):
    quality: int = Field(ge=0, le=5)


class ReviewAnswerResponse(BaseModel):
    card: SrsCardResponse


class InitializeReviewsResponse(BaseModel):
    created_count: int
    skipped_count: int
    total_cards: int


class InitializeMistakeReviewsResponse(BaseModel):
    created_count: int
    mistake_count: int


class MistakeCardResponse(BaseModel):
    id: int
    dictionary_entry: DictionaryEntrySummary
    context: str
    occurred_at: datetime


class MistakeCardsResponse(BaseModel):
    cards: list[MistakeCardResponse]


class CompleteMistakeChallengeRequest(BaseModel):
    dictionary_entry_ids: list[int] = Field(min_length=1, max_length=5)


class CompleteMistakeChallengeResponse(BaseModel):
    resolved_count: int
    entry_count: int
