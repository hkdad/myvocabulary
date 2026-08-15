from datetime import datetime

from pydantic import BaseModel


class LevelSuggestionResponse(BaseModel):
    id: int | None = None
    learner_id: int
    current_level: str
    suggested_level: str
    reason: str | None = None
    source: str
    confidence: float | None = None
    status: str = "none"
    assessed_at: datetime | None = None


class LevelAssessmentActionResponse(BaseModel):
    assessment_id: int
    learner_id: int
    english_level: str
    status: str


class DimensionScore(BaseModel):
    score: float
    weight: float
    status: str
    description: str


class ReadinessMetadata(BaseModel):
    current_level: str
    streak_days: int
    review_samples: int
    total_mistakes: int


class ReadinessResponse(BaseModel):
    overall_score: float
    dimensions: dict[str, DimensionScore]
    recommendation: str
    focus_areas: list[str]
    estimated_weeks_to_ready: int
    metadata: ReadinessMetadata


class AssessmentSuggestionResponse(BaseModel):
    should_suggest: bool
    reason: str | None
    cooldown_days_remaining: int
