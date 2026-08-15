from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LearnerProfileResponse(BaseModel):
    id: int
    display_name: str
    age: int
    english_level: str
    ui_mode: str
    emoji: str
    avatar_url: str | None
    daily_practice_goal: int


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    learner: LearnerProfileResponse | None = None


class LoginPickResponse(BaseModel):
    label: str
    emoji: str
    role: str
