"""All settings come from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str  # required: the app will not start without it
    cors_origins: str = "http://localhost:5173"

    # AI model (see app/ai/llm.py). SecretStr hides the key in logs and errors.
    llm_provider: str = "google_genai"
    llm_model: str = "gemini-2.5-flash"
    llm_api_key: SecretStr | None = None
    llm_timeout_seconds: float = 60
    llm_max_retries: int = 2
    # 0 = least random: the same CV and job profile get the same score (F2, B2).
    llm_temperature: float = 0

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
