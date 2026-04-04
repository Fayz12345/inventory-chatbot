"""
eBay Canada price fetching via Apify cloud scraping.

Uses the 'automation-lab/ebay-scraper' actor to search eBay.ca
by keyword. Results are filtered by condition to match internal grades.

Grade → eBay condition mapping:
    NEW        → "Brand New", "New"
    A+, A      → "Open box", "Seller refurbished", "Excellent - Refurbished"
    B          → "Used", "Very Good - Refurbished", "Good - Refurbished"
    C          → "Used", "Good - Refurbished", "Acceptable"
"""

import logging
import re
from ecommerce.pricing import apify_client

log = logging.getLogger(__name__)

ACTOR_ID = 'automation-lab/ebay-scraper'

# Map internal grades to acceptable eBay condition keywords (case-insensitive)
GRADE_CONDITION_MAP = {
    'NEW': ['new', 'brand new'],
    'A+': ['open box', 'excellent', 'like new', 'seller refurbished',
            'excellent - refurbished', 'certified - refurbished', '9/10', '10/10'],
    'A': ['open box', 'excellent', 'like new', 'seller refurbished',
           'excellent - refurbished', 'certified - refurbished', '9/10', '10/10'],
    'B': ['used', 'very good', 'good - refurbished', 'very good - refurbished',
           'seller refurbished', '8/10', '7/10'],
    'C': ['used', 'good', 'acceptable', 'good - refurbished', '6/10', '5/10'],
}


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


def _condition_matches_grade(ebay_condition, grade):
    """Check if an eBay listing condition is appropriate for our internal grade."""
    if not ebay_condition or not grade:
        return False

    acceptable = GRADE_CONDITION_MAP.get(grade, GRADE_CONDITION_MAP.get('C', []))
    condition_lower = ebay_condition.lower().strip()

    return any(pattern in condition_lower for pattern in acceptable)


def scrape_and_return_all(keywords_list):
    """
    Scrape eBay.ca for a list of search keywords via Apify.
    Returns all raw results grouped by keyword for later condition filtering.

    Args:
        keywords_list: list of keyword strings (product names, no grade)

    Returns:
        dict mapping keyword -> list of result dicts (each with 'price', 'condition', 'title')
    """
    if not keywords_list:
        return {}

    log.info("Scraping eBay.ca prices for %d keywords...", len(keywords_list))

    run_input = {
        'searchQueries': keywords_list,
        'maxResults': 30,  # enough results per keyword to find condition matches
        'site': 'ebay.ca',
    }

    rows = apify_client.run_actor(ACTOR_ID, run_input)
    return _group_by_keyword(rows, keywords_list)


def _group_by_keyword(rows, original_keywords):
    """Group eBay results by matched keyword."""
    grouped = {kw: [] for kw in original_keywords}

    for row in rows:
        title = str(row.get('title', '')).lower()

        # Match to original keyword by checking if key parts appear in title
        matched_kw = None
        best_match_count = 0
        for kw in original_keywords:
            kw_parts = kw.lower().split()
            match_count = sum(1 for part in kw_parts if part in title)
            if match_count > best_match_count and match_count >= len(kw_parts) * 0.6:
                best_match_count = match_count
                matched_kw = kw

        if matched_kw:
            grouped[matched_kw].append(row)

    for kw, items in grouped.items():
        log.info("eBay: %d results for '%s'", len(items), kw)

    return grouped


def get_floor_price_for_grade(grouped_results, keyword, grade):
    """
    Get the lowest eBay price for a keyword filtered by condition matching the grade.

    Args:
        grouped_results: dict from scrape_and_return_all()
        keyword: product search keyword (no grade)
        grade: internal grade (NEW, A+, A, B, C)

    Returns:
        float (lowest matching price) or None
    """
    items = grouped_results.get(keyword, [])
    if not items:
        return None

    floor_price = None
    for item in items:
        condition = item.get('condition', '')
        price = _parse_price(item.get('price'))

        if not price or price <= 0:
            continue

        # Skip obviously wrong items (accessories, parts, cases)
        # by filtering out very low prices relative to phones/devices
        if price < 20:
            continue

        if _condition_matches_grade(condition, grade):
            if floor_price is None or price < floor_price:
                floor_price = price

    if floor_price:
        log.info("eBay floor for '%s' Grade %s: $%.2f", keyword, grade, floor_price)
    else:
        log.info("eBay: no condition-matched results for '%s' Grade %s", keyword, grade)

    return floor_price
