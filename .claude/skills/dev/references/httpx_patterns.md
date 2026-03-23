# httpx Patterns for ContextCrawler

Common patterns for using httpx as the HTTP client layer.

## Table of Contents

1. [Client Setup & Connection Pooling](#client-setup)
2. [Request Configuration](#request-config)
3. [Response Handling](#response-handling)
4. [Retry with Backoff](#retry)
5. [Proxy Support](#proxy)
6. [Cookie & Session Handling](#cookies)
7. [Streaming Responses](#streaming)
8. [HTTP/2 Support](#http2)
9. [Testing with Mocked Transport](#testing)

---

## Client Setup & Connection Pooling <a id="client-setup"></a>

```python
import httpx

# Connection pool limits
limits = httpx.Limits(
    max_connections=100,        # Total connection pool size
    max_keepalive_connections=20, # Keep-alive pool
    keepalive_expiry=30,        # Seconds before closing idle connections
)

# Timeout configuration — set per-phase, not just a single number
timeout = httpx.Timeout(
    connect=5.0,    # Time to establish connection
    read=30.0,      # Time to receive response
    write=10.0,     # Time to send request body
    pool=10.0,      # Time waiting for a connection from the pool
)

async with httpx.AsyncClient(
    limits=limits,
    timeout=timeout,
    follow_redirects=True,
    max_redirects=5,
    http2=True,
) as client:
    response = await client.get(url)
```

## Request Configuration <a id="request-config"></a>

```python
# Custom headers per request
response = await client.get(
    url,
    headers={
        "User-Agent": "ContextCrawler/1.0",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    },
)

# Query parameters
response = await client.get(url, params={"page": 2, "limit": 50})
```

## Response Handling <a id="response-handling"></a>

```python
response = await client.get(url)

# Status checking
response.raise_for_status()  # Raises httpx.HTTPStatusError for 4xx/5xx

# Content type detection
content_type = response.headers.get("content-type", "")
is_html = "text/html" in content_type

# Encoding detection — httpx handles this well but you can override
text = response.text  # Auto-detected encoding
raw_bytes = response.content  # Raw bytes

# Response metadata
print(response.status_code)
print(response.url)  # Final URL after redirects
print(response.is_redirect)
print(dict(response.headers))
```

## Retry with Backoff <a id="retry"></a>

```python
import asyncio
import random
from typing import TypeVar

T = TypeVar("T")

async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retry_on: tuple[type[Exception], ...] = (
        httpx.TimeoutException,
        httpx.ConnectError,
    ),
    retry_status_codes: set[int] = {429, 500, 502, 503, 504},
) -> httpx.Response:
    """Fetch URL with exponential backoff and jitter."""
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = await client.get(url)
            if response.status_code in retry_status_codes and attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                delay *= 0.5 + random.random()  # Jitter

                # Respect Retry-After header for 429s
                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    if retry_after and retry_after.isdigit():
                        delay = max(delay, float(retry_after))

                await asyncio.sleep(delay)
                continue
            return response

        except retry_on as exc:
            last_exception = exc
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                delay *= 0.5 + random.random()
                await asyncio.sleep(delay)

    raise last_exception or RuntimeError("Retry loop exited unexpectedly")
```

## Proxy Support <a id="proxy"></a>

```python
# Single proxy
async with httpx.AsyncClient(proxy="http://proxy:8080") as client:
    response = await client.get(url)

# Rotating proxies — swap client or use custom transport
class RotatingProxyTransport(httpx.AsyncBaseTransport):
    def __init__(self, proxies: list[str]) -> None:
        self._proxies = proxies
        self._index = 0

    async def handle_async_request(self, request):
        proxy_url = self._proxies[self._index % len(self._proxies)]
        self._index += 1
        async with httpx.AsyncClient(proxy=proxy_url) as proxy_client:
            return await proxy_client.send(request)
```

## Cookie & Session Handling <a id="cookies"></a>

```python
# httpx AsyncClient automatically manages cookies across requests
async with httpx.AsyncClient(cookies={"session": "abc123"}) as client:
    # Cookies persist across requests in the same client
    await client.get("https://example.com/login")
    response = await client.get("https://example.com/dashboard")
```

## Streaming Responses <a id="streaming"></a>

```python
# Stream large responses to avoid loading everything into memory
async with client.stream("GET", url) as response:
    async for chunk in response.aiter_bytes(chunk_size=8192):
        process_chunk(chunk)

# Stream lines (useful for line-delimited JSON, sitemaps, etc.)
async with client.stream("GET", url) as response:
    async for line in response.aiter_lines():
        process_line(line)
```

## HTTP/2 Support <a id="http2"></a>

```python
# Enable HTTP/2 — requires httpx[http2] (uses h2 library)
# pip install httpx[http2]
async with httpx.AsyncClient(http2=True) as client:
    response = await client.get(url)
    print(response.http_version)  # "HTTP/2" or "HTTP/1.1"
```

## Testing with Mocked Transport <a id="testing"></a>

```python
import httpx
import pytest

class MockTransport(httpx.MockTransport):
    pass

def html_response(content: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=content.encode(),
        headers={"content-type": "text/html; charset=utf-8"},
    )

@pytest.fixture
def mock_client():
    """Client with mocked transport for testing."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "example.com" in url:
            return html_response("<html><body>Hello</body></html>")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)
```
