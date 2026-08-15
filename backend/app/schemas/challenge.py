from datetime import datetime

from pydantic import BaseModel, Field


class ChallengeSummary(BaseModel):
    id: int | None = None
    challenge_type: str
    title: str
    description: str
    target_level: str | None = None
    status: str | None = None
    can_start: bool = True
    word_count: int | None = None
    pass_threshold: float | None = None
    readiness_score: float | None = None
    lock_reason: str | None = None


class AvailableChallengesResponse(BaseModel):
    challenges: list[ChallengeSummary]


class ChallengeStartRequest(BaseModel):
    challenge_type: str = Field(min_length=1, max_length=32)
    challenge_id: int | None = None
    target_level: str | None = Field(default=None, max_length=8)


class ChallengeWordPrompt(BaseModel):
    dictionary_entry_id: int
    word_index: int
    total_words: int
    definition: str | None = None
    choices: list[str] = Field(default_factory=list)


class ChallengeSessionResponse(BaseModel):
    id: int
    challenge_type: str
    target_level: str | None
    status: str
    pass_threshold: float
    total_words: int
    words: list[ChallengeWordPrompt]
    started_at: datetime | None


class ChallengeAnswerItem(BaseModel):
    dictionary_entry_id: int
    answer: str = Field(min_length=0, max_length=128)


class ChallengeSubmitRequest(BaseModel):
    answers: list[ChallengeAnswerItem]


class ChallengeSubmitResponse(BaseModel):
    id: int
    status: str
    score: float
    passed: bool
    correct_count: int
    total_words: int
    badge_earned: str | None = None
    new_english_level: str | None = None


class ChallengeHistoryItem(BaseModel):
    id: int
    challenge_type: str
    target_level: str | None
    status: str
    score: float | None
    completed_at: datetime | None


class ChallengeHistoryResponse(BaseModel):
    items: list[ChallengeHistoryItem]


class LearnerBadgeResponse(BaseModel):
    id: int
    badge_type: str
    earned_at: datetime


class LearnerBadgesResponse(BaseModel):
    badges: list[LearnerBadgeResponse]
