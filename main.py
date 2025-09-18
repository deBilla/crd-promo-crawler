import logging
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Set
import datetime

from playwright.sync_api import sync_playwright, Page, Browser

from scraper import scrape_bank
from models import Promotion

# --- CONFIGURATION & SETUP ---
LOG_FILE = f"crawler_log_{datetime.date.today()}.log"
OUTPUT_FILE = f"bank_promotions_{datetime.date.today()}.json"
MAX_WORKERS = 4 # Number of banks to scrape in parallel

def setup_logging():
    """Sets up logging to both console and file."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(threadName)s] [%(levelname)s] %(message)s", # Added threadName for better logs
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )

def load_config(path="config.json") -> List[Dict]:
    """Loads the bank configurations from a JSON file."""
    with open(path, "r") as f:
        config = json.load(f)
    return config.get("banks", [])

def assign_promotion_ids(promotions: List[Promotion]):
    """Assigns unique, predictable IDs to each promotion."""
    id_counters = {}
    # Sort promotions by bank name to ensure consistent ID assignment
    sorted_promos = sorted(promotions, key=lambda p: p.bank)
    for promo in sorted_promos:
        bank_name = promo.bank
        bank_short_name = "".join(re.findall(r'[A-Z]', bank_name) or bank_name[:3]).lower()
        
        id_counters[bank_name] = id_counters.get(bank_name, 0) + 1
        promo.id = f"po-{bank_short_name}-{id_counters[bank_name]:04d}"

# --- NEW WORKER FUNCTION ---
def run_scraper_task(bank_config: Dict, processed_hashes: Set[int]) -> List[Promotion]:
    """
    A self-contained worker that initializes Playwright, scrapes one bank, and shuts down.
    This function is what each thread will execute.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"
        )
        page = context.new_page()
        try:
            results = scrape_bank(page, bank_config, processed_hashes)
        finally:
            browser.close() # Ensure browser is closed even if errors occur
    return results

# --- MAIN ORCHESTRATOR (MODIFIED) ---
def main():
    setup_logging()
    start_time = time.time()
    logging.info("--- STARTING PROMOTION CRAWLER ---")

    banks_config = load_config()
    if not banks_config:
        logging.error("No bank configurations found in config.json. Exiting.")
        return

    all_promotions = []
    # Using a shared set is tricky with threads. Let's handle deduplication after collection.
    # For now, let's keep it simple and accept potential duplicates that we filter later.
    # A more advanced solution would use a thread-safe set or a manager process.
    processed_hashes = set() 

    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="Scraper") as executor:
        future_to_bank = {
            executor.submit(run_scraper_task, bank, processed_hashes): bank["name"]
            for bank in banks_config
        }

        for future in as_completed(future_to_bank):
            bank_name = future_to_bank[future]
            try:
                results = future.result()
                logging.info(f"Completed scraping for {bank_name}, found {len(results)} promotions.")
                all_promotions.extend(results)
            except Exception as e:
                logging.error(f"A critical error occurred in the task for {bank_name}: {e}", exc_info=True)

    logging.info(f"Total promotions extracted: {len(all_promotions)}")
    
    assign_promotion_ids(all_promotions)
    
    output_data = [promo.dict() for promo in all_promotions]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)

    end_time = time.time()
    logging.info("--- SCRAPING COMPLETE ---")
    logging.info(f"Saved {len(all_promotions)} total offers to {OUTPUT_FILE}")
    logging.info(f"Total execution time: {end_time - start_time:.2f} seconds.")

if __name__ == "__main__":
    main()