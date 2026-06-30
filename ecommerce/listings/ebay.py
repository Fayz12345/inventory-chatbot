"""
eBay Inventory API listing client (ticket 1D.5 — #137).

`config.EBAY_ENV` toggles between sandbox and production. Sandbox creates real
listings at sandbox.ebay.com — visible in the sandbox Seller Hub but never on
real ebay.ca — so it's the safe place to validate end-to-end before flipping
`EBAY_ENV=production`.

Flow: createOrReplaceInventoryItem -> createOffer -> publishOffer.
"""

import logging
import re
import time

import requests

from ecommerce import config

log = logging.getLogger(__name__)

# Pulls "128GB" / "1 TB" out of a Model string for the Storage Capacity aspect.
_STORAGE_RE = re.compile(r"(\d+)\s*(TB|GB)", re.IGNORECASE)

# Short-lived in-memory cache for the OAuth access token. eBay tokens last
# ~2h; caching avoids a token round-trip per listing in a batch approve session.
# Keyed on env so a sandbox<->production toggle forces a refresh.
_token_cache = {"token": None, "expires_at": 0.0, "env": None}

_PROD_AUTH      = "https://api.ebay.com/identity/v1/oauth2/token"
_PROD_INVENTORY = "https://api.ebay.com/sell/inventory/v1"
_SANDBOX_AUTH      = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
_SANDBOX_INVENTORY = "https://api.sandbox.ebay.com/sell/inventory/v1"


def _auth_url():
    return _SANDBOX_AUTH if config.EBAY_SANDBOX else _PROD_AUTH


def _inventory_url():
    return _SANDBOX_INVENTORY if config.EBAY_SANDBOX else _PROD_INVENTORY


def _have_creds():
    return all([
        config.EBAY_APP_ID,
        config.EBAY_CERT_ID,
        config.EBAY_REFRESH_TOKEN,
    ])


def _condition_enum(grade):
    return config.GRADE_CONDITION_MAP.get(grade, {}).get("ebay", "USED_GOOD")


def _condition_id(grade):
    """eBay legacy numeric condition ID (offer-level), from GRADE_CONDITION_MAP."""
    return config.GRADE_CONDITION_MAP.get(grade, {}).get("ebay_id", "4000")


def _listing_policies():
    """The three business-policy IDs for the offer, omitting any not configured."""
    ids = {
        "fulfillmentPolicyId": config.EBAY_FULFILLMENT_POLICY_ID,
        "paymentPolicyId":     config.EBAY_PAYMENT_POLICY_ID,
        "returnPolicyId":      config.EBAY_RETURN_POLICY_ID,
    }
    return {k: v for k, v in ids.items() if v}


def _get_access_token():
    """Exchange refresh token for a short-lived access token (sell scope).

    Cached in-memory until shortly before expiry (capped) so a batch of
    approves doesn't re-fetch on every listing.
    """
    now = time.monotonic()
    if (_token_cache["token"]
            and _token_cache["env"] == config.EBAY_ENV
            and now < _token_cache["expires_at"]):
        return _token_cache["token"]

    resp = requests.post(
        _auth_url(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        auth=(config.EBAY_APP_ID, config.EBAY_CERT_ID),
        data={
            "grant_type":    "refresh_token",
            "refresh_token": config.EBAY_REFRESH_TOKEN,
            "scope": (
                "https://api.ebay.com/oauth/api_scope/sell.inventory "
                "https://api.ebay.com/oauth/api_scope/sell.account"
            ),
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["access_token"]
    # Cache until 60s before the token's stated expiry, capped at 30 min.
    ttl = max(min(int(data.get("expires_in", 7200)) - 60, 1800), 0)
    _token_cache.update(token=token, expires_at=now + ttl, env=config.EBAY_ENV)
    return token


def _item_specifics(product):
    """Item specifics (aspects) for the listing.

    eBay categories require more than brand/model to publish — e.g. Cell Phones
    (9355) mandates Storage Capacity — so we include the commonly-required
    aspects, parsing storage out of the Model string when present.
    """
    mfr = product.get("Manufacturer", "")
    specs = [
        {"name": "Brand", "values": [mfr]},
        {"name": "Model", "values": [product.get("Model", "")]},
        {"name": "Color", "values": [product.get("Colour", "")]},
        {"name": "Network", "values": ["Unlocked"]},
        {"name": "Operating System",
         "values": ["iOS" if mfr.strip().lower() == "apple" else "Android"]},
    ]
    m = _STORAGE_RE.search(product.get("Model", "") or "")
    if m:
        specs.append({"name": "Storage Capacity",
                      "values": ["%s %s" % (m.group(1), m.group(2).upper())]})
    return specs


def create_listing(product, price, listing_copy, catalog_info=None):
    """Create + publish an eBay listing.

    Returns:
        dict {'ok': True, 'listing_id': str, 'env': 'sandbox'|'production'} on
        success; {'ok': False, 'error': str} on failure.
    """
    if not _have_creds():
        return {
            "ok": False,
            "error": (
                f"eBay ({config.EBAY_ENV}) credentials not configured in .env "
                f"— set EBAY_APP_ID*, EBAY_CERT_ID*, EBAY_REFRESH_TOKEN*."
            ),
        }

    try:
        token = _get_access_token()
    except requests.RequestException as e:
        return {"ok": False, "error": f"eBay OAuth failed: {e}"}

    headers = {
        "Authorization":    f"Bearer {token}",
        "Content-Type":     "application/json",
        "Content-Language": "en-CA",
    }

    sku = (
        f"{product['Manufacturer']}-{product['Model']}-"
        f"{product['Grade']}-{product['Colour']}"
    ).replace(" ", "-").upper()

    description_html = f"<p>{listing_copy.get('description', '')}</p>"
    if listing_copy.get("bullets"):
        description_html += "<ul>" + "".join(
            f"<li>{b}</li>" for b in listing_copy["bullets"]
        ) + "</ul>"

    inventory_item = {
        "availability": {
            "shipToLocationAvailability": {"quantity": product["Quantity"]},
        },
        "condition": _condition_enum(product["Grade"]),
        "conditionDescription": listing_copy.get("condition_note", ""),
        "product": {
            "title":       listing_copy.get("title", ""),
            "description": description_html,
            "aspects": {
                spec["name"]: spec["values"]
                for spec in _item_specifics(product)
            },
        },
    }
    if catalog_info and catalog_info.get("epid"):
        inventory_item["product"]["epid"] = catalog_info["epid"]
    if catalog_info and catalog_info.get("upc"):
        inventory_item["product"]["upc"] = [catalog_info["upc"]]

    inv_url = _inventory_url()

    try:
        # 1) inventory item
        resp = requests.put(
            f"{inv_url}/inventory_item/{sku}",
            headers=headers, json=inventory_item, timeout=30,
        )
        if resp.status_code not in (200, 201, 204):
            return {"ok": False, "error": (
                f"eBay create inventory item failed: {resp.status_code} {resp.text}"
            )}

        # 2) offer
        offer_body = {
            "sku":               sku,
            "marketplaceId":     config.EBAY_MARKETPLACE_ID,
            "format":            "FIXED_PRICE",
            "listingDescription": description_html,
            "pricingSummary": {
                "price": {"value": str(price), "currency": config.DEFAULT_CURRENCY},
            },
            "categoryId":  config.EBAY_CATEGORY_ID,
            "conditionId": _condition_id(product["Grade"]),
            "quantityLimitPerBuyer": 1,
        }
        # publishOffer requires a merchant location + the three business policies.
        # They're omitted if unconfigured so createOffer still succeeds; publish
        # then fails with eBay's own (clear) error rather than a silent 400 here.
        if config.EBAY_MERCHANT_LOCATION_KEY:
            offer_body["merchantLocationKey"] = config.EBAY_MERCHANT_LOCATION_KEY
        policies = _listing_policies()
        if policies:
            offer_body["listingPolicies"] = policies
        if not (config.EBAY_MERCHANT_LOCATION_KEY and len(policies) == 3):
            log.warning(
                "eBay offer missing publish prerequisites "
                "(merchantLocationKey=%s, policies=%d/3) — publishOffer will fail "
                "until EBAY_MERCHANT_LOCATION_KEY + the 3 EBAY_*_POLICY_ID vars are set.",
                bool(config.EBAY_MERCHANT_LOCATION_KEY), len(policies),
            )
        resp = requests.post(
            f"{inv_url}/offer", headers=headers, json=offer_body, timeout=30,
        )
        if resp.status_code not in (200, 201):
            return {"ok": False, "error": (
                f"eBay create offer failed: {resp.status_code} {resp.text}"
            )}
        offer_id = resp.json().get("offerId")

        # 3) publish
        resp = requests.post(
            f"{inv_url}/offer/{offer_id}/publish", headers=headers, timeout=30,
        )
        if resp.status_code not in (200, 201):
            return {"ok": False, "error": (
                f"eBay publish offer failed: {resp.status_code} {resp.text}"
            )}

        public_listing_id = resp.json().get("listingId", offer_id)
        host = "www.sandbox.ebay.com" if config.EBAY_SANDBOX else "www.ebay.ca"
        listing_url = "https://%s/itm/%s" % (host, public_listing_id)
        log.info(
            "eBay listing published (%s): SKU=%s offerId=%s listingId=%s url=%s",
            config.EBAY_ENV, sku, offer_id, public_listing_id, listing_url,
        )
        # Return the offerId as the managed listing id: withdraw/delist operate
        # on the offer, not the public listingId (which can't be withdrawn).
        # public_listing_id + listing_url are for display/linking in the modal.
        return {
            "ok": True,
            "listing_id": str(offer_id),
            "env": config.EBAY_ENV,
            "public_listing_id": str(public_listing_id),
            "listing_url": listing_url,
        }

    except requests.RequestException as e:
        log.error("eBay API error creating listing for %s: %s", sku, e)
        return {"ok": False, "error": f"eBay API error: {e}"}


def delist(listing_id):
    """End an eBay listing by withdrawing the offer. Returns bool."""
    if not _have_creds():
        log.warning("eBay creds missing — skipping delist")
        return False
    try:
        token = _get_access_token()
    except requests.RequestException as e:
        log.error("eBay OAuth failed during delist: %s", e)
        return False

    try:
        resp = requests.post(
            f"{_inventory_url()}/offer/{listing_id}/withdraw",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code in (200, 204):
            log.info("eBay listing withdrawn (%s): %s", config.EBAY_ENV, listing_id)
            return True
        log.error("eBay withdraw failed: %s %s", resp.status_code, resp.text)
        return False
    except requests.RequestException as e:
        log.error("eBay API error delisting %s: %s", listing_id, e)
        return False
