import logging
import json
import time
from enum import Enum, auto
from urllib.parse import urljoin
from typing import Dict, List, Set, Callable

import ollama
from playwright.sync_api import Page, TimeoutError
from pydantic import ValidationError, BaseModel, HttpUrl
from typing import Optional

from models import Promotion, Merchant, OfferDetails, Validity, CANONICAL_CATEGORIES, VALID_CARD_TYPES

PROGRESS_FILE = "processed_urls.log"

# --- Mock models for demonstration ---
VALID_CARD_TYPES = ["Credit", "Debit"]
CANONICAL_CATEGORIES = ["Groceries & Supermarkets", "Dining & Restaurants", "Shopping & Retail", 
                        "Travel & Lodging", "Health & Wellness", "Online Shopping", "Other"]

# Crawl strategy enum
class CrawlStrategy(Enum):
    STATIC = auto()
    PREDEFINED_PAGES = auto()
    CATEGORY_DISCOVERY = auto()
    LOAD_MORE_BUTTON = auto()
    INFINITE_SCROLL = auto()
    PAGINATION = auto()

STRATEGY_MAP = {
    "static": CrawlStrategy.STATIC,
    "predefined_pages": CrawlStrategy.PREDEFINED_PAGES,
    "category_discovery": CrawlStrategy.CATEGORY_DISCOVERY,
    "load_more_button": CrawlStrategy.LOAD_MORE_BUTTON,
    "infinite_scroll": CrawlStrategy.INFINITE_SCROLL,
    "pagination": CrawlStrategy.PAGINATION
}

# --- AI Extraction with Retry ---
MAX_RETRIES = 2

def load_processed_urls(filepath: str) -> Set[str]:
    """Loads successfully scraped URLs from the progress file into a set for fast lookups."""
    try:
        with open(filepath, 'r') as f:
            # Use a set to automatically handle duplicates and provide O(1) lookup time
            return set(line.strip() for line in f)
    except FileNotFoundError:
        # If the file doesn't exist yet (first run), return an empty set
        return set()

def save_processed_url(filepath: str, url: str):
    """Appends a successfully scraped URL to the progress file."""
    # 'a' mode stands for append, which adds the line to the end of the file
    with open(filepath, 'a') as f:
        f.write(url + '\n')

def extract_with_ai(text: str, source_url: str, bank: str, scraped_category: str) -> Promotion | None:
    """
    Uses Llama 3 to extract a single promotion JSON from text.
    """
    prompt = f"""
You are an expert data extraction engine. From the promotional text below, create a SINGLE, VALID JSON object.
Adhere strictly to this schema. If a value is not found, use null. DO NOT invent data.

Schema:
- "bank": string (e.g., "{bank}")
- "card_types": Array of strings from {VALID_CARD_TYPES}
- "category": Choose ONE from {CANONICAL_CATEGORIES}
- "merchant": {{ "name": "string", "logo_url": "URL or null" }}
- "title": "Short, catchy title"
- "description": "Concise one-sentence summary"
- "offer_details": {{ "type": "percentage" | "fixed_amount" | "buy_one_get_one" | "other", "value": number or null, "max_discount_lkr": number or null }}
- "validity": {{ "start_date": "YYYY-MM-DD" or null, "end_date": "YYYY-MM-DD" or null, "days": ["Monday"] or null }}
- "location": {{ "address": "string or null", "latitude": float or null, "longitude": float or null }}
- "terms": "Brief summary of key terms"
- "source_url": "{source_url}"

Map the scraped category '{scraped_category}' to the canonical category list.
Extract strictly from the text provided. Text length limit: 4000 chars.

PROMOTIONAL TEXT:
\"\"\"{text[:4000]}\"\"\"

Return **only** a single valid JSON object.
"""
    last_response = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = ollama.generate(
                model="llama3.1",
                prompt=prompt,
                format="json",
                stream=False
            )
            last_response = response
            data = json.loads(response.get("response", "{}"))
            promotion = Promotion(**data)
            return promotion

        except (ValidationError, json.JSONDecodeError) as e:
            logging.warning(f"[Attempt {attempt}] AI extraction failed for bank {bank}, category {scraped_category}: {e}")
            logging.debug(f"Text snippet:\n{text[:500]}")
            if last_response:
                # Optional: prompt LLM to fix previous JSON
                correction_prompt = f"""
Previous AI output was invalid JSON:
{last_response.get('response', '')}

Please correct it to match the required schema exactly.
"""
                try:
                    last_response = ollama.generate(
                        model="llama3.1",
                        prompt=correction_prompt,
                        format="json",
                        stream=False
                    )
                except Exception as inner_e:
                    logging.error(f"Failed to correct JSON with LLM: {inner_e}")
            time.sleep(0.5)
        except Exception as e:
            logging.error(f"Unexpected error during AI extraction for bank {bank}: {e}")
            break
    return None

# --- Page Interaction Handlers ---
def handle_load_more(page: Page, selector: str):
    while True:
        try:
            button = page.locator(selector)
            if button.is_visible(timeout=5000) and button.is_enabled(timeout=5000):
                button.click()
                page.wait_for_load_state("networkidle", timeout=10000)
            else:
                break
        except TimeoutError:
            break
        except Exception:
            break

def handle_infinite_scroll(page: Page, pause_time: int = 2):
    last_height = page.evaluate("document.body.scrollHeight")
    while True:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except TimeoutError:
            pass
        time.sleep(pause_time)
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def handle_pagination(page: Page, selector: str, scrape_func: Callable):
    page_count = 1
    while True:
        scrape_func()
        try:
            next_button = page.locator(selector)
            if next_button.is_visible(timeout=5000) and next_button.is_enabled(timeout=5000):
                next_button.click()
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                page_count += 1
            else:
                break
        except TimeoutError:
            break
        except Exception:
            break

# --- Core Scraping Logic ---
def get_pages_to_scan(page: Page, config: Dict) -> List[tuple[str, str]]:
    strategy_str = config.get("crawl_strategy", "static")
    strategy = STRATEGY_MAP.get(strategy_str)
    base_url = config["url"]
    
    if strategy in [CrawlStrategy.STATIC, CrawlStrategy.PREDEFINED_PAGES, 
                    CrawlStrategy.LOAD_MORE_BUTTON, CrawlStrategy.INFINITE_SCROLL]:
        pages = config.get("pages", [{"url": base_url, "category": "General"}])
        return [(p["url"], p["category"]) for p in pages]

    elif strategy in [CrawlStrategy.CATEGORY_DISCOVERY, CrawlStrategy.PAGINATION]:
        pages_to_scan = []
        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=60000)
            container_selector = config["category_container_selector"]
            page.wait_for_selector(container_selector, state="visible", timeout=30000)
            
            category_cards = page.locator(container_selector).all()
            for card in category_cards:
                try:
                    name = card.locator(config["category_name_selector"]).inner_text().strip()
                    link = card.locator(config["category_link_selector"]).get_attribute("href")
                    if name and link:
                        pages_to_scan.append((urljoin(base_url, link), name))
                except Exception:
                    continue
            if not pages_to_scan and strategy == CrawlStrategy.PAGINATION:
                return [(base_url, "General")]
            return pages_to_scan

        except Exception as e:
            logging.error(f"Failed to discover categories for {config['name']}: {e}")
            return [(base_url, "General")]
    return []

def scrape_bank(page: Page, bank_config: Dict, processed_hashes: Set[int]) -> List[Promotion]:
    bank_name = bank_config["name"]
    card_selector = bank_config["card_selector"]
    strategy_str = bank_config.get("crawl_strategy", "static")
    strategy = STRATEGY_MAP.get(strategy_str)
    results: List[Promotion] = []

    processed_urls = load_processed_urls(PROGRESS_FILE)
    logging.info(f"Loaded {len(processed_urls)} previously processed URLs. They will be skipped.")

    pages_to_scan = get_pages_to_scan(page, bank_config)
    if not pages_to_scan:
        return []

    for page_url, category_name in pages_to_scan:
        def scrape_page_offers():
            nonlocal results
            promo_cards = page.locator(card_selector).all()
            for card in promo_cards:
                if page_url in processed_urls:
                    logging.info(f"Skipping already processed URL: {page_url}")
                    continue  # Move to the next URL
                try:
                    text_to_process = card.text_content().strip().replace('\n', ' ')
                    if len(text_to_process) < 25: continue
                    item_hash = hash(text_to_process[:150])
                    if item_hash in processed_hashes: continue
                    processed_hashes.add(item_hash)
                    link_element = card.locator("a").first
                    link = link_element.get_attribute("href") if link_element.count() > 0 else page_url
                    full_link = urljoin(page_url, link)
                    promotion_data = extract_with_ai(text_to_process, full_link, bank_name, category_name)
                    if promotion_data and promotion_data.merchant and promotion_data.merchant.name:
                        results.append(promotion_data)
                except Exception:
                    continue

        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
            if strategy == CrawlStrategy.LOAD_MORE_BUTTON:
                handle_load_more(page, bank_config["load_more_selector"])
            elif strategy == CrawlStrategy.INFINITE_SCROLL:
                handle_infinite_scroll(page)
            if strategy == CrawlStrategy.PAGINATION:
                handle_pagination(page, bank_config["pagination_selector"], scrape_page_offers)
            else:
                page.wait_for_selector(card_selector, state="visible", timeout=30000)
                scrape_page_offers()

                save_processed_url(PROGRESS_FILE, page_url)
                logging.info(f"Successfully processed and logged: {page_url}")
        except TimeoutError:
            logging.warning(f"Selector '{card_selector}' not found on {page_url}.")
        except Exception as e:
            logging.error(f"Critical error on {page_url}: {e}")
        time.sleep(1)
    return results
