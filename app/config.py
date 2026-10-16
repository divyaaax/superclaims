"""Application Configuration Module

Uses Pydantic Settings to load configuration from environment variables
or a local .env file.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings."""

    # Project metadata
    app_name: str = "Claim Processing Pipeline"
    app_version: str = "1.0.0"
    app_description: str = (
        "FastAPI service for PDF claim document segregation and multi-agent extraction using LangGraph."
    )

    # LLM Settings
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    use_mock_llm: bool = True

    # Document & Processing Constraints
    max_file_size_mb: int = 25
    batch_size: int = 5
    log_level: str = "INFO"

    @property
    def max_file_size_bytes(self) -> int:
        """Calculate max file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
