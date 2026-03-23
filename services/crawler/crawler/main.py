"""Crawler service entry point.

Consumes URLs from the frontier queue, fetches HTML, stores in MinIO,
writes metadata to Postgres, and pushes items to the parsing queue.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime
from urllib.parse import urlparse

from crawler.config import CrawlerConfig
from crawler.fetcher import FetchError, PageFetcher, create_http_client
from crawler.rate_limiter import DomainRateLimiter
from shared.db import URLMetadataRow, create_engine, create_session_factory, create_tables
from shared.dedup import URLDedup
from shared.minio_client import create_minio, ensure_bucket, upload_html
from shared.models import CrawlStatus, FrontierItem, ParsingQueueItem
from shared.queue import RedisQueue
from shared.redis_client import create_redis

logger = logging.getLogger(__name__)


async def process_url(
    item: FrontierItem,
    *,
    fetcher: PageFetcher,
    rate_limiter: DomainRateLimiter,
    minio,
    config: CrawlerConfig,
    session_factory,
    parsing_queue: RedisQueue,
    dedup: URLDedup,
) -> None:
    """Process a single URL: rate-limit → fetch → content-dedup → store → enqueue."""
    domain = urlparse(item.url).netloc

    # Rate limit per domain
    await rate_limiter.acquire(domain)

    # Fetch — use Puppeteer for JS-rendered pages
    if item.needs_puppeteer:
        logger.info("Using Puppeteer for %s", item.url)
        result = await fetcher.fetch_with_puppeteer(item.url)
    else:
        result = await fetcher.fetch(item.url)
    logger.info("Fetched %s → %d (%d bytes)", item.url, result.status_code, len(result.content))

    if result.status_code >= 400:
        # Record the failure but don't enqueue for parsing
        async with session_factory() as session:
            row = URLMetadataRow(
                url=item.url,
                domain=domain,
                status=CrawlStatus.FAILED,
                status_code=result.status_code,
                depth=item.depth,
                error_message=f"HTTP {result.status_code}",
                fetched_at=datetime.utcnow(),
            )
            session.add(row)
            await session.commit()
        return

    # Content-based dedup: skip if identical content already processed
    if await dedup.is_content_seen(result.content_hash):
        logger.info("Duplicate content for %s (hash=%s…), skipping", item.url, result.content_hash[:12])
        return
    await dedup.mark_content_seen(result.content_hash)

    # Store HTML in MinIO
    minio_path = await upload_html(minio, config.minio_bucket, item.url, result.content)

    # Write metadata to Postgres
    async with session_factory() as session:
        row = URLMetadataRow(
            url=item.url,
            domain=domain,
            file_path=minio_path,
            status=CrawlStatus.FETCHED,
            status_code=result.status_code,
            content_hash=result.content_hash,
            depth=item.depth,
            is_seed=item.depth == 0,
            fetched_at=datetime.utcnow(),
        )
        session.add(row)
        await session.commit()

    # Enqueue for parsing
    await parsing_queue.push(ParsingQueueItem(
        url=item.url,
        minio_path=minio_path,
        depth=item.depth,
        domain=domain,
    ))


async def handle_failure(
    item: FrontierItem,
    error: Exception,
    frontier_queue: RedisQueue,
    session_factory,
    max_retries: int,
) -> None:
    """Handle a failed fetch: retry or mark as dead."""
    domain = urlparse(item.url).netloc
    new_retry = item.priority + 1  # Reuse priority field as retry count for simplicity

    if new_retry <= max_retries:
        logger.warning("Retrying %s (attempt %d/%d): %s", item.url, new_retry, max_retries, error)
        item.priority = new_retry
        await frontier_queue.push(item)
    else:
        logger.error("Giving up on %s after %d retries: %s", item.url, max_retries, error)
        async with session_factory() as session:
            row = URLMetadataRow(
                url=item.url,
                domain=domain,
                status=CrawlStatus.DEAD,
                depth=item.depth,
                retry_count=max_retries,
                error_message=str(error),
            )
            session.add(row)
            await session.commit()


async def main() -> None:
    """Main loop: pop URLs from frontier → fetch → store → enqueue."""
    config = CrawlerConfig()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    logger.info("Starting crawler service...")

    # Initialize connections
    redis_client = await create_redis(config.redis_url)
    engine = create_engine(config.database_url)
    session_factory = create_session_factory(engine)
    minio = create_minio(
        config.minio_endpoint, config.minio_access_key,
        config.minio_secret_key, config.minio_secure,
    )
    http_client = create_http_client(config)

    # Ensure infrastructure is ready
    await create_tables(engine)
    await ensure_bucket(minio, config.minio_bucket)

    frontier_queue = RedisQueue(redis_client, config.frontier_queue_name)
    parsing_queue = RedisQueue(redis_client, config.parsing_queue_name)
    rate_limiter = DomainRateLimiter(redis_client, config.request_delay)
    dedup = URLDedup(redis_client)
    fetcher = PageFetcher(http_client, config)

    # Graceful shutdown
    shutdown = asyncio.Event()

    def on_signal(sig):
        logger.info("Received %s — shutting down...", signal.Signals(sig).name)
        shutdown.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, on_signal, sig)

    logger.info("Crawler ready. Waiting for URLs on queue '%s'...", config.frontier_queue_name)

    while not shutdown.is_set():
        item = await frontier_queue.pop(FrontierItem, timeout=config.pop_timeout)
        if item is None:
            continue

        # Dedup check (in case URL was added to queue before dedup existed)
        if await dedup.is_seen(item.url):
            logger.debug("Skipping already-seen URL: %s", item.url)
            continue
        await dedup.mark_seen(item.url)

        # Per-domain URL ceiling
        domain = urlparse(item.url).netloc
        if await dedup.is_domain_exhausted(domain, config.max_urls_per_domain):
            logger.info("Domain ceiling reached for %s, skipping %s", domain, item.url)
            continue
        await dedup.increment_domain(domain)

        try:
            await process_url(
                item,
                fetcher=fetcher,
                rate_limiter=rate_limiter,
                minio=minio,
                config=config,
                session_factory=session_factory,
                parsing_queue=parsing_queue,
                dedup=dedup,
            )
        except FetchError as e:
            await handle_failure(item, e, frontier_queue, session_factory, config.max_retries)
        except Exception as e:
            logger.error("Unexpected error processing %s: %s", item.url, e, exc_info=True)
            await handle_failure(item, e, frontier_queue, session_factory, config.max_retries)

    # Cleanup
    await http_client.aclose()
    await redis_client.aclose()
    await engine.dispose()
    logger.info("Crawler service stopped.")


if __name__ == "__main__":
    asyncio.run(main())
