"""Parser service configuration."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from shared.config import BaseServiceConfig, LLMConfig


class ParserConfig(BaseServiceConfig, LLMConfig):
    """Configuration for the Parser service."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # Queue names (must match the crawler's output queue names)
    parsing_queue_name: str = "parsing"
    frontier_queue_name: str = "frontier"
    extraction_queue_name: str = "extraction"

    # Puppeteer sidecar
    puppeteer_url: str = "http://puppeteer:3000"

    # Queue pop timeout
    pop_timeout: int = 5

    # Max crawl depth for discovered links
    max_depth: int = 3
