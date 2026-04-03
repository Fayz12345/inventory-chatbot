"""
Best Buy Canada and Reebelo Canada price fetching via Google Shopping scraping.

Uses the 'google-shopping-product-listing-scraper' Octoparse template.
Parses results and attributes prices to Best Buy or Reebelo by seller name.
"""

import logging
import re
from ecommerce.pricing import octoparse_client

log = logging.getLogger(__name__)

TEMPLATE = 'google-shopping-product-listing-scraper'

# Seller name patterns for attribution (case-insensitive)
BESTBUY_PATTERNS = ['best buy', 'bestbuy', 'best buy canada', 'bestbuy.ca']
REEBELO_PATTERNS = ['reebelo', 'reebelo.ca', 'reebelo canada']


def _parse_price(price_str):
    """Extract a numeric price from a scraped string like 'C$749.99' or '$749.99'."""
    if not price_str:
        return None
    match = re.search(r'[\d,]+\.?\d*', str(price_str).replace(',', ''))
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
    Scrape Google Shopping for Best Buy and Reebelo prices.

    Args:
        keywords_list: list of keyword strings
                       (e.g. ['iPhone 14 128GB', 'Samsung S24 256GB'])

    Returns:
        tuple of two dicts:
            (bestbuy_prices, reebelo_prices)
        Each maps keyword -> lowest price (float) or keyword -> None.
    """
    if not keywords_list:
        return {}, {}

    parameters = {
        'bur6xb09mnl.List': keywords_list,
    }

    log.info("Scraping Google Shopping for %d keywords (Best Buy + Reebelo)...",
             len(keywords_list))
    rows = octoparse_client.scrape(
        template_name=TEMPLATE,
        parameters=parameters,
        task_name=f'Google Shopping CA Scan ({len(keywords_list)} keywords)',
        target_max_rows=len(keywords_list) * 20,  # ~20 results per keyword
    )

    return _parse_results(rows, keywords_list)


def _parse_results(rows, original_keywords):
    """
    Parse Google Shopping results and attribute to Best Buy / Reebelo by seller name.

    Returns:
        tuple of (bestbuy_prices, reebelo_prices) dicts.
    """
    bestbuy_prices = {kw: None for kw in original_keywords}
    reebelo_prices = {kw: None for kw in original_keywords}

    for row in rows:
        # Find keyword
        keyword = None
        for key in ('Keyword', 'keyword', 'Search Keyword', 'search_keyword',
                     'Query', 'query'):
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

        # Get seller name
        seller = None
        for key in ('Seller', 'seller', 'Store', 'store', 'Shop', 'shop',
                     'Merchant', 'merchant', 'Source'):
            if key in row and row[key]:
                seller = str(row[key]).strip()
                break

        if not seller:
            continue

        # Extract price
        price = None
        for key in ('Price', 'price', 'Current Price', 'Sale Price',
                     'Discounted Price', 'Total Price'):
            if key in row and row[key]:
                price = _parse_price(row[key])
                if price and price > 0:
                    break

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


def get_prices_for_products(products):
    """
    Fetch Best Buy and Reebelo floor prices for a list of products.

    Args:
        products: list of dicts with Manufacturer, Model, Grade keys

    Returns:
        tuple of two dicts:
            (bestbuy_prices, reebelo_prices)
        Each maps (Manufacturer, Model, Grade) -> lowest price (float or None).
    """
    keyword_map = {}
    for p in products:
        keywords = f"{p['Manufacturer']} {p['Model']} {p.get('Grade', '')}".strip()
        key = (p['Manufacturer'], p['Model'], p['Grade'])
        keyword_map[keywords] = key

    if not keyword_map:
        return {}, {}

    raw_bb, raw_re = scrape_prices(list(keyword_map.keys()))

    bestbuy = {}
    reebelo = {}
    for keywords, product_key in keyword_map.items():
        bestbuy[product_key] = raw_bb.get(keywords)
        reebelo[product_key] = raw_re.get(keywords)

    return bestbuy, reebelo
