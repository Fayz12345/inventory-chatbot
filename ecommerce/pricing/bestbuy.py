"""
Best Buy Canada competitor pricing via the Mirakl seller API (endpoint P11).

Replaces the Google Shopping Apify actor as the Best Buy price source. That actor
was ~66% of the ecommerce Apify bill and the least reliable of the four (see
docs/apify-cost-optimization.md); P11 is a plain read-only REST GET at $0 Apify cost.

`GET /api/products/offers?product_references=UPC-A|<upc>&all_offers=<bool>` returns
every marketplace seller's offer for a Best Buy catalog product, matched by UPC. The
offers are third-party open-box / refurbished resellers priced in CAD — the right
competitor set for our used devices. We take the lowest total price (price + shipping)
across the offers as the Best Buy floor.

Auth reuses the same production key as ecommerce/listings/bestbuy.py — Best Buy CA is a
single production instance with no sandbox, but this path is strictly read-only (GET),
so it never mutates a listing.
"""

import logging
import time

import requests

from ecommerce import config

log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30       # seconds, matches listings/bestbuy.py
REQUEST_DELAY = 0.4        # seconds between per-UPC calls (rate-limit courtesy)
RETRIES = 2                # extra attempts on 429/5xx/network before giving up

# When the in-stock (active) lookup yields fewer offers than this, retry once with
# all_offers=true. Best Buy resellers frequently sit at ZERO_QUANTITY (inactive) yet
# still advertise a price, so without the fallback coverage is near zero.
ACTIVE_MIN_OFFERS = 1


class _AuthError(Exception):
    """Raised on a 401/403 so a bad/unscoped key stops the whole run early."""


def valid_upc(upc):
    """True if `upc` looks like a real GTIN we can query Best Buy with.

    Rejects blanks, non-numeric values, out-of-range lengths, and the known
    '999...' internal placeholders seeded into EcommerceProductCatalog.
    """
    if not upc:
        return False
    u = str(upc).strip()
    if not u.isdigit() or not (10 <= len(u) <= 14):
        return False
    if u.startswith('999') or set(u) == {'9'}:
        return False
    return True


def _headers():
    # GET only — no Content-Type needed (mirrors listings/bestbuy.py auth).
    return {"Authorization": config.BESTBUY_API_KEY, "Accept": "application/json"}


def _have_creds():
    return bool(config.BESTBUY_API_KEY and config.BESTBUY_API_BASE)


def fetch_prices(upc_list):
    """Fetch the Best Buy competitive floor price for each UPC via Mirakl P11.

    Returns:
        dict mapping upc -> lowest total price (float) or None.
    """
    upcs = [u for u in dict.fromkeys(upc_list or []) if valid_upc(u)]
    prices = {u: None for u in upcs}
    if not upcs:
        return prices

    if not _have_creds():
        log.warning("Best Buy (Mirakl) API key not configured — skipping Best Buy "
                    "pricing for %d UPC(s).", len(upcs))
        return prices

    log.info("Fetching Best Buy CA prices via Mirakl P11 for %d UPC(s)...", len(upcs))
    for idx, upc in enumerate(upcs):
        if idx:
            time.sleep(REQUEST_DELAY)
        try:
            offers = _fetch_offers(upc, all_offers=False)
            mode = "active"
            if offers is not None and len(offers) < ACTIVE_MIN_OFFERS:
                fallback = _fetch_offers(upc, all_offers=True)
                if fallback is not None:
                    offers, mode = fallback, "all_offers"
        except _AuthError as e:
            log.error("Best Buy P11 auth failed (%s) — aborting Best Buy pricing; "
                      "check BESTBUY_API_KEY scope.", e)
            break

        if offers is None:
            continue  # request failed (already logged)
        if not offers:
            log.info("Best Buy CA: no offers for UPC %s (not in catalog).", upc)
            continue

        floor = _floor_from_offers(offers)
        if floor is not None:
            prices[upc] = floor
            log.info("Best Buy CA floor for UPC %s: $%.2f (%s, %d offer(s)).",
                     upc, floor, mode, len(offers))

    found = sum(1 for v in prices.values() if v is not None)
    log.info("Best Buy CA (Mirakl P11): %d/%d UPCs with prices.", found, len(upcs))
    return prices


def _fetch_offers(upc, all_offers):
    """One P11 GET. Returns the flattened offers list (possibly empty) on success,
    or None on a transient failure. Raises _AuthError on 401/403."""
    params = {
        "product_references": f"{config.BESTBUY_PRODUCT_ID_TYPE}|{upc}",
        "all_offers": "true" if all_offers else "false",
    }
    url = f"{config.BESTBUY_API_BASE}/products/offers"
    for attempt in range(RETRIES + 1):
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            if attempt < RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            log.warning("Best Buy P11 request error for UPC %s: %s", upc, e)
            return None

        if r.status_code in (401, 403):
            raise _AuthError(f"{r.status_code} {r.text[:120]}")
        if r.status_code == 429 or r.status_code >= 500:
            if attempt < RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            log.warning("Best Buy P11 HTTP %s for UPC %s (giving up).", r.status_code, upc)
            return None
        if r.status_code != 200:
            log.warning("Best Buy P11 HTTP %s for UPC %s: %s", r.status_code, upc, r.text[:120])
            return None

        try:
            data = r.json()
        except ValueError:
            log.warning("Best Buy P11 non-JSON body for UPC %s.", upc)
            return None

        offers = []
        for product in (data.get("products") or []):
            offers.extend(product.get("offers") or [])
        return offers
    return None


def _floor_from_offers(offers):
    """Lowest total price (price + shipping) across the offers, in CAD."""
    floor = None
    for offer in offers:
        price = _offer_price(offer)
        if price is None or price <= 0:
            continue
        currency = offer.get("currency_iso_code")
        if currency and currency != "CAD":
            continue
        if floor is None or price < floor:
            floor = price
    return floor


def _offer_price(offer):
    """A single offer's total price. Prefers `total_price`, then price+shipping,
    then the applicable_pricing block."""
    total = offer.get("total_price")
    if isinstance(total, (int, float)):
        return float(total)

    price = offer.get("price")
    if isinstance(price, (int, float)):
        shipping = offer.get("min_shipping_price")
        shipping = float(shipping) if isinstance(shipping, (int, float)) else 0.0
        return float(price) + shipping

    applicable = offer.get("applicable_pricing") or {}
    ap_price = applicable.get("price")
    if isinstance(ap_price, (int, float)):
        return float(ap_price)
    return None
