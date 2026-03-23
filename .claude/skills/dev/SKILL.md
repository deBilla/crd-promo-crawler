---
name: dev
description: >
  Development skill for the Card Promotions Data Crawler — a Docker Compose-based system that crawls bank
  websites for credit card deals using a frontier queue, parser service, LLM relevance filtering, and a
  structured extraction pipeline. Use this skill whenever you need to write new code, add features, implement
  services, extend functionality, or work on any component of the crawler system. Trigger on: writing crawler
  logic, queue handling, parser service code, LLM integration, extraction pipeline, API endpoints, storage
  backends, Puppeteer integration, Docker Compose config, or any feature development. Even if the user just
  says "add X" or "implement Y" in the context of the crawler project, use this skill.
---

# Card Promotions Crawler — Development Skill

You are developing the **Card Promotions Data Crawler**, a system that crawls bank websites, identifies
pages containing credit card promotion content, extracts structured deal data using an LLM, and serves
it through an API to a web app. The system runs locally via Docker Compose.

## System Architecture Overview

```
┌─────────────┐     ┌──────────────────┐     ┌────────────┐
│  Seed URLs   │────▶│  Frontier Queue   │────▶│  Crawler   │
└─────────────┘     │  (Redis)          │     │  Service   │
                    └──────────────────┘     └─────┬──────┘
                           ▲                       │
                           │                       │ fetch HTML
                           │                       ▼
                           │                 ┌────────────┐
                           │                 │   MinIO     │ (store raw HTML)
                           │                 │   Blob      │
                           │                 └─────┬──────┘
                           │                       │
                           │                       ▼
                           │                 ┌────────────┐
                           │   new URLs      │  Postgres   │ (URLMetadata)
                           │◀────────────────│             │
                           │                 └─────┬──────┘
                           │                       │
                           │                       ▼
                           │                 ┌────────────────┐
                           │                 │ Parsing Queue   │ {url, minioPath}
                           │                 │ (Redis)         │
                           │                 └───────┬────────┘
                           │                         │
                           │                         ▼
                           │                 ┌────────────────┐
                           │   extracted     │ Parser Service  │
                           │◀── URLs ────────│ + LLM filter    │
                           │                 └───────┬────────┘
                           │                         │ relevant pages
                           │                         ▼
                           │                 ┌────────────────────────┐
                           │                 │ Card Promotion         │
                           │                 │ Extraction Service     │
                           │                 │ (LLM structured       │
                           │                 │  extraction)           │
                           │                 └───────┬────────────────┘
                           │                         │
                           │                         ▼
                           │                 ┌────────────┐     ┌─────────┐
                           │                 │ Deals DB   │────▶│  API    │──▶ Web App
                           │                 │ (Postgres) │     └─────────┘
                           │                 └────────────┘
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Orchestration | Docker Compose | Local dev & deployment |
| Crawler Service | Python 3.11+ / asyncio / httpx | HTTP fetching, rate limiting |
| Parser Service | Python 3.11+ / BeautifulSoup4 + lxml | HTML parsing, link extraction |
| Dynamic Pages | Puppeteer (Node.js sidecar) or Playwright | JS-rendered bank pages |
| Frontier Queue | Redis (lists or streams) | URL queue with dedup |
| Parsing Queue | Redis (lists or streams) | Crawler→Parser handoff |
| Rate Limiting | Redis (sliding window) | Per-domain throttling |
| DNS Cache | Redis (key-value with TTL) | Avoid redundant DNS lookups |
| Blob Storage | MinIO (S3-compatible) | Raw HTML page archive |
| Metadata DB | PostgreSQL | URL metadata, crawl state |
| Deals DB | PostgreSQL (same instance) | Extracted credit card deals |
| LLM Interface | OpenAI API / local model | Relevance filtering + extraction |
| API | FastAPI | Serve deals to web app |
| Web App | TBD (React / Next.js) | Display deals to users |
| Config/Settings | Pydantic v2 + pydantic-settings | Typed configuration |

## Project Structure

```
crd-promo-crawler/
├── docker-compose.yml
├── .env                          # Shared env vars (DB creds, Redis URL, MinIO keys)
├── .env.example
├── pyproject.toml                # Monorepo or per-service
├── skills/                       # Development skills (this file lives here)
│
├── services/
│   ├── crawler/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── crawler/
│   │   │   ├── __init__.py
│   │   │   ├── main.py           # Entry point — consume from frontier queue
│   │   │   ├── config.py         # CrawlerConfig (Pydantic settings)
│   │   │   ├── fetcher.py        # httpx-based page fetcher
│   │   │   ├── rate_limiter.py   # Redis-backed per-domain rate limiter
│   │   │   ├── dns_cache.py      # Redis-backed DNS cache
│   │   │   ├── robots.py         # robots.txt fetching & compliance
│   │   │   ├── storage.py        # MinIO upload (store raw HTML)
│   │   │   ├── dedup.py          # URL deduplication (Redis set)
│   │   │   └── models.py         # Pydantic models (URLMetadata, FetchResult)
│   │   └── tests/
│   │
│   ├── parser/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── parser/
│   │   │   ├── __init__.py
│   │   │   ├── main.py           # Entry point — consume from parsing queue
│   │   │   ├── config.py
│   │   │   ├── html_parser.py    # BS4/lxml text + link extraction
│   │   │   ├── link_extractor.py # URL extraction, normalization, filtering
│   │   │   ├── relevance.py      # LLM-based relevance check (is this a promo page?)
│   │   │   ├── puppeteer.py      # Client for Puppeteer sidecar (dynamic pages)
│   │   │   └── models.py
│   │   └── tests/
│   │
│   ├── extractor/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── extractor/
│   │   │   ├── __init__.py
│   │   │   ├── main.py           # Entry point — consume relevant pages
│   │   │   ├── config.py
│   │   │   ├── llm_client.py     # LLM interface for structured extraction
│   │   │   ├── prompts.py        # Extraction prompt templates
│   │   │   ├── schemas.py        # Pydantic models for extracted deals
│   │   │   └── store.py          # Write deals to Postgres
│   │   └── tests/
│   │
│   ├── api/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── main.py           # FastAPI app
│   │   │   ├── routes/
│   │   │   │   ├── deals.py      # GET /deals, GET /deals/{id}, search
│   │   │   │   └── health.py     # Health checks
│   │   │   ├── schemas.py        # API response models
│   │   │   └── db.py             # Database connection
│   │   └── tests/
│   │
│   └── puppeteer/
│       ├── Dockerfile
│       ├── package.json
│       └── server.js             # HTTP API that renders pages via Puppeteer
│
├── shared/
│   ├── pyproject.toml
│   └── shared/
│       ├── __init__.py
│       ├── queue.py              # Redis queue abstraction (frontier + parsing)
│       ├── db.py                 # SQLAlchemy/asyncpg Postgres connection
│       ├── minio_client.py       # MinIO upload/download helpers
│       ├── redis_client.py       # Redis connection factory
│       ├── models.py             # Shared Pydantic models (URLMetadata, etc.)
│       └── config.py             # Base config shared across services
│
├── migrations/
│   └── alembic/                  # Database migrations
│
└── webapp/                       # Frontend (TBD)
```

## Docker Compose Layout

```yaml
# docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: ["redis-data:/data"]

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: crawler
      POSTGRES_USER: crawler
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports: ["5432:5432"]
    volumes: ["pg-data:/var/lib/postgresql/data"]

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    ports:
      - "9000:9000"   # API
      - "9001:9001"   # Console
    volumes: ["minio-data:/data"]

  crawler:
    build: ./services/crawler
    depends_on: [redis, postgres, minio]
    environment:
      REDIS_URL: redis://redis:6379
      DATABASE_URL: postgresql+asyncpg://crawler:${POSTGRES_PASSWORD}@postgres:5432/crawler
      MINIO_ENDPOINT: minio:9000
      MINIO_ACCESS_KEY: ${MINIO_ROOT_USER}
      MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD}
    restart: unless-stopped

  parser:
    build: ./services/parser
    depends_on: [redis, postgres, minio, puppeteer]
    environment:
      REDIS_URL: redis://redis:6379
      DATABASE_URL: postgresql+asyncpg://crawler:${POSTGRES_PASSWORD}@postgres:5432/crawler
      MINIO_ENDPOINT: minio:9000
      PUPPETEER_URL: http://puppeteer:3000
      LLM_API_KEY: ${LLM_API_KEY}
    restart: unless-stopped

  extractor:
    build: ./services/extractor
    depends_on: [redis, postgres]
    environment:
      REDIS_URL: redis://redis:6379
      DATABASE_URL: postgresql+asyncpg://crawler:${POSTGRES_PASSWORD}@postgres:5432/crawler
      LLM_API_KEY: ${LLM_API_KEY}
    restart: unless-stopped

  puppeteer:
    build: ./services/puppeteer
    ports: ["3000:3000"]

  api:
    build: ./services/api
    depends_on: [postgres]
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://crawler:${POSTGRES_PASSWORD}@postgres:5432/crawler

volumes:
  redis-data:
  pg-data:
  minio-data:
```

## Core Data Models

These live in `shared/models.py` and are used across services:

```python
"""Shared data models for the Card Promotions Crawler."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class CrawlStatus(StrEnum):
    QUEUED = "queued"
    FETCHING = "fetching"
    FETCHED = "fetched"
    PARSING = "parsing"
    PARSED = "parsed"
    RELEVANT = "relevant"       # LLM confirmed it's a promo page
    IRRELEVANT = "irrelevant"   # LLM said not a promo page
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    FAILED = "failed"
    DEAD = "dead"               # Max retries exceeded


class URLMetadata(BaseModel):
    """Tracks the lifecycle of every URL through the pipeline."""
    id: int | None = None
    url: str
    domain: str
    file_path: str | None = None      # MinIO object path
    status: CrawlStatus = CrawlStatus.QUEUED
    status_code: int | None = None
    content_hash: str | None = None   # For duplicate content detection
    depth: int = 0                    # Hops from seed URL
    retry_count: int = 0
    is_seed: bool = False
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    fetched_at: datetime | None = None
    parsed_at: datetime | None = None
    error_message: str | None = None


class FrontierItem(BaseModel):
    """An item in the frontier queue."""
    url: str
    depth: int = 0
    priority: int = 0            # Higher = crawl sooner
    source_url: str | None = None  # Page where this URL was found


class ParsingQueueItem(BaseModel):
    """Handoff from crawler to parser."""
    url: str
    minio_path: str              # Where the raw HTML is stored
    depth: int = 0


class ExtractionQueueItem(BaseModel):
    """Handoff from parser to extractor — only relevant pages."""
    url: str
    minio_path: str
    text_content: str            # Extracted text from the page
    page_title: str = ""


class CreditCardDeal(BaseModel):
    """A structured credit card promotion extracted by the LLM."""
    id: int | None = None
    source_url: str
    bank_name: str
    card_name: str | None = None
    promotion_title: str
    description: str
    discount_percentage: float | None = None
    discount_amount: float | None = None
    merchant_name: str | None = None
    merchant_category: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    terms_and_conditions: str | None = None
    raw_text: str                # Original text the deal was extracted from
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    confidence_score: float = 0.0  # LLM's confidence in the extraction
```

## Redis Queue Abstraction

Both the frontier queue and parsing queue use the same Redis abstraction:

```python
"""Redis-backed queue for inter-service communication."""

from __future__ import annotations

import json
import logging
from typing import TypeVar, Type

import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class RedisQueue:
    """A simple Redis-backed FIFO queue with Pydantic serialization.

    Uses LPUSH/BRPOP for reliable FIFO ordering. For priority support,
    use a Redis sorted set (ZADD/BZPOPMIN) instead.
    """

    def __init__(self, redis_client: redis.Redis, queue_name: str) -> None:
        self.redis = redis_client
        self.queue_name = queue_name

    async def push(self, item: BaseModel) -> None:
        """Add an item to the queue."""
        await self.redis.lpush(self.queue_name, item.model_dump_json())

    async def pop(self, model_class: Type[T], timeout: int = 0) -> T | None:
        """Pop an item from the queue. Blocks for `timeout` seconds (0 = forever)."""
        result = await self.redis.brpop(self.queue_name, timeout=timeout)
        if result is None:
            return None
        _, data = result
        return model_class.model_validate_json(data)

    async def size(self) -> int:
        return await self.redis.llen(self.queue_name)

    async def clear(self) -> None:
        await self.redis.delete(self.queue_name)
```

## URL Deduplication

```python
"""Redis-backed URL deduplication using a set."""

from __future__ import annotations
import hashlib
import redis.asyncio as redis


class URLDedup:
    """Check and track seen URLs to prevent re-crawling.

    Uses a Redis set. For very large crawls (millions of URLs),
    consider switching to a Redis Bloom filter (RedisBloom module).
    """

    def __init__(self, redis_client: redis.Redis, key: str = "seen_urls") -> None:
        self.redis = redis_client
        self.key = key

    def _normalize(self, url: str) -> str:
        """Normalize URL for dedup: lowercase, strip fragment, sort params."""
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
        parsed = urlparse(url.lower())
        params = parse_qs(parsed.query)
        sorted_query = urlencode(sorted(params.items()), doseq=True)
        normalized = parsed._replace(fragment="", query=sorted_query)
        return urlunparse(normalized)

    def _hash(self, url: str) -> str:
        return hashlib.sha256(self._normalize(url).encode()).hexdigest()

    async def is_seen(self, url: str) -> bool:
        return await self.redis.sismember(self.key, self._hash(url))

    async def mark_seen(self, url: str) -> bool:
        """Mark URL as seen. Returns True if it was new, False if already seen."""
        result = await self.redis.sadd(self.key, self._hash(url))
        return result == 1

    async def count(self) -> int:
        return await self.redis.scard(self.key)
```

## Service Entry Point Pattern

Each service follows the same main loop pattern:

```python
"""Crawler service entry point."""

import asyncio
import logging
import signal

from crawler.config import CrawlerConfig
from shared.queue import RedisQueue
from shared.redis_client import create_redis
from shared.minio_client import create_minio

logger = logging.getLogger(__name__)


async def main() -> None:
    config = CrawlerConfig()
    redis_client = await create_redis(config.redis_url)
    minio_client = create_minio(config.minio_endpoint, config.minio_access_key, config.minio_secret_key)

    frontier_queue = RedisQueue(redis_client, "frontier")
    parsing_queue = RedisQueue(redis_client, "parsing")

    # Graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_signal(sig):
        logger.info("Received %s, shutting down gracefully...", sig.name)
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal, sig)

    logger.info("Crawler service started, waiting for URLs...")

    while not shutdown_event.is_set():
        item = await frontier_queue.pop(FrontierItem, timeout=5)
        if item is None:
            continue  # Timeout, check shutdown flag and retry

        try:
            result = await fetch_page(item, config, minio_client)
            await update_metadata(result, db)
            await parsing_queue.push(ParsingQueueItem(
                url=item.url,
                minio_path=result.minio_path,
                depth=item.depth,
            ))
        except Exception as e:
            logger.error("Failed to process %s: %s", item.url, e)
            await handle_retry(item, e, frontier_queue, db)

    await redis_client.aclose()
    logger.info("Crawler service stopped.")


if __name__ == "__main__":
    asyncio.run(main())
```

## Coding Conventions

### Style
- `ruff` for linting and formatting, line length 100, double quotes
- Complete type annotations on all public functions
- Pydantic models for all data crossing service boundaries (never raw dicts)

### Async
- `asyncio` everywhere — all services are async
- `httpx.AsyncClient` for HTTP (reuse across requests, don't create per-request)
- `redis.asyncio` for Redis
- `asyncpg` (via SQLAlchemy async or raw) for Postgres
- `miniopy-async` or `aioboto3` for MinIO

### Error Handling
- Custom exceptions per service (e.g., `FetchError`, `ParseError`, `ExtractionError`)
- Never silently swallow — log with context, then decide: retry, skip, or dead-letter
- All network calls must have timeouts

### Configuration
- Pydantic Settings with `env_prefix` per service
- All config via environment variables (Docker Compose `.env` file)
- No hardcoded URLs, credentials, or magic numbers

### Commit Messages
- Conventional commits: `feat(crawler): add per-domain rate limiting`
- Prefixes: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `infra`

## Quick Reference

Read `references/component_template.md` for a copy-paste service template.
Read `references/httpx_patterns.md` for HTTP client patterns.
Read `references/llm_integration.md` for LLM prompt patterns and the relevance/extraction interface.
