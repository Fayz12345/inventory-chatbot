import logging
from ecommerce import config

log = logging.getLogger(__name__)


def select_best_marketplace(prices):
    """
    Deterministic pricing algorithm: pick the marketplace with the highest floor price.

    Args:
        prices: dict mapping marketplace name -> floor price (float or None)
                e.g. {'Amazon': 750.0, 'eBay': 800.0}

    Returns:
        (marketplace, price) tuple, or (None, None) if no valid prices.
    """
    valid = {k: v for k, v in prices.items() if v is not None}
    if not valid:
        return None, None
    best = max(valid, key=valid.get)
    return best, valid[best]


def passes_margin_check(recommended_price, device_cost):
    """
    Sanity check: does the recommended price clear the minimum margin above cost?

    Returns True if price >= cost + minimum margin, False otherwise.
    """
    if device_cost is None or device_cost <= 0:
        return True  # no cost data — allow listing, flag in digest
    return recommended_price >= device_cost + config.MINIMUM_MARGIN


def recommend(product, amazon_price, ebay_price, device_cost):
    """
    Full pricing recommendation for a single product group.

    Returns a dict with the recommendation details:
        {
            'product': <original product dict>,
            'marketplace': 'Amazon' | 'eBay' | None,
            'price': float | None,
            'amazon_price': float | None,
            'ebay_price': float | None,
            'device_cost': float,
            'margin_ok': bool,
            'skip_reason': str | None,
        }
    """
    marketplace, price = select_best_marketplace({
        'Amazon': amazon_price,
        'eBay': ebay_price,
    })

    if marketplace is None:
        return {
            'product': product,
            'marketplace': None,
            'price': None,
            'amazon_price': amazon_price,
            'ebay_price': ebay_price,
            'device_cost': device_cost,
            'margin_ok': False,
            'skip_reason': 'No pricing data available from any marketplace',
        }

    margin_ok = passes_margin_check(price, device_cost)

    return {
        'product': product,
        'marketplace': marketplace,
        'price': price,
        'amazon_price': amazon_price,
        'ebay_price': ebay_price,
        'device_cost': device_cost,
        'margin_ok': margin_ok,
        'skip_reason': None if margin_ok else f'Price ${price:.2f} below cost ${device_cost:.2f} + margin ${config.MINIMUM_MARGIN:.2f}',
    }
