from datetime import date, datetime

from pydantic import BaseModel, Field


class DictionaryEntrySummary(BaseModel):
    id: int
    word: str
    definition: str
    definition_zh_hant: str | None = None
    part_of_speech: str | None
    phonetic: str | None = None
    has_audio: bool = False


class WordListItemResponse(BaseModel):
    id: int
    sort_order: int
    notes: str | None
    dictionary_entry: DictionaryEntrySummary


class WordListSummary(BaseModel):
    id: int
    name: str
    description: str | None
    level_tag: str | None
    source: str
    source_url: str | None
    is_active: bool
    item_count: int
    assigned_learner_ids: list[int] = Field(default_factory=list)
    created_by_learner_id: int | None = None
    created_at: datetime
    updated_at: datetime


class WordListDetailResponse(WordListSummary):
    items: list[WordListItemResponse]


class WordListCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    level_tag: str | None = Field(default=None, max_length=8)


class WordListUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    level_tag: str | None = Field(default=None, max_length=8)
    is_active: bool | None = None


class WordListItemCreateRequest(BaseModel):
    word: str = Field(min_length=1, max_length=128)
    notes: str | None = None
    sort_order: int | None = None


class WordListAssignRequest(BaseModel):
    learner_ids: list[int] = Field(min_length=1)
    due_date: date | None = None


class AssignmentResponse(BaseModel):
    id: int
    word_list_id: int
    learner_id: int
    assigned_at: datetime
    due_date: date | None
    is_active: bool


class AssignmentsResponse(BaseModel):
    assignments: list[AssignmentResponse]


class CatalogResponse(BaseModel):
    level: str | None
    lists: list[WordListSummary]


class AssignedListSummary(WordListSummary):
    due_date: date | None = None


class AssignedListsResponse(BaseModel):
    lists: list[AssignedListSummary]
