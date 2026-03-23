#!/usr/bin/env python3
"""Seed the frontier queue with initial URLs from bank configurations.

Usage:
    python scripts/seed.py
    python scripts/seed.py --config banks.yaml
    python scripts/seed.py --clear  # Clear queues and dedup set before seeding

Reads bank configs (migrated from the V1 config.json) and pushes
seed URLs into the Redis frontier queue.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

import redis.asyncio as redis

from shared.dedup import URLDedup
from shared.models import FrontierItem
from shared.queue import RedisQueue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Default bank configs — migrated from V1 config.json
DEFAULT_BANKS = [
    {
        "name": "Sampath Bank",
        "seed_urls": [
            "https://www.sampath.lk/sampath-cards/credit-card-offer",
            "https://www.sampath.lk/sampath-cards/credit-card-offer?firstTab=super_markets",
            "https://www.sampath.lk/sampath-cards/credit-card-offer?firstTab=Electronics_and_Furniture",
            "https://www.sampath.lk/sampath-cards/credit-card-offer?firstTab=shopping",
            "https://www.sampath.lk/sampath-cards/credit-card-offer?firstTab=hotels",
            "https://www.sampath.lk/sampath-cards/credit-card-offer?firstTab=health",
            "https://www.sampath.lk/sampath-cards/credit-card-offer?firstTab=online",
        ],
        "needs_puppeteer": True,
    },
    {
        "name": "People's Bank",
        "seed_urls": [
            "https://www.peoplesbank.lk/special-offers/",
        ],
        "needs_puppeteer": False,
    },
    {
        "name": "Bank of Ceylon",
        "seed_urls": [
            "https://www.boc.lk/personal-banking/card-offers/",
            "https://www.boc.lk/personal-banking/card-offers/travel-and-leisure",
            "https://www.boc.lk/personal-banking/card-offers/lifestyle",
            "https://www.boc.lk/personal-banking/card-offers/supermarkets",
            "https://www.boc.lk/personal-banking/card-offers/zero-plans",
            "https://www.boc.lk/personal-banking/card-offers/online",
            "https://www.boc.lk/personal-banking/card-offers/health-beauty",
            "https://www.boc.lk/personal-banking/card-offers/dining",
        ],
        "needs_puppeteer": False,
    },
    {
        "name": "HSBC",
        "seed_urls": [
            "https://www.hsbc.lk/credit-cards/offers/",
        ],
        "needs_puppeteer": False,
    },
    {
        "name": "Commercial Bank",
        "seed_urls": [
            "https://www.combank.lk/rewards-promotions",
        ],
        "needs_puppeteer": False,
    },
    {
        "name": "DFCC Bank",
        "seed_urls": [
            "https://www.dfcc.lk/promotions-categories/card-promotions/",
        ],
        "needs_puppeteer": False,
    },
]


async def seed(
    redis_url: str = "redis://localhost:6379/0",
    banks: list[dict] | None = None,
    clear: bool = False,
) -> None:
    """Push seed URLs into the frontier queue."""
    client = await redis.from_url(redis_url, decode_responses=False)
    frontier = RedisQueue(client, "frontier")
    dedup = URLDedup(client)

    if clear:
        logger.info("Clearing queues and dedup set...")
        await frontier.clear()
        await RedisQueue(client, "parsing").clear()
        await RedisQueue(client, "extraction").clear()
        await dedup.clear()

    banks = banks or DEFAULT_BANKS
    total = 0

    for bank in banks:
        name = bank["name"]
        urls = bank.get("seed_urls", [])
        logger.info("Seeding %d URLs for %s", len(urls), name)

        for url in urls:
            if await dedup.is_seen(url):
                logger.debug("Skipping already-seen URL: %s", url)
                continue

            await frontier.push(FrontierItem(
                url=url,
                depth=0,
                priority=10,  # Seeds get high priority
                source_url=None,
                domain=name.lower().replace(" ", "-"),
                needs_puppeteer=bank.get("needs_puppeteer", False),
            ))
            total += 1

    queue_size = await frontier.size()
    logger.info("Seeded %d new URLs. Frontier queue size: %d", total, queue_size)
    await client.aclose()


def main():
    parser = argparse.ArgumentParser(description="Seed the crawler frontier queue")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--config", type=Path, help="JSON file with bank configs")
    parser.add_argument("--clear", action="store_true", help="Clear queues before seeding")
    args = parser.parse_args()

    config_path = args.config or Path(__file__).parent.parent / "config" / "banks.json"
    banks = None
    if config_path.exists():
        with open(config_path) as f:
            data = json.load(f)
            banks = data.get("banks", data) if isinstance(data, dict) else data
        logger.info("Loaded bank config from %s", config_path)

    asyncio.run(seed(redis_url=args.redis_url, banks=banks, clear=args.clear))


if __name__ == "__main__":
    main()
