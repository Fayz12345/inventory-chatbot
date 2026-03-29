import logging
import time
from sp_api.api import ProductPricing
from sp_api.base import Marketplaces, SellingApiException
from ecommerce import config

log = logging.getLogger(__name__)

# Amazon SP-API rate limit: 0.5 req/sec → 2s between calls
RATE_LIMIT_DELAY = 2.0


def _get_credentials():
    return {
        'refresh_token': config.AMAZON_REFRESH_TOKEN,
        'lwa_app_id': config.AMAZON_LWA_APP_ID,
        'lwa_client_secret': config.AMAZON_LWA_CLIENT_SECRET,
    }


def _get_marketplace():
    marketplace_map = {
        'A2EUQ1WTGCTBG2': Marketplaces.CA,
        'ATVPDKIKX0DER': Marketplaces.US,
    }
    return marketplace_map.get(config.AMAZON_MARKETPLACE_ID, Marketplaces.CA)


def get_competitive_price(asin):
    """
    Fetch the lowest competitive price for an ASIN on Amazon.

    Returns the lowest landed price (float) or None if unavailable.
    """
    if not config.AMAZON_REFRESH_TOKEN:
        log.warning("Amazon SP-API credentials not configured — skipping")
        return None

    try:
        pricing_api = ProductPricing(
            credentials=_get_credentials(),
            marketplace=_get_marketplace(),
        )
        response = pricing_api.get_competitive_pricing_for_asins([asin])
        time.sleep(RATE_LIMIT_DELAY)

        for product in response.payload:
            competitive_prices = product.get('Product', {}).get(
                'CompetitivePricing', {}
            ).get('CompetitivePrices', [])
            for cp in competitive_prices:
                price_obj = cp.get('Price', {})
                landed = price_obj.get('LandedPrice', {}).get('Amount')
                if landed is not None:
                    return float(landed)
        return None

    except SellingApiException as e:
        log.error("Amazon SP-API error for ASIN %s: %s", asin, e)
        return None
    except Exception as e:
        log.error("Unexpected error fetching Amazon price for ASIN %s: %s", asin, e)
        return None


def get_prices_for_products(products_with_asins):
    """
    Fetch Amazon floor prices for a list of products.

    Args:
        products_with_asins: list of dicts, each with at least 'asin' key

    Returns:
        dict mapping asin -> lowest price (float or None)
    """
    results = {}
    for item in products_with_asins:
        asin = item.get('asin')
        if not asin:
            continue
        price = get_competitive_price(asin)
        results[asin] = price
        log.info("Amazon price for %s: %s", asin, price)
    return results
