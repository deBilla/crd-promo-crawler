"""Parser service entry point.

Consumes pages from the parsing queue, extracts text/links, checks relevance,
pushes new URLs to the frontier and relevant pages to the extraction queue.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import signal
import time
from pathlib import Path

from parser.config import ParserConfig
from parser.html_parser import extract_links, extract_text, extract_title
from parser.link_filter import filter_urls
from parser.relevance import check_relevance, pre_filter
from shared.config import LLMConfig
from shared.db import create_engine, create_session_factory, create_tables, URLMetadataRow
from shared.dedup import URLDedup
from shared.llm_client import create_llm_client
from shared.minio_client import create_minio, download_html
from shared.models import CrawlStatus, ExtractionQueueItem, FrontierItem, ParsingQueueItem
from shared.queue import RedisQueue
from shared.redis_client import create_redis

logger = logging.getLogger(__name__)

# Telemetry instruments (initialized in main)
_meter = None
_tracer = None
_pages_parsed = None
_pages_relevant = None
_pages_irrelevant = None
_links_discovered = None
_prefilter_results = None
_llm_call_duration = None
_llm_errors = None
_errors = None


def load_bank_url_patterns(config_path: str = "config/banks.json") -> dict[str, list[re.Pattern]]:
    """Load bank URL patterns from config, keyed by cleaned domain."""
    patterns: dict[str, list[re.Pattern]] = {}
    path = Path(config_path)
    if not path.exists():
        return patterns
    with open(path) as f:
        data = json.load(f)
    banks = data.get("banks", data) if isinstance(data, dict) else data
    for bank in banks:
        base_url = bank.get("base_url", "")
        if not base_url:
            continue
        from urllib.parse import urlparse
        domain = urlparse(base_url).netloc.lower().replace("www.", "").replace("www2.", "")
        compiled = [re.compile(p) for p in bank.get("url_patterns", [])]
        if compiled:
            patterns[domain] = compiled
    return patterns


async def process_item(
    item: ParsingQueueItem,
    *,
    config: ParserConfig,
    minio,
    llm,
    dedup: URLDedup,
    session_factory,
    frontier_queue: RedisQueue,
    extraction_queue: RedisQueue,
    bank_patterns: dict[str, list[re.Pattern]],
) -> None:
    """Process a single parsing queue item."""
    logger.info("Processing: %s (depth=%d)", item.url, item.depth)

    # Download HTML from MinIO
    try:
        html = await download_html(minio, config.minio_bucket, item.minio_path)
        if not html:
            logger.warning("Empty HTML from MinIO: %s", item.minio_path)
            return
    except Exception as e:
        logger.error("Error downloading from MinIO %s: %s", item.minio_path, e)
        return

    # Extract text, title, and links
    try:
        text = extract_text(html)
        title = extract_title(html)
        links = extract_links(html, item.url)
        logger.debug("Extracted %d links from %s", len(links), item.url)
    except Exception as e:
        logger.error("Error parsing HTML from %s: %s", item.url, e)
        return

    # Filter discovered links by domain and depth, dedup, push to frontier
    # Note: only check is_seen here — the crawler marks URLs as seen after popping
    domain_clean = item.domain.replace("www.", "").replace("www2.", "")
    url_patterns = bank_patterns.get(domain_clean)
    filtered_links = filter_urls(links, item.domain, config.max_depth, item.depth, url_patterns)
    new_links = 0
    for url in filtered_links:
        if not await dedup.is_seen(url):
            await frontier_queue.push(FrontierItem(
                url=url,
                domain=item.domain,
                depth=item.depth + 1,
            ))
            new_links += 1
    logger.debug("Pushed new links to frontier from %s", item.url)
    if _links_discovered:
        _links_discovered.add(new_links, {"domain": item.domain})

    # Two-stage relevance check
    pre_result = pre_filter(item.url, title)
    if _prefilter_results:
        _prefilter_results.add(1, {"result": pre_result})

    if pre_result == "likely":
        is_relevant, confidence = True, 0.9
    elif pre_result == "unlikely":
        is_relevant, confidence = False, 0.1
    else:
        t0 = time.monotonic()
        try:
            is_relevant, confidence = await check_relevance(llm, item.url, title, text)
        except Exception:
            if _llm_errors:
                _llm_errors.add(1, {"service": "parser"})
            raise
        if _llm_call_duration:
            _llm_call_duration.record(time.monotonic() - t0, {"service": "parser"})

    logger.debug("Relevance for %s: relevant=%s, confidence=%.2f", item.url, is_relevant, confidence)

    # Update URL metadata in Postgres
    async with session_factory() as session:
        from sqlalchemy import update

        status = CrawlStatus.RELEVANT if is_relevant else CrawlStatus.IRRELEVANT
        await session.execute(
            update(URLMetadataRow)
            .where(URLMetadataRow.url == item.url)
            .values(status=status, parsed_at=__import__("datetime").datetime.utcnow())
        )
        await session.commit()

    # Record parse metrics
    if _pages_parsed:
        _pages_parsed.add(1, {"domain": item.domain})
    if is_relevant and _pages_relevant:
        _pages_relevant.add(1, {"domain": item.domain})
    elif not is_relevant and _pages_irrelevant:
        _pages_irrelevant.add(1, {"domain": item.domain})

    # Push relevant pages to extraction queue
    if is_relevant:
        await extraction_queue.push(ExtractionQueueItem(
            url=item.url,
            minio_path=item.minio_path,
            text_content=text[:10000],  # Truncate for queue message size
            page_title=title,
            domain=item.domain,
        ))
        logger.info("Pushed to extraction queue: %s", item.url)
    else:
        logger.debug("Not relevant: %s", item.url)


async def main() -> None:
    """Main loop: pop pages from parsing queue → parse → relevance check → route."""
    global _meter, _tracer, _pages_parsed, _pages_relevant, _pages_irrelevant
    global _links_discovered, _prefilter_results, _llm_call_duration, _llm_errors, _errors

    config = ParserConfig()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Initialize OpenTelemetry
    if config.otel_enabled:
        from shared.telemetry import init_telemetry
        _meter, _tracer = init_telemetry("parser", config.otel_endpoint)
        _pages_parsed = _meter.create_counter("pages_parsed", description="Pages parsed")
        _pages_relevant = _meter.create_counter("pages_relevant", description="Pages marked relevant")
        _pages_irrelevant = _meter.create_counter("pages_irrelevant", description="Pages marked irrelevant")
        _links_discovered = _meter.create_counter("links_discovered", description="New links discovered")
        _prefilter_results = _meter.create_counter("prefilter_results", description="Pre-filter outcomes")
        _llm_call_duration = _meter.create_histogram(
            "llm_call_duration_seconds", description="LLM call duration", unit="s",
        )
        _llm_errors = _meter.create_counter("llm_errors", description="LLM call errors")
        _errors = _meter.create_counter("processing_errors", description="Processing errors")

    logger.info("Starting parser service...")

    # Initialize connections
    redis_client = await create_redis(config.redis_url)
    engine = create_engine(config.database_url)
    session_factory = create_session_factory(engine)
    minio = create_minio(
        config.minio_endpoint, config.minio_access_key,
        config.minio_secret_key, config.minio_secure,
    )

    # Build LLMConfig for the LLM client factory
    llm_config = LLMConfig(
        llm_provider=config.llm_provider,
        llm_model=config.llm_model,
        llm_base_url=config.llm_base_url,
        llm_api_key=config.llm_api_key,
        llm_max_retries=config.llm_max_retries,
        llm_timeout=config.llm_timeout,
    )
    llm = create_llm_client(llm_config)

    # Ensure tables exist
    await create_tables(engine)

    # Load bank URL patterns for link filtering
    bank_patterns = load_bank_url_patterns()
    logger.info("Loaded URL patterns for %d banks", len(bank_patterns))

    # Set up queues
    parsing_queue = RedisQueue(redis_client, config.parsing_queue_name)
    frontier_queue = RedisQueue(redis_client, config.frontier_queue_name)
    extraction_queue = RedisQueue(redis_client, config.extraction_queue_name)
    dedup = URLDedup(redis_client)

    # Graceful shutdown
    shutdown = asyncio.Event()

    def on_signal(sig):
        logger.info("Received %s — shutting down...", signal.Signals(sig).name)
        shutdown.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, on_signal, sig)

    logger.info("Parser ready. Waiting for items on queue '%s'...", config.parsing_queue_name)

    while not shutdown.is_set():
        item = await parsing_queue.pop(ParsingQueueItem, timeout=config.pop_timeout)
        if item is None:
            continue

        try:
            await process_item(
                item,
                config=config,
                minio=minio,
                llm=llm,
                dedup=dedup,
                session_factory=session_factory,
                frontier_queue=frontier_queue,
                extraction_queue=extraction_queue,
                bank_patterns=bank_patterns,
            )
        except Exception as e:
            logger.error("Error processing %s: %s", item.url, e, exc_info=True)
            if _errors:
                _errors.add(1, {"service": "parser", "type": "unexpected"})

    # Cleanup
    await llm.close()
    await redis_client.aclose()
    await engine.dispose()
    logger.info("Parser service stopped.")


if __name__ == "__main__":
    asyncio.run(main())
