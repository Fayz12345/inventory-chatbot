"""
Reebelo ("Cobalt") listing client (ticket 1D.12).

Reebelo's seller API is a single synchronous endpoint:
    POST {base}/sockets/offers/update   (create OR update; batch under "data")
Auth is a static API key in the `x-api-key` header. Base URL is env-specific:
sandbox `https://a.reebelo.blue`, production `https://a.reebelo.com`.

Offer fields: `sku` (required), `name` (required on create), `price`, `stock`
(= quantity), `minPrice` (optional repricer floor). The response buckets each
SKU into updatedOffers / skippedOffers (reason `unchanged` | `vendor_deactivated`)
/ failedOffers (reason `internal_error`, retryable).

TWO THINGS UNCONFIRMED in Reebelo's docs (confirm with Reebelo before prod):
  1. No documented delist/end endpoint — we use stock:0, which is the likely
     mechanism but not documented as such.
  2. No condition/grade field — grade is encoded into the offer `name` (e.g.
     "Samsung Galaxy S21 Black - Grade A") until Reebelo confirms a real field
     or it's set during SKU onboarding.

Built from the docs at cobalt.reebelo.com/documentation/custom-api; NOT yet
validated against a live key (sandbox pending).
"""

import logging

import requests

from ecommerce import config

log = logging.getLogger(__name__)


def _headers():
    return {"x-api-key": config.REEBELO_API_KEY,
            "Content-Type": "application/json"}


def _have_creds():
    return bool(config.REEBELO_API_KEY and config.REEBELO_API_BASE)


def _sku(product):
    return (
        f"{product['Manufacturer']}-{product['Model']}-"
        f"{product['Grade']}-{product['Colour']}"
    ).replace(" ", "-").upper()


def _name(product):
    """Human-readable offer name; grade is encoded here since Cobalt has no
    condition field."""
    base = f"{product['Manufacturer']} {product['Model']} {product['Colour']}".strip()
    grade = product.get("Grade")
    return f"{base} - Grade {grade}" if grade else base


def _find(buckets, key, sku):
    for o in buckets.get(key, []) or []:
        if (o.get("sku") if isinstance(o, dict) else o) == sku:
            return o if isinstance(o, dict) else {"sku": sku}
    return None


def create_listing(product, price, listing_copy, catalog_info=None):
    """Create/update a Reebelo offer.

    Returns {'ok': True, 'listing_id': sku, 'env': 'sandbox'|'production'} on
    success; {'ok': False, 'error': str} on failure.
    """
    if not _have_creds():
        return {"ok": False, "error": "Reebelo (Cobalt) API key not configured in .env "
                                      "— set REEBELO_API_KEY*."}

    sku = _sku(product)
    payload = {"data": [{
        "sku":   sku,
        "name":  _name(product),
        "price": float(price),
        "stock": product["Quantity"],
    }]}

    try:
        r = requests.post(
            f"{config.REEBELO_API_BASE}/sockets/offers/update",
            headers=_headers(), json=payload, timeout=30,
        )
        if r.status_code not in (200, 201):
            return {"ok": False, "error": f"Reebelo offer update failed: "
                                          f"{r.status_code} {r.text[:300]}"}
        data = r.json()
        env = "sandbox" if config.REEBELO_SANDBOX else "production"

        if _find(data, "updatedOffers", sku):
            log.info("Reebelo offer posted (%s): sku=%s", env, sku)
            return {"ok": True, "listing_id": sku, "env": env}

        skipped = _find(data, "skippedOffers", sku)
        if skipped:
            reason = skipped.get("reason", "")
            if reason == "unchanged":   # already at this price/stock — treat as success
                return {"ok": True, "listing_id": sku, "env": env}
            return {"ok": False, "error": f"Reebelo skipped offer ({reason or 'unknown'}) — "
                                          f"check the SKU is active/onboarded."}

        failed = _find(data, "failedOffers", sku)
        if failed:
            return {"ok": False, "error": f"Reebelo offer failed ({failed.get('reason', 'error')}) "
                                          f"— retryable. requestId={data.get('requestId')}"}

        return {"ok": False, "error": f"Reebelo returned no result for sku {sku}: {str(data)[:200]}"}

    except requests.RequestException as e:
        log.error("Reebelo API error for %s: %s", sku, e)
        return {"ok": False, "error": f"Reebelo API error: {e}"}


def delist(sku):
    """End a Reebelo offer by setting stock to 0. Returns bool.

    NOTE: Reebelo's docs don't document an explicit delist endpoint; stock:0 is
    the assumed mechanism — confirm with Reebelo.
    """
    if not _have_creds():
        log.warning("Reebelo creds missing — skipping delist")
        return False
    try:
        r = requests.post(
            f"{config.REEBELO_API_BASE}/sockets/offers/update",
            headers=_headers(), json={"data": [{"sku": sku, "stock": 0}]}, timeout=30,
        )
        if r.status_code in (200, 201) and not _find(r.json(), "failedOffers", sku):
            log.info("Reebelo offer withdrawn (stock 0): sku=%s", sku)
            return True
        log.error("Reebelo delist failed: %s %s", r.status_code, r.text[:200])
        return False
    except requests.RequestException as e:
        log.error("Reebelo API error delisting %s: %s", sku, e)
        return False
