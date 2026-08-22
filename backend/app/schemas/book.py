from pydantic import BaseModel, Field


class BookLemmaSample(BaseModel):
    id: int
    lemma: str
    frequency: int
    rank: int
    in_study_set: bool
    is_hidden: bool
    matched_baseline: bool


class BookProgress(BaseModel):
    learner_id: int
    study_known: int
    study_total: int
    study_progress_percent: float
    page_known: int
    content_total: int
    page_coverage_percent: float
    ready_to_read: bool
    days_estimate: int = 0
    learning_count: int = 0
    familiar_count: int = 0
    mastered_count: int = 0


class BookSummary(BaseModel):
    id: int
    title: str
    title_source: str = "filename"
    title_needs_review: bool = False
    original_filename: str
    status: str
    coverage_target: float
    token_count: int
    unique_lemma_count: int
    content_lemma_count: int
    study_lemma_count: int
    skipped_function_words: int
    skipped_proper_nouns: int
    coverage_curve: dict[str, int]
    days_at_five_new: int
    word_list_id: int | None
    assigned_learner_ids: list[int] = Field(default_factory=list)
    analysis_engine: str
    confirmed_at: str | None = None
    created_at: str | None = None
    baseline_match_count: int = 0
    new_word_count: int = 0
    sample_study: list[BookLemmaSample] = Field(default_factory=list)
    sample_advanced: list[BookLemmaSample] = Field(default_factory=list)


class BookListResponse(BaseModel):
    books: list[BookSummary]


class BookConfirmRequest(BaseModel):
    coverage_target: float | None = None
    title: str | None = None


class BookUpdateRequest(BaseModel):
    title: str


class BookAssignRequest(BaseModel):
    learner_id: int


class BookLemmaHideRequest(BaseModel):
    hidden: bool = True
