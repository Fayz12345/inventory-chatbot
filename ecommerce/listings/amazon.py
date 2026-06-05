"""
Amazon SP-API listing client (ticket 1D.4 — #136).

`config.AMAZON_ENV` toggles between sandbox and production. Sandbox uses
`sandbox.sellingpartnerapi-na.amazon.com` and returns canned mock responses
(useful for verifying request shape, not for visual confirmation of a listing).
Production hits the real `sellingpartnerapi-na.amazon.com` and creates a real
listing in Amazon Seller Central — so flip `AMAZON_ENV=production` only after
sandbox validation has passed.
"""

import logging

from sp_api.api import ListingsItems
from sp_api.base import Marketplaces, SellingApiException

from ecommerce import config

log = logging.getLogger(__name__)

# Amazon's sandbox endpoint for North America. Same path structure as prod,
# different host. See: developer-docs.amazon.com/sp-api/docs/connecting-to-the-selling-partner-api-sandbox
_SANDBOX_ENDPOINT = "https://sandbox.sellingpartnerapi-na.amazon.com"


def _credentials():
    return {
        "refresh_token":     config.AMAZON_REFRESH_TOKEN,
        "lwa_app_id":        config.AMAZON_LWA_APP_ID,
        "lwa_client_secret": config.AMAZON_LWA_CLIENT_SECRET,
    }


def _marketplace():
    """Always Amazon.ca for this project; toggle is via sandbox flag."""
    return {
        "A2EUQ1WTGCTBG2": Marketplaces.CA,
        "ATVPDKIKX0DER": Marketplaces.US,
    }.get(config.AMAZON_MARKETPLACE_ID, Marketplaces.CA)


def _listings_client():
    """Build a ListingsItems client pointed at sandbox or production."""
    kwargs = {
        "credentials": _credentials(),
        "marketplace": _marketplace(),
    }
    if config.AMAZON_SANDBOX:
        kwargs["endpoint"] = _SANDBOX_ENDPOINT
    return ListingsItems(**kwargs)


def _condition_type(grade):
    """Map internal grade to Amazon condition_type enum."""
    return config.GRADE_CONDITION_MAP.get(grade, {}).get("amazon", "UsedGood")


def _have_creds():
    """All four cred fields must be present for the current env."""
    return all([
        config.AMAZON_SELLER_ID,
        config.AMAZON_REFRESH_TOKEN,
        config.AMAZON_LWA_APP_ID,
        config.AMAZON_LWA_CLIENT_SECRET,
    ])


def create_listing(product, asin, price, listing_copy, seller_sku=None):
    """Create or replace a used-device listing on Amazon.

    Args:
        product: dict with Manufacturer, Model, Colour, Grade, Quantity.
        asin: Amazon ASIN to list against (may be None — Listings API allows
            create-without-ASIN for marketplaces that accept new products).
        price: numeric listing price (CAD).
        listing_copy: dict with at least `condition_note`; `title`/`description`
            are ignored on Amazon (the ASIN owns those).
        seller_sku: optional custom SKU; auto-generated if not provided.

    Returns:
        dict {'ok': True, 'listing_id': seller_sku, 'env': 'sandbox'|'production'}
        on success; {'ok': False, 'error': str} on failure.
    """
    if not _have_creds():
        return {
            "ok": False,
            "error": (
                f"Amazon SP-API ({config.AMAZON_ENV}) credentials not configured "
                f"in .env — set AMAZON_SELLER_ID*, AMAZON_REFRESH_TOKEN*, "
                f"AMAZON_LWA_APP_ID*, AMAZON_LWA_CLIENT_SECRET*."
            ),
        }

    if seller_sku is None:
        seller_sku = (
            f"{product['Manufacturer']}-{product['Model']}-"
            f"{product['Grade']}-{product['Colour']}"
        ).replace(" ", "-").upper()

    condition = _condition_type(product["Grade"])
    condition_note = (listing_copy or {}).get("condition_note", "")

    body = {
        "productType": "WIRELESS_PHONE",
        "requirements": "LISTING",
        "attributes": {
            "condition_type": [{"value": condition}],
            "condition_note": [{"value": condition_note}],
            "purchasable_offer": [{
                "currency": "CAD",
                "our_price": [{"schedule": [{"value_with_tax": price}]}],
            }],
            "fulfillment_availability": [{
                "fulfillment_channel_code": "DEFAULT",
                "quantity": product["Quantity"],
            }],
        },
    }

    try:
        response = _listings_client().put_listings_item(
            sellerId=config.AMAZON_SELLER_ID,
            sku=seller_sku,
            body=body,
        )
        payload = response.payload or {}
        status = payload.get("status", "")
        if status in ("ACCEPTED", "VALID"):
            log.info(
                "Amazon listing posted (%s): SKU=%s ASIN=%s",
                config.AMAZON_ENV, seller_sku, asin,
            )
            return {"ok": True, "listing_id": seller_sku, "env": config.AMAZON_ENV}
        issues = payload.get("issues", [])
        msg = f"Amazon rejected listing (status={status}): {issues}"
        log.error("Amazon listing rejected: %s — %s", seller_sku, issues)
        return {"ok": False, "error": msg}

    except SellingApiException as e:
        log.error("Amazon SP-API error for %s: %s", seller_sku, e)
        return {"ok": False, "error": f"Amazon SP-API error: {e}"}
    except Exception as e:
        log.exception("Unexpected error creating Amazon listing %s", seller_sku)
        return {"ok": False, "error": f"Unexpected error: {e}"}


def delist(seller_sku):
    """Set quantity to 0 to end the listing. Returns bool."""
    if not _have_creds():
        log.warning("Amazon creds missing — skipping delist")
        return False

    body = {
        "productType": "WIRELESS_PHONE",
        "patches": [{
            "op": "replace",
            "path": "/attributes/fulfillment_availability",
            "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": 0}],
        }],
    }
    try:
        _listings_client().patch_listings_item(
            sellerId=config.AMAZON_SELLER_ID,
            sku=seller_sku,
            body=body,
        )
        log.info("Amazon listing delisted (%s): SKU=%s", config.AMAZON_ENV, seller_sku)
        return True
    except Exception as e:
        log.error("Error delisting Amazon SKU %s: %s", seller_sku, e)
        return False
