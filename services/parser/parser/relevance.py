"""Two-stage relevance checking for credit card promotion detection."""

import json
import logging
import re
from typing import Literal

from shared.llm_client import LLMClient


logger = logging.getLogger(__name__)

# Prompt for LLM relevance check
RELEVANCE_PROMPT = """You are a credit card promotion detector. Analyze the following web page and determine if it contains promotions or offers for Sri Lankan credit cards or banking products.

URL: {url}
Title: {title}
Content (first 2000 chars):
{content}

Look for:
- Credit card offers and eligibility
- Dining deals and merchant partnerships
- Shopping discounts and cashback offers
- Rewards programs and loyalty benefits
- Special promotions or limited-time offers
- Annual fees and benefits

Respond with ONLY a JSON object:
{{"is_relevant": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}

If you cannot determine relevance, default to false with low confidence."""

# Keywords for pre-filtering - likely relevant
LIKELY_KEYWORDS = [
    r"card\s+offer",
    r"credit\s+card",
    r"dining\s+deal",
    r"cashback",
    r"rewards?",
    r"merchant\s+partner",
    r"shopping\s+discount",
    r"offer",
    r"promotion",
    r"special\s+rate",
    r"interest\s+rate",
    r"annual\s+fee",
    r"loyalty\s+program",
    r"exclusive\s+benefit",
]

# Keywords for pre-filtering - unlikely relevant
UNLIKELY_KEYWORDS = [
    r"careers?",
    r"job",
    r"recruitment",
    r"press\s+release",
    r"news",
    r"annual\s+report",
    r"financial\s+statement",
    r"investor",
    r"earnings",
    r"stock",
]

# Compiled regex patterns
LIKELY_PATTERNS = [re.compile(keyword, re.IGNORECASE) for keyword in LIKELY_KEYWORDS]
UNLIKELY_PATTERNS = [
    re.compile(keyword, re.IGNORECASE) for keyword in UNLIKELY_KEYWORDS
]


def pre_filter(url: str, title: str) -> Literal["likely", "unlikely", "uncertain"]:
    """Quick pre-filter based on URL and title patterns.

    Args:
        url: URL to check.
        title: Page title.

    Returns:
        "likely" if strong indicators of credit card promotions,
        "unlikely" if strong indicators it's not,
        "uncertain" for ambiguous cases requiring LLM check.
    """
    combined_text = f"{url} {title}".lower()

    # Check unlikely patterns first (higher priority to avoid false positives)
    if any(pattern.search(combined_text) for pattern in UNLIKELY_PATTERNS):
        return "unlikely"

    # Check likely patterns
    likely_count = sum(1 for pattern in LIKELY_PATTERNS if pattern.search(combined_text))
    if likely_count >= 2:
        return "likely"

    if likely_count >= 1:
        return "uncertain"

    return "uncertain"


async def check_relevance(
    llm: LLMClient, url: str, title: str, content: str
) -> tuple[bool, float]:
    """Check relevance using LLM with retry logic.

    Args:
        llm: LLM client for making API calls.
        url: URL of the page.
        title: Page title.
        content: Page content text.

    Returns:
        Tuple of (is_relevant, confidence).
        Defaults to (True, 0.0) on failure to avoid false negatives.
    """
    # Truncate content to avoid token limits
    content_truncated = content[:2000]

    # Format prompt
    prompt = RELEVANCE_PROMPT.format(url=url, title=title, content=content_truncated)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = await llm.complete(prompt)

            # Extract JSON from response (may contain other text)
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                logger.warning(
                    "No JSON found in LLM response for %s: %s...",
                    url,
                    response[:200],
                )
                continue

            result = json.loads(json_match.group())
            is_relevant = result.get("is_relevant", True)
            confidence = float(result.get("confidence", 0.0))

            logger.debug(
                "LLM relevance check: %s -> relevant=%s, confidence=%.2f",
                url,
                is_relevant,
                confidence,
            )

            return is_relevant, confidence

        except Exception as e:
            logger.warning(
                "LLM relevance check failed for %s (attempt %d/%d): %s",
                url,
                attempt + 1,
                max_retries,
                e,
            )
            if attempt < max_retries - 1:
                continue

    # Default to relevant on failure (avoid missing promotions)
    logger.warning("LLM check exhausted retries for %s, defaulting to relevant", url)
    return True, 0.0
