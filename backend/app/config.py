from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Database ---
    database_url: str  # e.g. postgresql+asyncpg://user:pass@localhost:5432/apip

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


settings = Settings()  # type: ignore[call-arg]
