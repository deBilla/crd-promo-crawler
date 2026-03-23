"""Crawler service configuration."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from shared.config import BaseServiceConfig


class CrawlerConfig(BaseServiceConfig):
    """Settings specific to the crawler service."""
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # Crawl behavior
    max_concurrent_requests: int = 5
    request_delay: float = 1.0  # Seconds between requests to same domain
    max_retries: int = 3
    timeout: float = 30.0
    max_response_size: int = 10_000_000  # 10MB — reject larger responses

    # User agent
    user_agent: str = "ContextCrawler/1.0 (Card Promotions Crawler)"

    # robots.txt
    respect_robots_txt: bool = True

    # Per-domain URL ceiling
    max_urls_per_domain: int = 500

    # Puppeteer sidecar for JS-rendered pages
    puppeteer_url: str = "http://localhost:3000"

    # Frontier queue
    frontier_queue_name: str = "frontier"
    parsing_queue_name: str = "parsing"
    pop_timeout: int = 5  # Seconds to wait before checking shutdown flag
