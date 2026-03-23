"""Extractor service configuration."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from shared.config import BaseServiceConfig, LLMConfig


class ExtractorConfig(BaseServiceConfig, LLMConfig):
    """Configuration for the credit card deal extractor service."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    extraction_queue_name: str = "extraction"
    pop_timeout: int = 5
    max_content_chars: int = 8000
