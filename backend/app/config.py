from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://ceis:ceis@localhost:5432/ceis"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    retrieval_top_k: int = 10
    cors_origins: list[str] = ["http://localhost:5173"]  # Vite dev server


settings = Settings()
