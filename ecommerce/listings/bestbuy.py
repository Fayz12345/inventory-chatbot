"""
Best Buy Canada Marketplace (Mirakl) listing client (ticket 1D.11).

Best Buy CA runs on Mirakl. There is a SINGLE production instance
(`marketplace.bestbuy.ca/api`) — no sandbox — so creating an offer posts a
REAL listing. Auth is the front API key in the `Authorization` header.

Two Mirakl facts that shape this module (confirmed live against the account):
  - Only state_code "11" (New) is offered, so used-device grade is carried in
    the offer `description` (matching the existing seller pattern, e.g.
    "A grade - HSO").
  - An offer must match a Best Buy catalog product, referenced here by UPC
    (`product_references` of type UPC-A). Products without a UPC in
    EcommerceProductCatalog can't be matched — same gap as Amazon's ASIN, so
    the dispatcher keeps those preview-only.

Offer create/update is asynchronous: POST /api/offers returns an import_id; we
poll GET /api/offers/imports/{id} to confirm it processed without errors.

NOTE: the read path (auth, base URL, offer/account shape) is live-verified. The
POST /api/offers + import-poll contract follows the Mirakl Offers API and should
be confirmed with one real offer before it's relied on in production.
"""

import logging
import time

import requests

from ecommerce import config

log = logging.getLogger(__name__)

_POLL_ATTEMPTS = 10
_POLL_INTERVAL = 2  # seconds


def _headers():
    return {"Authorization": config.BESTBUY_API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json"}


def _have_creds():
    return bool(config.BESTBUY_API_KEY and config.BESTBUY_API_BASE)


def _description(product, listing_copy):
    """Best Buy only offers state 'New', so the grade is conveyed in text."""
    note = (listing_copy or {}).get("condition_note", "")
    grade = product.get("Grade", "")
    parts = [p for p in (f"Grade {grade}" if grade else "", note) if p]
    return " - ".join(parts) or "Refurbished"


def _shop_sku(product):
    return (
        f"{product['Manufacturer']}-{product['Model']}-"
        f"{product['Grade']}-{product['Colour']}"
    ).replace(" ", "-").upper()


def _poll_import(import_id):
    """Poll an offer import until it finishes. Returns (ok, detail)."""
    url = f"{config.BESTBUY_API_BASE}/offers/imports/{import_id}"
    for _ in range(_POLL_ATTEMPTS):
        r = requests.get(url, headers=_headers(), timeout=30)
        if r.status_code != 200:
            return False, f"import status check failed: {r.status_code} {r.text[:200]}"
        data = r.json()
        status = (data.get("status") or "").upper()
        if status in ("COMPLETE", "COMPLETED"):
            errors = data.get("lines_in_error", 0)
            if errors:
                return False, f"offer rejected ({errors} line error(s)): {data}"
            return True, data
        if status in ("FAILED", "CANCELLED"):
            return False, f"import {status}: {data}"
        time.sleep(_POLL_INTERVAL)
    return False, f"offer import {import_id} not confirmed after " \
                  f"{_POLL_ATTEMPTS * _POLL_INTERVAL}s — check Mirakl"


def create_listing(product, price, listing_copy, catalog_info=None):
    """Create/update a Best Buy (Mirakl) offer.

    Returns {'ok': True, 'listing_id': shop_sku, 'env': 'production'} on success;
    {'ok': False, 'error': str} on failure. The caller keeps products with no
    UPC match preview-only, so this expects a UPC in catalog_info.
    """
    if not _have_creds():
        return {"ok": False, "error": "Best Buy (Mirakl) API key not configured in .env "
                                      "— set BESTBUY_API_KEY."}

    upc = (catalog_info or {}).get("upc")
    if not upc:
        return {"ok": False, "error": "No Best Buy product match (UPC) — populate "
                                      "EcommerceProductCatalog (1D.1) before auto-posting."}

    shop_sku = _shop_sku(product)
    offer = {
        "shop_sku":         shop_sku,
        "product_id":       upc,
        "product_id_type":  config.BESTBUY_PRODUCT_ID_TYPE,
        "price":            float(price),
        "quantity":         product["Quantity"],
        "state_code":       config.BESTBUY_STATE_CODE,
        "description":      _description(product, listing_copy),
        "logistic_class":   config.BESTBUY_LOGISTIC_CLASS,
        "leadtime_to_ship": config.BESTBUY_LEADTIME_TO_SHIP,
        "update_delete":    "update",
    }

    try:
        r = requests.post(
            f"{config.BESTBUY_API_BASE}/offers",
            headers=_headers(), json={"offers": [offer]}, timeout=30,
        )
        if r.status_code not in (200, 201):
            return {"ok": False, "error": f"Best Buy offer submit failed: "
                                          f"{r.status_code} {r.text[:300]}"}
        import_id = r.json().get("import_id")
        if not import_id:
            return {"ok": False, "error": f"Best Buy offer submit returned no import_id: {r.text[:200]}"}

        ok, detail = _poll_import(import_id)
        if not ok:
            log.error("Best Buy offer %s not accepted: %s", shop_sku, detail)
            return {"ok": False, "error": f"Best Buy offer not accepted: {detail}"}

        log.info("Best Buy offer posted (production): shop_sku=%s import=%s", shop_sku, import_id)
        return {"ok": True, "listing_id": shop_sku, "env": "production"}

    except requests.RequestException as e:
        log.error("Best Buy API error for %s: %s", shop_sku, e)
        return {"ok": False, "error": f"Best Buy API error: {e}"}


def delist(shop_sku):
    """End a Best Buy offer by setting its quantity to 0. Returns bool."""
    if not _have_creds():
        log.warning("Best Buy creds missing — skipping delist")
        return False
    offer = {
        "shop_sku":      shop_sku,
        "product_id":    shop_sku,
        "product_id_type": "SHOP_SKU",
        "quantity":      0,
        "update_delete": "update",
    }
    try:
        r = requests.post(
            f"{config.BESTBUY_API_BASE}/offers",
            headers=_headers(), json={"offers": [offer]}, timeout=30,
        )
        if r.status_code in (200, 201):
            log.info("Best Buy offer withdrawn (production): shop_sku=%s", shop_sku)
            return True
        log.error("Best Buy delist failed: %s %s", r.status_code, r.text[:200])
        return False
    except requests.RequestException as e:
        log.error("Best Buy API error delisting %s: %s", shop_sku, e)
        return False
