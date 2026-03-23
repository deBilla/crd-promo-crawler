"""Extractor service entry point.

Consumes relevant pages from the extraction queue, calls the LLM to extract
structured credit card deals, and stores them in Postgres.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime

from sqlalchemy import update

from extractor.config import ExtractorConfig
from extractor.extract import extract_deals
from shared.config import LLMConfig
from shared.db import CreditCardDealRow, URLMetadataRow, create_engine, create_session_factory, create_tables
from shared.llm_client import create_llm_client
from shared.models import CrawlStatus, CreditCardDeal, ExtractionQueueItem
from shared.queue import RedisQueue
from shared.redis_client import create_redis

logger = logging.getLogger(__name__)


async def store_deals(
    deals: list[CreditCardDeal],
    source_url: str,
    session_factory,
) -> int:
    """Store extracted deals in Postgres, skipping duplicates.

    Returns the number of newly stored deals.
    """
    if not deals:
        return 0

    stored = 0
    async with session_factory() as session:
        for deal in deals:
            try:
                # Check for duplicates (same source URL + promotion title)
                from sqlalchemy import select, and_
                existing = await session.execute(
                    select(CreditCardDealRow).where(
                        and_(
                            CreditCardDealRow.source_url == source_url,
                            CreditCardDealRow.promotion_title == deal.promotion_title,
                        )
                    )
                )
                if existing.scalar_one_or_none():
                    logger.debug("Skipping duplicate: %s", deal.promotion_title)
                    continue

                row = CreditCardDealRow(
                    source_url=source_url,
                    bank_name=deal.bank_name,
                    card_name=deal.card_name,
                    card_types=deal.card_types,
                    promotion_title=deal.promotion_title,
                    description=deal.description,
                    category=deal.category,
                    discount_percentage=deal.discount_percentage,
                    discount_amount=deal.discount_amount,
                    max_discount_lkr=deal.max_discount_lkr,
                    merchant_name=deal.merchant_name,
                    merchant_category=deal.merchant_category,
                    merchant_logo_url=deal.merchant_logo_url,
                    valid_from=deal.valid_from,
                    valid_until=deal.valid_until,
                    valid_days=deal.valid_days,
                    terms_and_conditions=deal.terms_and_conditions,
                    raw_text=deal.raw_text,
                    confidence_score=deal.confidence_score,
                )
                session.add(row)
                stored += 1
            except Exception as e:
                logger.error("Failed to store deal '%s': %s", deal.promotion_title, e)

        await session.commit()

    logger.info("Stored %d deals from %s", stored, source_url)
    return stored


async def process_item(
    item: ExtractionQueueItem,
    *,
    llm,
    session_factory,
    max_content_chars: int,
) -> None:
    """Process a single extraction queue item."""
    logger.info("Extracting deals from: %s", item.url)

    # Extract deals using LLM
    deals = await extract_deals(
        llm,
        item.url,
        item.page_title,
        item.text_content,
        max_content_chars,
    )

    # Store deals
    stored_count = await store_deals(deals, item.url, session_factory)

    # Update URL metadata status
    async with session_factory() as session:
        await session.execute(
            update(URLMetadataRow)
            .where(URLMetadataRow.url == item.url)
            .values(status=CrawlStatus.EXTRACTED)
        )
        await session.commit()

    logger.info("Processed %s: extracted %d deals, stored %d", item.url, len(deals), stored_count)


async def main() -> None:
    """Main loop: pop from extraction queue → LLM extract → store."""
    config = ExtractorConfig()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    logger.info("Starting extractor service...")

    # Initialize connections
    redis_client = await create_redis(config.redis_url)
    engine = create_engine(config.database_url)
    session_factory = create_session_factory(engine)

    # Build LLMConfig for the factory
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

    # Set up queue
    extraction_queue = RedisQueue(redis_client, config.extraction_queue_name)

    # Graceful shutdown
    shutdown = asyncio.Event()

    def on_signal(sig):
        logger.info("Received %s — shutting down...", signal.Signals(sig).name)
        shutdown.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, on_signal, sig)

    logger.info("Extractor ready. Waiting for items on queue '%s'...", config.extraction_queue_name)

    while not shutdown.is_set():
        item = await extraction_queue.pop(ExtractionQueueItem, timeout=config.pop_timeout)
        if item is None:
            continue

        try:
            await process_item(
                item,
                llm=llm,
                session_factory=session_factory,
                max_content_chars=config.max_content_chars,
            )
        except Exception as e:
            logger.error("Error processing %s: %s", item.url, e, exc_info=True)

    # Cleanup
    await llm.close()
    await redis_client.aclose()
    await engine.dispose()
    logger.info("Extractor service stopped.")


if __name__ == "__main__":
    asyncio.run(main())
