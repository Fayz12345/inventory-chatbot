"""
Reebelo Canada price fetching via Apify cloud scraping.

Uses the custom 'adminbridge/reebelo-ca-scraper' actor (no public Reebelo actor
exists). It takes `searchQueries` (array) + `minPrice` and returns refurbished
device listings with a numeric `price` in CAD, the matched `query`, plus
condition/storage/color. A single batched call works because the actor echoes
the source `query` in every result row.
"""

import logging

from ecommerce.pricing import apify_client
from ecommerce.pricing.filters import is_accessory

log = logging.getLogger(__name__)

ACTOR_ID = 'adminbridge/reebelo-ca-scraper'

DEFAULT_MIN_PRICE = 30.0

# Reebelo is slow per query (reebelo.ca anti-bot 403s force a fresh proxy IP +
# delay on every query). One giant run over every keyword blows past the actor
# timeout and returns nothing, so scrape in small chunks instead.
CHUNK_SIZE = 10


def scrape_prices(keywords_list, min_price=DEFAULT_MIN_PRICE, max_results=20,
                  chunk_size=CHUNK_SIZE):
    """
    Scrape Reebelo CA for the lowest price per keyword, in small chunks.

    Returns:
        dict mapping keyword -> lowest price (float) or None.
    """
    if not keywords_list:
        return {}

    keywords = list(keywords_list)
    chunks = [keywords[i:i + chunk_size] for i in range(0, len(keywords), chunk_size)]
    log.info("Scraping Reebelo CA for %d keywords in %d chunk(s)...",
             len(keywords), len(chunks))

    all_rows = []
    for idx, chunk in enumerate(chunks, 1):
        run_input = {
            'searchQueries': chunk,
            'maxResults': max_results,
        }
        if min_price is not None:
            run_input['minPrice'] = int(min_price)
        log.info("  Reebelo chunk %d/%d (%d keywords)...", idx, len(chunks), len(chunk))
        rows = apify_client.run_actor(ACTOR_ID, run_input, timeout_secs=900)
        all_rows.extend(rows)

    return _parse_results(all_rows, keywords)


def _parse_results(rows, original_keywords):
    prices = {kw: None for kw in original_keywords}

    for row in rows:
        keyword = row.get('query')
        matched_kw = None
        if keyword:
            keyword_lower = str(keyword).strip().lower()
            for orig_kw in original_keywords:
                if orig_kw.lower() == keyword_lower:
                    matched_kw = orig_kw
                    break
        if not matched_kw:
            continue

        if is_accessory(row.get('title', '')):
            continue

        price = row.get('price')
        if not isinstance(price, (int, float)) or price <= 0:
            continue

        if prices[matched_kw] is None or price < prices[matched_kw]:
            prices[matched_kw] = float(price)

    found = sum(1 for v in prices.values() if v is not None)
    log.info("Reebelo CA: %d/%d keywords with prices.", found, len(original_keywords))
    return prices
