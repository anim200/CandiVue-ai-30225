"""All settings come from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic import Field, SecretStr
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

    # Login tokens (see app/auth). The secret signs every token, so anyone who
    # knows it could create tokens: required, long, and only in .env.
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = Field(default=480, gt=0)  # one working day

    # First interviewer account, created at startup when there is no user yet.
    demo_interviewer_email: str | None = None
    demo_interviewer_name: str = "Interviewer A"
    demo_interviewer_password: SecretStr | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
