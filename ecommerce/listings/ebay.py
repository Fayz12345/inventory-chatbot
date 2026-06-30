"""
eBay Inventory API listing client (ticket 1D.5 — #137).

`config.EBAY_ENV` toggles between sandbox and production. Sandbox creates real
listings at sandbox.ebay.com — visible in the sandbox Seller Hub but never on
real ebay.ca — so it's the safe place to validate end-to-end before flipping
`EBAY_ENV=production`.

Flow: createOrReplaceInventoryItem -> createOffer -> publishOffer.
"""

import hashlib
import logging
import re
import time

import requests

from ecommerce import config

log = logging.getLogger(__name__)

# Pulls "128GB" / "1 TB" out of a Model string for the Storage Capacity aspect.
_STORAGE_RE = re.compile(r"(\d+)\s*(TB|GB)", re.IGNORECASE)
_CASE_SIZE_RE = re.compile(r"(\d{2})\s*mm", re.IGNORECASE)

# eBay CA leaf categories per device type (validated live against the sandbox:
# each one published with the aspect set built in _item_specifics below).
_CATEGORY_BY_TYPE = {
    "phone":      "9355",    # Cell Phones & Smartphones
    "smartwatch": "178893",  # Smart Watches
    "tablet":     "171485",  # Tablets & eBook Readers
    "earbuds":    "112529",  # Headphones
}


def _device_type(product):
    """Classify a product into an eBay category bucket from its Model string."""
    m = (product.get("Model") or "").lower()
    if any(k in m for k in ("airpod", "buds", "earbud", "earphone")):
        return "earbuds"
    if "watch" in m:
        return "smartwatch"
    if any(k in m for k in ("ipad", "tablet", "galaxy tab", "tab s", "tab a")):
        return "tablet"
    return "phone"


def _category_id(product):
    return _CATEGORY_BY_TYPE.get(_device_type(product), config.EBAY_CATEGORY_ID or "9355")


def _sku(product):
    """eBay SKU: alphanumeric/dash only, max 50 chars. Long models (which embed
    parenthesised descriptions) are truncated with a short hash so distinct
    products stay distinct — eBay rejects anything else with errorId 25707."""
    raw = "-".join([product.get("Manufacturer", ""), product.get("Model", ""),
                    product.get("Grade", ""), product.get("Colour", "")])
    s = re.sub(r"[^A-Za-z0-9]+", "-", raw).strip("-").upper()
    if len(s) > 50:
        h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8].upper()
        s = s[:41].rstrip("-") + "-" + h
    return s

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


def _existing_offer_id(resp):
    """eBay 25002 'Offer entity already exists' carries the existing offerId in
    the error parameters — pull it so we can reuse the offer instead of failing."""
    try:
        for err in (resp.json().get("errors") or []):
            if err.get("errorId") == 25002:
                for p in (err.get("parameters") or []):
                    if p.get("name") == "offerId" and p.get("value"):
                        return p["value"]
    except ValueError:
        pass
    return None


def _offer_id_by_sku(inv_url, headers, sku):
    """Look up an existing offerId for a SKU (fallback when the error lacks it)."""
    try:
        r = requests.get(f"{inv_url}/offer?sku={sku}", headers=headers, timeout=30)
        offers = (r.json() or {}).get("offers") or []
        return offers[0].get("offerId") if offers else None
    except requests.RequestException:
        return None


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
    """Item specifics (aspects) required to PUBLISH in the product's eBay
    category. The required set differs per category (validated live against the
    sandbox), so we build it per device type and fill values from the product
    where possible, with sensible defaults otherwise.
    """
    mfr = product.get("Manufacturer", "") or ""
    model = product.get("Model", "") or ""
    colour = product.get("Colour", "") or ""
    apple = mfr.strip().lower() == "apple"
    dtype = _device_type(product)

    specs = {"Brand": mfr or "Unbranded", "Model": model or mfr or "N/A"}
    storage = _STORAGE_RE.search(model)
    storage_val = "%s %s" % (storage.group(1), storage.group(2).upper()) if storage else None

    if dtype == "smartwatch":
        case = _CASE_SIZE_RE.search(model)
        specs["Case Size"] = ("%s mm" % case.group(1)) if case else "44 mm"
        specs["Compatible Operating System"] = "Apple iOS" if apple else "Android"
        specs["Band Material"] = "Silicone"
        if colour:
            specs["Colour"] = colour
    elif dtype == "earbuds":
        specs["Connectivity"] = "Wireless"
        specs["Type"] = "In-Ear (Earbud)"
        specs["Color"] = colour or "Black"
    elif dtype == "tablet":
        if storage_val:
            specs["Storage Capacity"] = storage_val
        specs["Screen Size"] = "10.9 in"
        specs["Type"] = "Tablet"
        specs["Internet Connectivity"] = (
            "Wi-Fi + Cellular" if re.search(r"cellular|lte", model, re.I) else "Wi-Fi")
    else:  # phone
        if storage_val:
            specs["Storage Capacity"] = storage_val
        specs["Network"] = "Unlocked"
        specs["Operating System"] = "iOS" if apple else "Android"
        specs["Color"] = colour or "Black"

    return [{"name": k, "values": [v]} for k, v in specs.items()]


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

    sku = _sku(product)

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
            "categoryId":  _category_id(product),
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
        if resp.status_code in (200, 201):
            offer_id = resp.json().get("offerId")
        else:
            # Idempotent re-approve: if an unpublished offer already exists for
            # this SKU (eBay 25002), reuse it — update it with the current data
            # and continue to publish — instead of hard-failing.
            offer_id = _existing_offer_id(resp) or _offer_id_by_sku(inv_url, headers, sku)
            if not offer_id:
                return {"ok": False, "error": (
                    f"eBay create offer failed: {resp.status_code} {resp.text}"
                )}
            update_body = {k: v for k, v in offer_body.items() if k != "sku"}
            upd = requests.put(
                f"{inv_url}/offer/{offer_id}", headers=headers, json=update_body, timeout=30,
            )
            if upd.status_code not in (200, 204):
                return {"ok": False, "error": (
                    f"eBay update existing offer failed: {upd.status_code} {upd.text}"
                )}

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
