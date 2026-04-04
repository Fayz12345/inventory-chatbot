"""
Amazon Canada price fetching via Apify cloud scraping.

Uses the 'automation-lab/amazon-scraper' actor to search Amazon.ca
by ASIN (preferred) or keyword (fallback when no ASIN is available).
"""

import logging
import re
from ecommerce.pricing import apify_client

log = logging.getLogger(__name__)

ACTOR_ID = 'automation-lab/amazon-scraper'


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


def scrape_prices(asins):
    """
    Scrape Amazon.ca prices for a list of ASINs via Apify.

    Args:
        asins: list of ASIN strings (e.g. ['B0BDJH7M8H', 'B0CHX3QBCH'])

    Returns:
        dict mapping ASIN -> lowest price (float), or ASIN -> None if not found.
    """
    if not asins:
        return {}

    log.info("Scraping Amazon.ca prices for %d ASINs...", len(asins))

    run_input = {
        'asins': [{'asin': asin, 'country': 'CA'} for asin in asins],
        'maxResults': len(asins),
        'proxyConfiguration': {'useApifyProxy': True},
    }

    rows = apify_client.run_actor(ACTOR_ID, run_input)
    return _parse_asin_results(rows, asins)


def scrape_prices_by_keyword(keywords):
    """
    Scrape Amazon.ca prices by keyword search via Apify (fallback when no ASIN).

    Takes the lowest-priced result per keyword. Less precise than ASIN lookup
    but works for any product without a catalog entry.

    Args:
        keywords: list of keyword strings (e.g. ['Apple iPhone 14 Pro Max'])

    Returns:
        dict mapping keyword -> lowest price (float), or keyword -> None if not found.
    """
    if not keywords:
        return {}

    log.info("Scraping Amazon.ca prices by keyword for %d terms...", len(keywords))

    run_input = {
        'queries': keywords,  # actor expects plain list of strings
        'country': 'CA',
        'maxResults': 5,  # top 5 results per keyword — take the floor
        'proxyConfiguration': {'useApifyProxy': True},
    }

    rows = apify_client.run_actor(ACTOR_ID, run_input)
    return _parse_keyword_results(rows, keywords)


def _parse_asin_results(rows, original_asins):
    """Parse Apify ASIN results into ASIN -> price mapping."""
    prices = {asin: None for asin in original_asins}

    for row in rows:
        asin = None
        for key in ('asin', 'ASIN', 'Asin', 'productAsin'):
            if key in row and row[key]:
                asin = str(row[key]).strip()
                break

        if not asin or asin not in prices:
            continue

        price = _extract_price_from_row(row)
        if price and price > 0:
            if prices[asin] is None or price < prices[asin]:
                prices[asin] = price
                log.info("Amazon price for ASIN %s: $%.2f", asin, price)

    found = sum(1 for v in prices.values() if v is not None)
    log.info("Amazon ASIN scrape: %d/%d with prices.", found, len(original_asins))
    return prices


def _parse_keyword_results(rows, original_keywords):
    """Parse Apify keyword results into keyword -> lowest price mapping."""
    prices = {kw: None for kw in original_keywords}

    for row in rows:
        # Find keyword the result belongs to
        keyword = None
        for key in ('keyword', 'searchKeyword', 'query', 'searchTerm'):
            if key in row and row[key]:
                keyword = str(row[key]).strip()
                break

        if not keyword:
            continue

        matched_kw = None
        keyword_lower = keyword.lower()
        for orig_kw in original_keywords:
            if orig_kw.lower() == keyword_lower:
                matched_kw = orig_kw
                break

        if not matched_kw:
            continue

        price = _extract_price_from_row(row)
        if price and price > 0:
            if prices[matched_kw] is None or price < prices[matched_kw]:
                prices[matched_kw] = price
                log.info("Amazon keyword price for '%s': $%.2f", matched_kw, price)

    found = sum(1 for v in prices.values() if v is not None)
    log.info("Amazon keyword scrape: %d/%d keywords with prices.", found, len(original_keywords))
    return prices


def _extract_price_from_row(row):
    """Extract the best available price from a result row."""
    price = None
    for key in ('price', 'Price', 'currentPrice', 'salePrice',
                'dealPrice', 'priceToBuy'):
        if key in row and row[key]:
            price = _parse_price(row[key])
            if price and price > 0:
                return price

    # Check nested price object
    if isinstance(row.get('price'), dict):
        price = _parse_price(row['price'].get('value'))

    return price
