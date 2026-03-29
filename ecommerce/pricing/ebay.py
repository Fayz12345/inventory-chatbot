import logging
import requests
from ecommerce import config

log = logging.getLogger(__name__)

EBAY_AUTH_URL = 'https://api.ebay.com/identity/v1/oauth2/token'
EBAY_BROWSE_URL = 'https://api.ebay.com/buy/browse/v1/item_summary/search'


def _get_access_token():
    """Exchange refresh token for a short-lived access token."""
    if not config.EBAY_REFRESH_TOKEN:
        log.warning("eBay credentials not configured — skipping")
        return None

    response = requests.post(
        EBAY_AUTH_URL,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        auth=(config.EBAY_APP_ID, config.EBAY_CERT_ID),
        data={
            'grant_type': 'refresh_token',
            'refresh_token': config.EBAY_REFRESH_TOKEN,
            'scope': 'https://api.ebay.com/oauth/api_scope/buy.browse',
        },
    )
    response.raise_for_status()
    return response.json()['access_token']


def get_floor_price(keywords, category_id=None):
    """
    Search eBay for the lowest price matching the given keywords.

    Args:
        keywords: search string (e.g. "iPhone 14 128GB Grade A")
        category_id: optional eBay category ID (defaults to config)

    Returns:
        Lowest price as float, or None if no results / credentials missing.
    """
    token = _get_access_token()
    if not token:
        return None

    category_id = category_id or config.EBAY_CATEGORY_ID

    params = {
        'q': keywords,
        'category_ids': category_id,
        'filter': 'buyingOptions:{FIXED_PRICE},conditionIds:{2000|2500|3000}',
        'sort': 'price',
        'limit': '5',
    }
    headers = {
        'Authorization': f'Bearer {token}',
        'X-EBAY-C-MARKETPLACE-ID': config.EBAY_MARKETPLACE_ID,
    }

    try:
        response = requests.get(EBAY_BROWSE_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        items = data.get('itemSummaries', [])
        if not items:
            log.info("No eBay results for: %s", keywords)
            return None

        # Items are sorted by price ascending — first item is the floor
        price_str = items[0].get('price', {}).get('value')
        if price_str:
            return float(price_str)
        return None

    except requests.RequestException as e:
        log.error("eBay API error for '%s': %s", keywords, e)
        return None


def get_prices_for_products(products):
    """
    Fetch eBay floor prices for a list of products.

    Args:
        products: list of dicts with Manufacturer, Model, Grade keys

    Returns:
        dict mapping (Manufacturer, Model, Grade) -> lowest price (float or None)
    """
    results = {}
    for p in products:
        keywords = f"{p['Manufacturer']} {p['Model']} {p.get('Grade', '')}".strip()
        key = (p['Manufacturer'], p['Model'], p['Grade'])
        price = get_floor_price(keywords)
        results[key] = price
        log.info("eBay price for %s: %s", keywords, price)
    return results
