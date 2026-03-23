# LLM Integration Patterns

The crawler uses LLM calls in two places: relevance filtering (parser service) and structured deal extraction (extractor service). This reference covers both.

## Table of Contents

1. [Relevance Check (Parser Service)](#relevance-check)
2. [Deal Extraction (Extractor Service)](#deal-extraction)
3. [LLM Client Abstraction](#client-abstraction)
4. [Error Handling & Fallbacks](#error-handling)
5. [Cost Management](#cost-management)

---

## Relevance Check (Parser Service) <a id="relevance-check"></a>

The relevance check determines whether a crawled page contains credit card promotion content. This runs on every parsed page, so it needs to be fast and cheap.

### Two-Stage Filtering

**Stage 1 — URL/Title Pre-filter (no LLM, instant):**

```python
PROMO_URL_PATTERNS = [
    r"/promotions?/",
    r"/offers?/",
    r"/deals?/",
    r"/credit-?cards?/",
    r"/rewards?/",
    r"/cashback/",
    r"/privileges?/",
    r"/benefits?/",
    r"/merchant/",
    r"/dining/",
    r"/travel/",
    r"/shopping/",
]

PROMO_TITLE_KEYWORDS = [
    "promotion", "offer", "deal", "discount", "cashback",
    "credit card", "reward", "privilege", "merchant",
    "% off", "free", "bonus", "exclusive",
]

def pre_filter(url: str, title: str) -> str:
    """Returns 'likely', 'unlikely', or 'uncertain'."""
    url_lower = url.lower()
    title_lower = title.lower()

    # Definite skip patterns
    skip_patterns = ["/careers", "/about-us", "/investor", "/annual-report", "/login"]
    if any(p in url_lower for p in skip_patterns):
        return "unlikely"

    # Likely promo
    if any(re.search(p, url_lower) for p in PROMO_URL_PATTERNS):
        return "likely"
    if any(kw in title_lower for kw in PROMO_TITLE_KEYWORDS):
        return "likely"

    return "uncertain"
```

**Stage 2 — LLM check (only for "uncertain" pages or to confirm "likely" ones):**

```python
RELEVANCE_PROMPT = """You are classifying web pages for a credit card promotions crawler.

Given the following page content, determine if this page contains credit card promotions,
deals, or offers from a bank or financial institution.

A relevant page typically contains:
- Specific credit card offers (e.g., "10% off dining with XYZ Card")
- Merchant partnerships with card discounts
- Cashback or rewards promotions
- Seasonal card promotions

A page is NOT relevant if it:
- Only describes card features/benefits without specific time-limited promotions
- Is a general banking page (account types, interest rates, loans)
- Is a news article mentioning cards without listing specific deals
- Is a terms and conditions page without deal details

Page URL: {url}
Page Title: {title}

Page Content (first 2000 chars):
{content}

Respond with ONLY a JSON object:
{{"is_relevant": true/false, "confidence": 0.0-1.0, "reason": "one sentence explanation"}}
"""
```

### When to Call the LLM

```
URL pre-filter result:
  "likely"    → Optionally confirm with LLM, or pass through directly
  "uncertain" → Always call LLM
  "unlikely"  → Skip LLM, mark as irrelevant
```

This keeps LLM costs down. On a typical bank website, maybe 10-20% of pages are promotion-related, and the URL pre-filter can confidently classify 60-70% of pages without the LLM.

---

## Deal Extraction (Extractor Service) <a id="deal-extraction"></a>

For pages confirmed as relevant, extract structured deal data.

```python
EXTRACTION_PROMPT = """You are extracting structured credit card promotion data from a web page.

Extract ALL individual credit card deals/promotions from this page. Each deal should be a
separate item. If the page contains multiple deals, return all of them.

For each deal, extract:
- bank_name: The bank or financial institution offering the card
- card_name: Specific card name if mentioned (e.g., "Platinum Visa", "Gold Mastercard")
- promotion_title: Short title of the promotion
- description: What the promotion offers
- discount_percentage: Numeric percentage discount, if any
- discount_amount: Fixed dollar/currency amount off, if any
- merchant_name: Specific merchant if this is a merchant deal
- merchant_category: Category (dining, travel, shopping, groceries, fuel, etc.)
- valid_from: Start date in ISO format if mentioned
- valid_until: End date in ISO format if mentioned
- terms_and_conditions: Key terms (minimum spend, max discount, exclusions)

Page URL: {url}
Page Title: {title}

Page Content:
{content}

Respond with ONLY a JSON array of deals:
[
  {{
    "bank_name": "...",
    "card_name": "...",
    "promotion_title": "...",
    "description": "...",
    "discount_percentage": null,
    "discount_amount": null,
    "merchant_name": "...",
    "merchant_category": "...",
    "valid_from": null,
    "valid_until": null,
    "terms_and_conditions": "..."
  }}
]

If no deals can be extracted, return an empty array [].
"""
```

### Content Preparation

Before sending to the LLM, clean the text:

```python
def prepare_for_extraction(raw_text: str, max_chars: int = 8000) -> str:
    """Clean and truncate text for LLM consumption."""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', raw_text).strip()
    # Remove common boilerplate
    text = remove_nav_footer(text)
    # Truncate to avoid token limits
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[Content truncated]"
    return text
```

---

## LLM Client Abstraction <a id="client-abstraction"></a>

Wrap the LLM call behind an abstraction so you can swap providers:

```python
from abc import ABC, abstractmethod

class LLMClient(ABC):
    @abstractmethod
    async def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        ...

class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    async def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        # Use httpx to call the API
        ...

class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        ...

class LocalClient(LLMClient):
    """For local models via Ollama or similar."""
    def __init__(self, base_url: str = "http://localhost:11434"):
        ...
```

---

## Error Handling & Fallbacks <a id="error-handling"></a>

LLM calls can fail (rate limits, timeouts, malformed responses). Handle gracefully:

```python
async def check_relevance_safe(
    llm: LLMClient,
    url: str,
    title: str,
    content: str,
    *,
    max_retries: int = 2,
) -> tuple[bool, float]:
    """Returns (is_relevant, confidence). Defaults to (True, 0.0) on failure
    so the page gets passed to extraction rather than dropped."""
    for attempt in range(max_retries + 1):
        try:
            response = await llm.complete(
                RELEVANCE_PROMPT.format(url=url, title=title, content=content[:2000])
            )
            result = json.loads(response)
            return result["is_relevant"], result["confidence"]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("LLM returned unparseable response for %s: %s", url, e)
        except Exception as e:
            logger.warning("LLM call failed for %s (attempt %d): %s", url, attempt, e)
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)

    # On total failure, assume relevant (false positive is better than missing a deal)
    return True, 0.0
```

---

## Cost Management <a id="cost-management"></a>

LLM calls are the most expensive part of the pipeline. Keep costs under control:

- **Use the cheapest model** that works for relevance checks (gpt-4o-mini, claude-haiku, or a local model)
- **Use a stronger model** for extraction where accuracy matters more
- **Pre-filter aggressively** with URL patterns to minimize LLM calls
- **Truncate content** — 2000 chars is usually enough for relevance; 8000 for extraction
- **Cache results** — if you re-crawl a page and the content hash hasn't changed, reuse the previous LLM result
- **Log token usage** per call so you can track costs over time
