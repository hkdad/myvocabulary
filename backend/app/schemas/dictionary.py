from pydantic import BaseModel, Field


class DictionaryEntryResponse(BaseModel):
    id: int
    word: str
    phonetic: str | None
    part_of_speech: str | None
    definition: str
    definition_zh_hant: str | None = None
    example_sentence: str | None
    synonyms: list[str] = Field(default_factory=list)
    source: str
    audio_path: str | None = None
    has_audio: bool = False


class DictionarySearchResponse(BaseModel):
    results: list[DictionaryEntryResponse]
    query: str


class DictionarySuggestResponse(BaseModel):
    query: str
    suggestions: list[DictionaryEntryResponse]


class ManualWordCreateRequest(BaseModel):
    word: str = Field(min_length=1, max_length=128)
    definition: str = Field(min_length=1)
    phonetic: str | None = Field(default=None, max_length=128)
    part_of_speech: str | None = Field(default=None, max_length=64)
    example_sentence: str | None = None


class EnsureZhRequest(BaseModel):
    entry_ids: list[int] = Field(default_factory=list, max_length=20)


class EnsureZhItem(BaseModel):
    id: int
    definition_zh_hant: str


class EnsureZhResponse(BaseModel):
    items: list[EnsureZhItem] = Field(default_factory=list)


class ClearZhResponse(BaseModel):
    id: int
    definition_zh_hant: str | None = None
