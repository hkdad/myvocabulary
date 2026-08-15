from datetime import date, datetime

from pydantic import BaseModel


class LearnerProgressSummary(BaseModel):
    learner_id: int
    display_name: str
    username: str
    english_level: str
    ui_mode: str
    emoji: str
    due_count: int
    reviewed_today: int
    daily_practice_goal: int
    daily_new_word_goal: int
    daily_learning_retention_goal: int = 1
    daily_mastered_retention_goal: int = 1
    daily_retention_goal: int = 2
    review_accuracy_percent: float
    streak_days: int
    dictation_sessions_completed: int
    unresolved_mistakes: int
    assigned_lists: int
    learning_count: int = 0
    familiar_count: int = 0
    mastered_count: int = 0
    new_released_today: int = 0
    new_remaining_today: int = 0
    daily_challenge_completed: bool = False
    bank_at_level: int = 0
    due_overloaded: bool = False


class DashboardOverviewResponse(BaseModel):
    learners: list[LearnerProgressSummary]


class ActivityItem(BaseModel):
    type: str
    description: str
    occurred_at: datetime


class LearnerDetailResponse(LearnerProgressSummary):
    recent_activity: list[ActivityItem]


class LearnerMeStatsResponse(BaseModel):
    english_level: str
    display_name: str
    due_count: int
    reviewed_today: int
    daily_practice_goal: int
    daily_new_word_goal: int
    daily_learning_retention_goal: int = 1
    daily_mastered_retention_goal: int = 1
    daily_retention_goal: int = 2
    review_accuracy_percent: float
    streak_days: int
    dictation_sessions_completed: int
    unresolved_mistakes: int
    learning_count: int = 0
    familiar_count: int = 0
    mastered_count: int = 0
    new_released_today: int = 0
    new_remaining_today: int = 0
    new_released_this_week: int = 0
    weekly_new_target: int = 25
    daily_challenge_completed: bool = False
    daily_challenge_srs_completed: bool = False
    daily_challenge_dictation_completed: bool = False


class TrendDayPoint(BaseModel):
    date: date
    reviews: int
    correct_reviews: int
    accuracy_percent: float
    new_words: int
    challenge_completed: bool
    learning_count: int = 0
    familiar_count: int = 0
    mastered_count: int = 0


class LearnerTrendSeries(BaseModel):
    learner_id: int
    display_name: str
    emoji: str
    days: list[TrendDayPoint]


class FamilyTrendsResponse(BaseModel):
    days: int
    learners: list[LearnerTrendSeries]
