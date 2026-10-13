"""All settings come from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All app settings, read from environment variables (.env)."""

    app_env: str = "development"
    log_level: str = "INFO"
    # Local time zone for application deadlines and interview times.
    app_timezone: str = "Asia/Dhaka"
    database_url: str  # required: the app will not start without it
    cors_origins: str = "http://localhost:5173"

    # AI model (see app/ai/llm.py). SecretStr hides the key in logs and errors.
    llm_provider: str = "google_genai"
    llm_model: str = "gemini-3.5-flash-lite"  # used until the interviewer picks one
    # Models the interviewer may pick under the chat (comma-separated).
    llm_models: str = "gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    llm_api_key: SecretStr | None = None
    llm_timeout_seconds: float = 60
    llm_max_retries: int = 2
    # 0 = least random: the same CV and job profile get the same score (F2, B2).
    llm_temperature: float = 0

    # Embedding model for the knowledge base (see app/ai/embeddings.py).
    # Default: a local Ollama model in Docker, so document text stays on this
    # machine. "google_genai" uses Gemini with the LLM key instead.
    embedding_provider: str = "ollama"
    embedding_model: str = "qwen3-embedding:0.6b"
    ollama_base_url: str = "http://ollama:11434"  # the ollama service in Compose

    # Local model for CV screening (app/screening/local_model.py): reads the
    # years when a CV has no readable job dates, and checks a missing
    # mandatory requirement once more before a candidate is excluded.
    screening_model: str = "qwen3:4b-instruct"
    screening_model_timeout_seconds: float = Field(default=300, gt=0)

    # Job board MCP server (jobboard-mcp container, Blogger). The Blogger
    # credentials live only in that container, never in the backend.
    jobboard_mcp_url: str = "http://jobboard-mcp:8001/mcp"

    # Email MCP server (email-mcp container): interview invitations. The
    # email login lives only in that container.
    email_mcp_url: str = "http://email-mcp:8002/mcp"
    # Where candidates open their private interview link (this app's address).
    app_public_url: str = "http://localhost:5173"

    # Calendar MCP server (calendar-mcp container): the interviewer's Google
    # Calendar. The Google sign-in lives only in that container.
    calendar_mcp_url: str = "http://calendar-mcp:8003/mcp"

    # Video calls (F3): the LiveKit server in Docker. The key and secret sign
    # each room "ticket" (only this backend can make them) and LiveKit's
    # webhooks. Empty secret: calls show "not set up".
    livekit_url: str = "http://livekit:7880"
    livekit_api_key: str = "candivue"
    livekit_api_secret: SecretStr | None = None

    # Live transcript (F4): the transcriber container streams each speaker's
    # audio to Deepgram. Only that container gets the key. Empty: the room
    # says "speech-to-text is not set up".
    deepgram_api_key: SecretStr | None = None
    deepgram_model: str = "nova-3"
    deepgram_language: str = "en"

    # CV Collector (app/collector, cv-collector container). The Google key is
    # given only to that container (read-only service account, N7).
    google_service_account_key: SecretStr | None = None  # JSON or base64 JSON
    cv_responses_sheet_id: str | None = None  # the Google Form's response Sheet
    cv_collect_interval_seconds: int = Field(default=300, ge=30)
    cv_intake_dir: str = "/data/cv_intake"  # Docker named volume, never in git
    max_cv_mb: int = Field(default=10, gt=0)
    # The form question "Position applied for", e.g. "entry.123456789": the job
    # post pre-fills it with "JOB-12 · title" so each CV finds its job.
    google_form_position_field: str | None = None

    # Largest document the knowledge base accepts (N8).
    max_upload_mb: int = Field(default=20, gt=0)

    # Login tokens (see app/auth). The secret signs every token, so anyone who
    # knows it could create tokens: required, long, and only in .env.
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = Field(default=480, gt=0)  # one working day

    # First interviewer account, created at startup when there is no user yet.
    demo_interviewer_email: str | None = None
    demo_interviewer_name: str = "Interviewer A"
    demo_interviewer_password: SecretStr | None = None

    @field_validator(
        "llm_api_key",
        "livekit_api_secret",
        "deepgram_api_key",
        "google_service_account_key",
        "demo_interviewer_password",
        mode="before",
    )
    @classmethod
    def empty_secret_is_unset(cls, value):
        """An empty value (e.g. "DEEPGRAM_API_KEY=" in .env, which Docker
        passes as "") means the secret is not set."""
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def llm_model_list(self) -> list[str]:
        """The models that may be chosen; the default model is always one."""
        names = [name.strip() for name in self.llm_models.split(",") if name.strip()]
        return names if self.llm_model in names else [self.llm_model, *names]

    @property
    def cors_origin_list(self) -> list[str]:
        """Turn the comma-separated CORS_ORIGINS text into a list."""
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    """Return the settings, created once and then reused."""
    return Settings()
