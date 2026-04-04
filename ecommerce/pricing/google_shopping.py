"""
Best Buy Canada and Reebelo Canada price fetching via Google Shopping scraping.

Uses the 'automation-lab/google-shopping-scraper' Apify actor.
Parses results and attributes prices to Best Buy or Reebelo by seller name.
"""

import logging
import re
from ecommerce.pricing import apify_client

log = logging.getLogger(__name__)

ACTOR_ID = 'automation-lab/google-shopping-scraper'

# Seller name patterns for attribution (case-insensitive)
BESTBUY_PATTERNS = ['best buy', 'bestbuy', 'best buy canada', 'bestbuy.ca', 'best buy canada marketplace']
REEBELO_PATTERNS = ['reebelo', 'reebelo.ca', 'reebelo canada']


def _parse_price(price_val):
    """Extract a numeric price from a scraped value (string or number)."""
    if price_val is None:
        return None
    if isinstance(price_val, (int, float)):
        return float(price_val) if price_val > 0 else None
    match = re.search(r'[\d,]+\.?\d*', str(price_val).replace(',', ''))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def _match_seller(seller_name, patterns):
    """Check if a seller name matches any of the given patterns."""
    if not seller_name:
        return False
    seller_lower = seller_name.lower().strip()
    return any(pattern in seller_lower for pattern in patterns)


def scrape_prices(keywords_list):
    """
    Scrape Google Shopping for Best Buy and Reebelo prices via Apify.

    Args:
        keywords_list: list of keyword strings

    Returns:
        tuple of two dicts:
            (bestbuy_prices, reebelo_prices)
        Each maps keyword -> lowest price (float) or keyword -> None.
    """
    if not keywords_list:
        return {}, {}

    log.info("Scraping Google Shopping for %d keywords (Best Buy + Reebelo)...",
             len(keywords_list))

    run_input = {
        'queries': keywords_list,
        'country': 'ca',
        'maxResults': 20,  # results per keyword
    }

    rows = apify_client.run_actor(ACTOR_ID, run_input, timeout_secs=900)
    return _parse_results(rows, keywords_list)


def _parse_results(rows, original_keywords):
    """Parse Google Shopping results and attribute to Best Buy / Reebelo."""
    bestbuy_prices = {kw: None for kw in original_keywords}
    reebelo_prices = {kw: None for kw in original_keywords}

    for row in rows:
        # Find keyword
        keyword = None
        for key in ('query', 'searchTerm', 'keyword', 'Keyword',
                     'search_keyword', 'Query'):
            if key in row and row[key]:
                keyword = str(row[key]).strip()
                break

        if not keyword:
            continue

        # Match to original keyword
        matched_kw = None
        keyword_lower = keyword.lower()
        for orig_kw in original_keywords:
            if orig_kw.lower() == keyword_lower:
                matched_kw = orig_kw
                break

        if not matched_kw:
            continue

        # Get seller name — actor returns 'merchant'
        seller = str(row.get('merchant', '')).strip()
        if not seller:
            continue

        # Extract price — actor returns 'priceNumeric' (float) and 'price' (string)
        price = _parse_price(row.get('priceNumeric') or row.get('price'))
        if not price or price <= 0:
            continue

        # Attribute to Best Buy or Reebelo
        if _match_seller(seller, BESTBUY_PATTERNS):
            if bestbuy_prices[matched_kw] is None or price < bestbuy_prices[matched_kw]:
                bestbuy_prices[matched_kw] = price
                log.info("Best Buy price for '%s': $%.2f (seller: %s)",
                         matched_kw, price, seller)

        elif _match_seller(seller, REEBELO_PATTERNS):
            if reebelo_prices[matched_kw] is None or price < reebelo_prices[matched_kw]:
                reebelo_prices[matched_kw] = price
                log.info("Reebelo price for '%s': $%.2f (seller: %s)",
                         matched_kw, price, seller)

    bb_found = sum(1 for v in bestbuy_prices.values() if v is not None)
    re_found = sum(1 for v in reebelo_prices.values() if v is not None)
    log.info("Google Shopping results: Best Buy %d/%d, Reebelo %d/%d keywords with prices.",
             bb_found, len(original_keywords), re_found, len(original_keywords))

    return bestbuy_prices, reebelo_prices
