from pydantic import BaseModel, Field

from app.schemas.review import SrsCardResponse


class WordBankImportResponse(BaseModel):
    bank_id: int
    created: int
    updated: int
    skipped: int
    placeholder_count: int
    needs_level_count: int
    invalid_category_count: int = 0
    total_items: int
    errors: list[str] = Field(default_factory=list)


class WordBankSummaryResponse(BaseModel):
    bank_id: int | None
    name: str
    total_items: int
    by_level: dict[str, int]
    by_category: dict[str, int]


class WordBankDeleteResponse(BaseModel):
    deleted_items: int
    deleted_cards: int


class WordBankItem(BaseModel):
    id: int
    word: str
    definition: str
    part_of_speech: str | None
    phonetic: str | None
    has_audio: bool
    level: str | None
    categories: list[str] = Field(default_factory=list)
    sort_order: int


class WordBankItemsResponse(BaseModel):
    items: list[WordBankItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class LoopProgressResponse(BaseModel):
    learning_count: int
    familiar_count: int
    mastered_count: int
    due_count: int
    new_released_today: int
    daily_new_goal: int
    new_remaining_today: int
    new_released_this_week: int = 0
    weekly_new_target: int = 25
    bank_total: int
    bank_at_level: int
    daily_challenge_completed: bool
    daily_challenge_srs_completed: bool = False
    daily_challenge_dictation_completed: bool = False


class DailyMixResponse(BaseModel):
    cards: list[SrsCardResponse]
    new_count: int
    retention_count: int
    learning_retention_count: int = 0
    mastered_retention_count: int = 0
    daily_new_goal: int
    daily_learning_retention_goal: int = 1
    daily_mastered_retention_goal: int = 1
    daily_retention_goal: int
    new_released_today: int
    completed_today: bool
    srs_completed: bool = False
    dictation_completed: bool = False
    suggested: bool
    source_kind: str | None = "random"
    source_ref: str | None = None
    can_regenerate: bool = True
    book_title: str | None = None
    study_progress_percent: float | None = None
    page_coverage_percent: float | None = None
    ready_to_read: bool | None = None
    book_study_total: int | None = None
    book_learning_count: int | None = None
    book_familiar_count: int | None = None
    book_mastered_count: int | None = None


class ChallengeSourceCategory(BaseModel):
    name: str
    word_count: int


class ChallengeSourceList(BaseModel):
    id: int
    name: str
    item_count: int


class ChallengeSourceOptionsResponse(BaseModel):
    english_level: str
    categories: list[ChallengeSourceCategory]
    my_lists: list[ChallengeSourceList]
    can_regenerate: bool
    source_kind: str = "random"
    source_ref: str | None = None


class RegenerateDailyMixRequest(BaseModel):
    mode: str = "random"  # random | category | list
    category: str | None = None
    word_list_id: int | None = None


class DailyChallengeCompleteResponse(BaseModel):
    completed: bool
    completed_at: str | None = None
    srs_completed: bool = False
    dictation_completed: bool = False


class DailyChallengePhaseResponse(BaseModel):
    srs_completed: bool
    dictation_completed: bool
    completed: bool
    completed_at: str | None = None


class ThemePackQuest(BaseModel):
    slug: str
    category: str
    emoji: str
    title: str
    badge_type: str
    total_words: int
    started_words: int
    strong_words: int
    progress_percent: float
    completed: bool


class MilestoneQuest(BaseModel):
    tier: str
    label: str
    badge_type: str
    current: int
    target: int
    earned: bool
    progress_percent: float


class QuestStrengthSummary(BaseModel):
    bank_total: int
    released: int
    learning: int
    familiar: int
    mastered: int


class LevelQuest(BaseModel):
    level: str
    is_current: bool
    bank_total: int
    released: int
    learning: int
    familiar: int
    mastered: int
    readiness_score: float
    milestones: list[MilestoneQuest]


class QuestsSummaryResponse(BaseModel):
    english_level: str
    overall: QuestStrengthSummary
    levels: list[LevelQuest]
    packs: list[ThemePackQuest]
    packs_by_level: dict[str, list[ThemePackQuest]] = Field(default_factory=dict)
    earned_pack_badges: int
    earned_milestone_badges: int
    total_pack_quests: int
    completed_pack_quests: int
    newly_earned_badges: list[str] = Field(default_factory=list)


class LearnerWordItem(BaseModel):
    card_id: int
    word: str
    definition: str
    level: str | None = None
    levels: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    strength: str
    distinct_review_days: int = 0
    released_at: str | None = None
    interval_days: int = 0
    repetitions: int = 0
    state: str


class LearnerWordsResponse(BaseModel):
    items: list[LearnerWordItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    by_level: dict[str, int] = Field(default_factory=dict)
    by_bank_level: dict[str, int] = Field(default_factory=dict)
    by_book: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_strength: dict[str, int] = Field(default_factory=dict)
