from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-me-in-development"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite+aiosqlite:///../data/myvocabulary.db"
    secret_key: str = DEFAULT_SECRET_KEY
    access_token_expire_minutes: int = 15
    refresh_token_expire_days_learner: int = 30
    refresh_token_expire_days_parent: int = 7
    audio_dir: Path = Path("./data/audio")
    dictionary_api_url: str = "https://api.dictionaryapi.dev/api/v2/entries/en"
    dictionary_fallback_api_url: str = "https://api.suvankar.cc/dictionaryapi/v1/definitions/en"
    tts_voice: str = "en-US-JennyNeural"
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    )
    debug: bool = True
    openai_api_key: str | None = None
    openai_api_base: str = "https://opencode.ai/zen/go/v1"
    openai_model: str = "mimo-v2.5"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    def validate_production(self) -> None:
        if not self.is_production:
            return
        if self.secret_key == DEFAULT_SECRET_KEY:
            raise RuntimeError("SECRET_KEY must be set to a random value when APP_ENV=production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
