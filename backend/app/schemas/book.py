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


class SuspiciousLemma(BaseModel):
    id: int
    lemma: str
    frequency: int
    rank: int
    in_study_set: bool
    is_hidden: bool
    reason: str


class SuspiciousLemmaListResponse(BaseModel):
    items: list[SuspiciousLemma]
    total: int


class BookLemmaBulkHideRequest(BaseModel):
    lemma_ids: list[int] = Field(min_length=1)
    hidden: bool = True


class BookDefinitionsSummary(BaseModel):
    needs_refresh_count: int
    missing_en_count: int
    missing_zh_count: int


class DefinitionFillJobResponse(BaseModel):
    id: int
    status: str
    total: int
    processed: int
    filled: int
    failed: int
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class PlaceholderLemma(BaseModel):
    id: int
    book_id: int
    book_title: str
    lemma: str
    frequency: int
    in_study_set: bool
    is_hidden: bool


class PlaceholderLemmaListResponse(BaseModel):
    items: list[PlaceholderLemma]
    total: int
