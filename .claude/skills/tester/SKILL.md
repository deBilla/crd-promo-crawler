---
name: tester
description: >
  Testing skill for the Card Promotions Data Crawler — covers unit tests, integration tests, and
  end-to-end tests for a multi-service Docker Compose system with Redis queues, MinIO blob storage,
  Postgres, LLM integration, and Puppeteer. Use this skill whenever you need to write tests, create
  test fixtures, mock HTTP responses, mock LLM calls, set up test infrastructure, test queue behavior,
  test Docker Compose services, debug failing tests, or improve coverage. Trigger on: "write tests",
  "add tests for", "test this", "fix failing test", "mock", "pytest", "test coverage", "integration test",
  or any testing-related work. If the user says "make sure this works" or "verify this", use this skill too.
---

# Card Promotions Crawler — Testing Skill

You are writing tests for the **Card Promotions Data Crawler**, a multi-service system running on
Docker Compose with Redis queues, MinIO, Postgres, LLM-based filtering, and Puppeteer. This skill
guides you through testing each service and the system as a whole.

## Testing Philosophy

This system has multiple services communicating through Redis queues and shared storage. That means
there are three distinct testing scopes:

1. **Unit tests** — Test individual functions and classes within a service, mocking all external
   dependencies (Redis, Postgres, MinIO, LLM, HTTP). Fast, run on every commit.
2. **Integration tests** — Test a service end-to-end with real Redis, Postgres, and MinIO (via
   Docker Compose test profile or testcontainers). Slower, run before merge.
3. **E2E tests** — Start all services, seed the frontier queue, and verify deals appear in the
   database. Slowest, run in CI or manually.

Every test should answer one question clearly: "does this specific behavior work correctly?"

## Tech Stack

- **pytest** + **pytest-asyncio** — async test runner
- **httpx.MockTransport** — mock HTTP responses for crawled pages
- **fakeredis[aioredis]** — in-memory Redis for unit tests (no real Redis needed)
- **pytest-docker** or **testcontainers-python** — spin up real services for integration tests
- **factory-boy** — generate test data (URLMetadata, CreditCardDeal, etc.)
- **pytest-cov** — coverage reporting
- **respx** (optional) — higher-level httpx mocking

## Test Directory Structure

Each service has its own `tests/` directory:

```
services/
├── crawler/
│   └── tests/
│       ├── conftest.py                # Crawler-specific fixtures
│       ├── unit/
│       │   ├── test_fetcher.py        # HTTP fetching logic
│       │   ├── test_rate_limiter.py   # Per-domain rate limiting
│       │   ├── test_dns_cache.py      # DNS caching in Redis
│       │   ├── test_robots.py         # robots.txt compliance
│       │   ├── test_dedup.py          # URL deduplication
│       │   └── test_storage.py        # MinIO upload/download
│       └── integration/
│           └── test_crawl_loop.py     # Full fetch→store→queue cycle
│
├── parser/
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       │   ├── test_html_parser.py    # Text extraction from HTML
│       │   ├── test_link_extractor.py # URL extraction and normalization
│       │   ├── test_relevance.py      # LLM relevance check (mocked LLM)
│       │   └── test_puppeteer.py      # Puppeteer client (mocked sidecar)
│       └── integration/
│           └── test_parse_loop.py     # Full consume→parse→classify→enqueue cycle
│
├── extractor/
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       │   ├── test_llm_extraction.py # Deal extraction (mocked LLM)
│       │   ├── test_prompts.py        # Prompt formatting
│       │   └── test_store.py          # Writing deals to Postgres
│       └── integration/
│           └── test_extract_loop.py
│
├── api/
│   └── tests/
│       ├── conftest.py
│       ├── test_deals_endpoint.py     # GET /deals, search, filtering
│       └── test_health.py
│
└── e2e/
    ├── conftest.py                    # Docker Compose setup for all services
    ├── test_full_crawl.py             # Seed URLs → deals in DB
    ├── test_fault_tolerance.py        # Kill a service, verify recovery
    └── fixtures/
        └── mock_bank_site/            # Static site served via httpbin or similar
```

Also a shared test utilities package:

```
shared/
└── tests/
    ├── test_queue.py                  # RedisQueue push/pop/size
    ├── test_dedup.py                  # URL deduplication
    └── test_models.py                 # Pydantic model validation
```

## Configuration: pyproject.toml (per service)

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: requires real Docker services",
    "e2e: end-to-end across all services",
    "slow: marks tests as slow",
]

[tool.coverage.run]
source = ["crawler"]  # or "parser", "extractor", "api"
branch = true

[tool.coverage.report]
fail_under = 80
```

## Core Fixtures

### Shared conftest.py (for unit tests using fakeredis)

```python
"""Shared fixtures for unit testing with mocked infrastructure."""

from __future__ import annotations

import pytest
import fakeredis.aioredis

from shared.queue import RedisQueue
from shared.models import URLMetadata, FrontierItem, CrawlStatus


@pytest.fixture
async def fake_redis():
    """In-memory Redis for unit tests — no real Redis needed."""
    server = fakeredis.FakeServer()
    client = fakeredis.aioredis.FakeRedis(server=server)
    yield client
    await client.aclose()


@pytest.fixture
async def frontier_queue(fake_redis):
    return RedisQueue(fake_redis, "frontier")


@pytest.fixture
async def parsing_queue(fake_redis):
    return RedisQueue(fake_redis, "parsing")


@pytest.fixture
def sample_url_metadata() -> URLMetadata:
    return URLMetadata(
        url="https://bank.example.com/promotions/dining",
        domain="bank.example.com",
        status=CrawlStatus.QUEUED,
        depth=1,
        is_seed=False,
    )


@pytest.fixture
def sample_frontier_item() -> FrontierItem:
    return FrontierItem(
        url="https://bank.example.com/promotions",
        depth=0,
        priority=10,
    )
```

### HTTP Mocking for Crawled Pages

```python
import httpx

def make_bank_page(
    body: str,
    status: int = 200,
    url: str = "https://bank.example.com/promotions",
    content_type: str = "text/html; charset=utf-8",
) -> httpx.Response:
    return httpx.Response(
        status,
        content=body.encode("utf-8"),
        headers={"content-type": content_type},
        request=httpx.Request("GET", url),
    )


@pytest.fixture
def mock_bank_transport():
    """Mock transport simulating a bank website with promotion pages."""
    pages = {
        "/promotions": """
            <html><head><title>Credit Card Promotions</title></head>
            <body>
                <h1>Current Promotions</h1>
                <a href="/promotions/dining">Dining Deals</a>
                <a href="/promotions/travel">Travel Offers</a>
                <a href="/about">About Us</a>
                <a href="/careers">Careers</a>
            </body></html>
        """,
        "/promotions/dining": """
            <html><head><title>Dining Promotions</title></head>
            <body>
                <h1>Dining Promotions</h1>
                <div class="deal">
                    <h2>20% off at Selected Restaurants</h2>
                    <p>Use your Platinum Visa to enjoy 20% off dining
                       at over 100 partner restaurants.</p>
                    <p>Valid until: 31 Dec 2026</p>
                    <p>Min spend: $50. Max discount: $30 per transaction.</p>
                </div>
            </body></html>
        """,
        "/about": """
            <html><head><title>About Our Bank</title></head>
            <body><h1>About Us</h1><p>We are a bank.</p></body></html>
        """,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in pages:
            return make_bank_page(pages[path], url=str(request.url))
        return httpx.Response(404, request=request)

    return httpx.MockTransport(handler)
```

### LLM Mock

```python
@pytest.fixture
def mock_llm_client():
    """Mock LLM that returns canned responses for testing."""

    class MockLLM:
        def __init__(self):
            self.calls: list[str] = []  # Track prompts for assertions

        async def complete(self, prompt: str, max_tokens: int = 1000) -> str:
            self.calls.append(prompt)

            # Relevance check responses
            if "is_relevant" in prompt:
                if "dining" in prompt.lower() or "promotion" in prompt.lower():
                    return '{"is_relevant": true, "confidence": 0.95, "reason": "Contains dining promotion"}'
                return '{"is_relevant": false, "confidence": 0.9, "reason": "General bank page"}'

            # Extraction responses
            if "bank_name" in prompt:
                return """[{
                    "bank_name": "Example Bank",
                    "card_name": "Platinum Visa",
                    "promotion_title": "20% off Dining",
                    "description": "20% off at selected restaurants",
                    "discount_percentage": 20.0,
                    "merchant_category": "dining",
                    "valid_until": "2026-12-31",
                    "terms_and_conditions": "Min spend $50, max discount $30"
                }]"""

            return "[]"

    return MockLLM()
```

## Test Patterns

### Pattern 1: Testing the Crawler Service (Fetcher)

```python
class TestFetcher:
    @pytest.mark.asyncio
    async def test_fetches_html_and_returns_content(self, mock_bank_transport):
        async with httpx.AsyncClient(transport=mock_bank_transport) as client:
            fetcher = PageFetcher(client=client, config=CrawlerConfig(request_delay=0))
            result = await fetcher.fetch("https://bank.example.com/promotions")
            assert result.status_code == 200
            assert "Credit Card Promotions" in result.content

    @pytest.mark.asyncio
    async def test_returns_error_on_404(self, mock_bank_transport):
        async with httpx.AsyncClient(transport=mock_bank_transport) as client:
            fetcher = PageFetcher(client=client, config=CrawlerConfig(request_delay=0))
            result = await fetcher.fetch("https://bank.example.com/nonexistent")
            assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_respects_timeout(self):
        async def slow_handler(request):
            import asyncio
            await asyncio.sleep(10)
            return httpx.Response(200)

        transport = httpx.MockTransport(slow_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            fetcher = PageFetcher(client=client, config=CrawlerConfig(timeout=0.1))
            with pytest.raises(FetchError):
                await fetcher.fetch("https://slow.example.com")
```

### Pattern 2: Testing Redis Queue Behavior

```python
class TestRedisQueue:
    @pytest.mark.asyncio
    async def test_push_and_pop_fifo_order(self, frontier_queue):
        items = [
            FrontierItem(url=f"https://example.com/{i}", depth=0)
            for i in range(3)
        ]
        for item in items:
            await frontier_queue.push(item)

        assert await frontier_queue.size() == 3

        # FIFO: first pushed = first popped
        popped = await frontier_queue.pop(FrontierItem, timeout=1)
        assert popped.url == "https://example.com/0"

    @pytest.mark.asyncio
    async def test_pop_returns_none_on_timeout(self, frontier_queue):
        result = await frontier_queue.pop(FrontierItem, timeout=1)
        assert result is None
```

### Pattern 3: Testing URL Deduplication

```python
class TestURLDedup:
    @pytest.mark.asyncio
    async def test_marks_new_url_as_seen(self, fake_redis):
        dedup = URLDedup(fake_redis)
        assert await dedup.mark_seen("https://example.com/page1") is True
        assert await dedup.is_seen("https://example.com/page1") is True

    @pytest.mark.asyncio
    async def test_rejects_duplicate_url(self, fake_redis):
        dedup = URLDedup(fake_redis)
        await dedup.mark_seen("https://example.com/page1")
        assert await dedup.mark_seen("https://example.com/page1") is False

    @pytest.mark.asyncio
    async def test_normalizes_urls_for_dedup(self, fake_redis):
        dedup = URLDedup(fake_redis)
        await dedup.mark_seen("https://EXAMPLE.COM/page#section")
        assert await dedup.is_seen("https://example.com/page") is True

    @pytest.mark.asyncio
    async def test_different_urls_not_duplicated(self, fake_redis):
        dedup = URLDedup(fake_redis)
        await dedup.mark_seen("https://example.com/page1")
        assert await dedup.is_seen("https://example.com/page2") is False
```

### Pattern 4: Testing LLM Relevance Check (Mocked)

```python
class TestRelevanceCheck:
    @pytest.mark.asyncio
    async def test_identifies_promotion_page(self, mock_llm_client):
        is_relevant, confidence = await check_relevance(
            llm=mock_llm_client,
            url="https://bank.example.com/promotions/dining",
            title="Dining Promotions",
            content="20% off at selected restaurants with Platinum Visa",
        )
        assert is_relevant is True
        assert confidence > 0.8

    @pytest.mark.asyncio
    async def test_rejects_non_promotion_page(self, mock_llm_client):
        is_relevant, confidence = await check_relevance(
            llm=mock_llm_client,
            url="https://bank.example.com/about",
            title="About Our Bank",
            content="We are a leading financial institution founded in 1990.",
        )
        assert is_relevant is False

    @pytest.mark.asyncio
    async def test_pre_filter_skips_careers_page(self):
        result = pre_filter(
            url="https://bank.example.com/careers",
            title="Join Our Team",
        )
        assert result == "unlikely"

    @pytest.mark.asyncio
    async def test_pre_filter_flags_promotion_url(self):
        result = pre_filter(
            url="https://bank.example.com/promotions/dining",
            title="Dining Deals",
        )
        assert result == "likely"
```

### Pattern 5: Testing Deal Extraction (Mocked LLM)

```python
class TestDealExtraction:
    @pytest.mark.asyncio
    async def test_extracts_structured_deal(self, mock_llm_client):
        deals = await extract_deals(
            llm=mock_llm_client,
            url="https://bank.example.com/promotions/dining",
            title="Dining Promotions",
            content="20% off at selected restaurants with Platinum Visa. Valid until 31 Dec 2026.",
        )
        assert len(deals) == 1
        deal = deals[0]
        assert deal.bank_name == "Example Bank"
        assert deal.discount_percentage == 20.0
        assert deal.merchant_category == "dining"

    @pytest.mark.asyncio
    async def test_handles_page_with_no_deals(self, mock_llm_client):
        # Override mock to return empty
        mock_llm_client.complete = lambda *a, **kw: asyncio.coroutine(lambda: "[]")()
        deals = await extract_deals(
            llm=mock_llm_client,
            url="https://bank.example.com/about",
            title="About",
            content="We are a bank.",
        )
        assert deals == []

    @pytest.mark.asyncio
    async def test_handles_malformed_llm_response(self, mock_llm_client):
        async def bad_response(*a, **kw):
            return "this is not json"
        mock_llm_client.complete = bad_response

        deals = await extract_deals(
            llm=mock_llm_client,
            url="https://example.com",
            title="Test",
            content="Content",
        )
        assert deals == []  # Graceful fallback
```

### Pattern 6: Testing the API (FastAPI TestClient)

```python
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

@pytest.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

class TestDealsEndpoint:
    @pytest.mark.asyncio
    async def test_list_deals(self, api_client, seed_deals_in_db):
        response = await api_client.get("/deals")
        assert response.status_code == 200
        data = response.json()
        assert len(data["deals"]) > 0

    @pytest.mark.asyncio
    async def test_filter_by_bank(self, api_client, seed_deals_in_db):
        response = await api_client.get("/deals?bank=Example Bank")
        assert response.status_code == 200
        deals = response.json()["deals"]
        assert all(d["bank_name"] == "Example Bank" for d in deals)

    @pytest.mark.asyncio
    async def test_filter_by_category(self, api_client, seed_deals_in_db):
        response = await api_client.get("/deals?category=dining")
        assert response.status_code == 200
        deals = response.json()["deals"]
        assert all(d["merchant_category"] == "dining" for d in deals)
```

### Pattern 7: Integration Test with Real Docker Services

```python
@pytest.mark.integration
class TestCrawlLoopIntegration:
    """Requires running Redis + MinIO via Docker Compose test profile."""

    @pytest.mark.asyncio
    async def test_fetch_store_and_enqueue(self, real_redis, real_minio, mock_bank_transport):
        """Full cycle: dequeue URL → fetch → store in MinIO → enqueue for parsing."""
        frontier = RedisQueue(real_redis, "frontier")
        parsing = RedisQueue(real_redis, "parsing")

        # Seed the frontier
        await frontier.push(FrontierItem(
            url="https://bank.example.com/promotions",
            depth=0,
        ))

        # Run one crawl iteration
        async with httpx.AsyncClient(transport=mock_bank_transport) as http:
            result = await crawl_one(
                frontier_queue=frontier,
                parsing_queue=parsing,
                http_client=http,
                minio_client=real_minio,
                config=CrawlerConfig(request_delay=0),
            )

        assert result.status == CrawlStatus.FETCHED
        assert await parsing.size() == 1

        # Verify HTML is in MinIO
        item = await parsing.pop(ParsingQueueItem, timeout=1)
        obj = await real_minio.get_object("pages", item.minio_path)
        html = await obj.read()
        assert b"Credit Card Promotions" in html
```

## Running Tests

```bash
# Unit tests (fast, no Docker needed)
cd services/crawler && pytest tests/unit/
cd services/parser && pytest tests/unit/
cd services/extractor && pytest tests/unit/

# Integration tests (need Docker Compose services)
docker compose --profile test up -d redis postgres minio
pytest tests/integration/ -m integration

# E2E tests (full system)
docker compose up -d
pytest tests/e2e/ -m e2e

# Coverage report
pytest --cov=crawler --cov-report=term-missing tests/unit/

# All unit tests across all services
pytest services/*/tests/unit/
```

## Anti-Patterns

- **Don't test with real LLM calls** in unit tests — they're slow, expensive, and non-deterministic. Always mock.
- **Don't use real Redis** in unit tests — use `fakeredis`. Save real Redis for integration tests.
- **Don't hardcode bank-specific HTML** in every test — put reusable HTML in fixtures files.
- **Don't test queue + fetcher + parser together** in unit tests — that's integration testing.
- **Don't skip testing the error paths** — LLM failures, Redis timeouts, MinIO unavailability, malformed HTML. These happen in production constantly.
