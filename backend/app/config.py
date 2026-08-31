from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Database & Cache ---
    database_url: str  # e.g. postgresql+asyncpg://user:pass@localhost:5432/apip
    redis_url: str = "redis://localhost:6379/0"

    # --- Auth / JWT ---
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # --- Groq ---
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    # --- HuggingFace ---
    hf_api_key: str
    hf_embedding_model: str = "BAAI/bge-m3"

    # --- File Upload ---
    upload_dir: str = "uploads"
    max_file_size_mb: int = 50

    # --- Rate Limiting ---
    rate_limit_per_minute: int = 100
    rate_limit_per_day: int = 1000

    model_config = {"env_file": ".env", "extra": "ignore"}

    @field_validator("database_url", mode="after")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


settings = Settings()  # type: ignore[call-arg]

