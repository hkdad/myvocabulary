from pydantic import BaseModel, Field


class LearnerCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    age: int = Field(ge=4, le=18)
    english_level: str = Field(min_length=2, max_length=8)
    ui_mode: str | None = Field(default=None, pattern="^(kid|teen)$")
    emoji: str | None = Field(default=None, min_length=1, max_length=16)
    daily_new_word_goal: int | None = Field(default=None, ge=1, le=30)
    daily_learning_retention_mix: int | None = Field(default=None, ge=0, le=10)
    daily_mastered_retention_mix: int | None = Field(default=None, ge=0, le=10)


class LearnerUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    age: int | None = Field(default=None, ge=4, le=18)
    english_level: str | None = Field(default=None, min_length=2, max_length=8)
    ui_mode: str | None = Field(default=None, pattern="^(kid|teen)$")
    emoji: str | None = Field(default=None, min_length=1, max_length=16)
    daily_new_word_goal: int | None = Field(default=None, ge=1, le=30)
    daily_learning_retention_mix: int | None = Field(default=None, ge=0, le=10)
    daily_mastered_retention_mix: int | None = Field(default=None, ge=0, le=10)
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=6, max_length=128)


class LearnerResponse(BaseModel):
    id: int
    user_id: int
    username: str
    display_name: str
    age: int
    english_level: str
    ui_mode: str
    emoji: str
    avatar_url: str | None
    daily_practice_goal: int
    daily_new_word_goal: int
    daily_learning_retention_mix: int
    daily_mastered_retention_mix: int
    is_active: bool
