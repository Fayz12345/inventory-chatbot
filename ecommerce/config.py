"""
Re-exports root config values + ecommerce-specific constants, AND resolves
marketplace credentials from the environment (`.env`) for the 1D.4 / 1D.5 /
1D.6 auto-listing flow.

Marketplace creds live in `.env` rather than `config.py` so that sandbox and
production sets can sit side-by-side and a single `*_ENV=sandbox|production`
toggle picks which one the app uses. See `.env.example` for the full field
list.
"""

import os

from config import (
    DB_SERVER,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
    ANTHROPIC_API_KEY,
    APIFY_API_TOKEN,
    ECOMMERCE_MINIMUM_MARGIN,
)

MINIMUM_MARGIN = ECOMMERCE_MINIMUM_MARGIN

# Single source of truth for listing currency (was hardcoded "CAD" in each
# listing module).
DEFAULT_CURRENCY = "CAD"


# ---------------------------------------------------------------------------
# Marketplace credential resolution
# ---------------------------------------------------------------------------

def _env(name, default=""):
    """Read an env var with a sensible default. Strips whitespace."""
    return (os.environ.get(name) or default).strip()


def _resolve(env_name, prod_key, sandbox_key, default=""):
    """Return prod or sandbox value based on the *_ENV toggle.

    `env_name`: the toggle env var (e.g. 'AMAZON_ENV').
    `prod_key`, `sandbox_key`: env var names holding the actual credential.
    """
    mode = _env(env_name, "sandbox").lower()
    if mode == "production":
        return _env(prod_key, default)
    return _env(sandbox_key, default)


# Amazon SP-API
AMAZON_ENV               = _env("AMAZON_ENV", "sandbox").lower()
AMAZON_MARKETPLACE_ID    = _env("AMAZON_MARKETPLACE_ID", "A2EUQ1WTGCTBG2")
AMAZON_SELLER_ID         = _resolve("AMAZON_ENV", "AMAZON_SELLER_ID",         "AMAZON_SELLER_ID_SANDBOX")
AMAZON_REFRESH_TOKEN     = _resolve("AMAZON_ENV", "AMAZON_REFRESH_TOKEN",     "AMAZON_REFRESH_TOKEN_SANDBOX")
AMAZON_LWA_APP_ID        = _resolve("AMAZON_ENV", "AMAZON_LWA_APP_ID",        "AMAZON_LWA_APP_ID_SANDBOX")
AMAZON_LWA_CLIENT_SECRET = _resolve("AMAZON_ENV", "AMAZON_LWA_CLIENT_SECRET", "AMAZON_LWA_CLIENT_SECRET_SANDBOX")
AMAZON_SANDBOX           = (AMAZON_ENV != "production")

# eBay API
EBAY_ENV              = _env("EBAY_ENV", "sandbox").lower()
EBAY_MARKETPLACE_ID   = _env("EBAY_MARKETPLACE_ID", "EBAY_CA")
EBAY_CATEGORY_ID      = _env("EBAY_CATEGORY_ID", "")
EBAY_APP_ID           = _resolve("EBAY_ENV", "EBAY_APP_ID",         "EBAY_APP_ID_SANDBOX")
EBAY_CERT_ID          = _resolve("EBAY_ENV", "EBAY_CERT_ID",        "EBAY_CERT_ID_SANDBOX")
EBAY_REFRESH_TOKEN    = _resolve("EBAY_ENV", "EBAY_REFRESH_TOKEN",  "EBAY_REFRESH_TOKEN_SANDBOX")
EBAY_SANDBOX          = (EBAY_ENV != "production")
# Inventory API publishOffer prerequisites: a merchant inventory location and the
# three business policies (their IDs differ per sandbox/prod account).
EBAY_MERCHANT_LOCATION_KEY = _resolve("EBAY_ENV", "EBAY_MERCHANT_LOCATION_KEY", "EBAY_MERCHANT_LOCATION_KEY_SANDBOX")
EBAY_FULFILLMENT_POLICY_ID = _resolve("EBAY_ENV", "EBAY_FULFILLMENT_POLICY_ID", "EBAY_FULFILLMENT_POLICY_ID_SANDBOX")
EBAY_PAYMENT_POLICY_ID     = _resolve("EBAY_ENV", "EBAY_PAYMENT_POLICY_ID",     "EBAY_PAYMENT_POLICY_ID_SANDBOX")
EBAY_RETURN_POLICY_ID      = _resolve("EBAY_ENV", "EBAY_RETURN_POLICY_ID",      "EBAY_RETURN_POLICY_ID_SANDBOX")

# Best Buy Canada Marketplace (Mirakl) — ticket 1D.11. Single PRODUCTION
# instance (no sandbox); creating an offer posts a REAL listing. Only state
# "11" (New) is offered, so grade is carried in the offer description.
BESTBUY_API_BASE         = _env("BESTBUY_API_BASE", "https://marketplace.bestbuy.ca/api")
BESTBUY_API_KEY          = _env("BESTBUY_API_KEY", "")
BESTBUY_STATE_CODE       = _env("BESTBUY_STATE_CODE", "11")
BESTBUY_LOGISTIC_CLASS   = _env("BESTBUY_LOGISTIC_CLASS", "SMALL")
BESTBUY_PRODUCT_ID_TYPE  = _env("BESTBUY_PRODUCT_ID_TYPE", "UPC-A")
BESTBUY_LEADTIME_TO_SHIP = int(_env("BESTBUY_LEADTIME_TO_SHIP", "4") or "4")
# Mirakl requires the additional offer field "manufacturer-warranty" (days).
BESTBUY_MANUFACTURER_WARRANTY = _env("BESTBUY_MANUFACTURER_WARRANTY", "365")
# Override the posted offer quantity when set (e.g. "0" for a demo listing that
# is live but not purchasable). Leave blank in production so real stock is used.
BESTBUY_FORCE_QUANTITY = _env("BESTBUY_FORCE_QUANTITY", "")

# Reebelo (Cobalt) — ticket 1D.12. Cobalt auth is a static API key in the
# `x-api-key` header; base URL is env-specific (sandbox a.reebelo.blue / prod
# a.reebelo.com). USERNAME/PASSWORD slots are legacy/unused by Cobalt.
REEBELO_ENV       = _env("REEBELO_ENV", "sandbox").lower()
REEBELO_USERNAME  = _resolve("REEBELO_ENV", "REEBELO_USERNAME",  "REEBELO_USERNAME_SANDBOX")
REEBELO_PASSWORD  = _resolve("REEBELO_ENV", "REEBELO_PASSWORD",  "REEBELO_PASSWORD_SANDBOX")
REEBELO_API_KEY   = _resolve("REEBELO_ENV", "REEBELO_API_KEY",   "REEBELO_API_KEY_SANDBOX")
REEBELO_SANDBOX   = (REEBELO_ENV != "production")
REEBELO_API_BASE  = _env("REEBELO_API_BASE",
                         "https://a.reebelo.blue" if REEBELO_SANDBOX else "https://a.reebelo.com")


# ---------------------------------------------------------------------------
# Marketplace condition mapping (Grade -> per-marketplace enum)
# ---------------------------------------------------------------------------

# Used by listings/amazon.py (`condition_type`) and listings/ebay.py
# (`conditionEnum` + the legacy numeric `conditionId`, now consolidated here as
# `ebay_id` instead of a duplicate dict in ebay.py). Adjust once we have real
# marketplace sign-off on which condition codes to use.
GRADE_CONDITION_MAP = {
    "NEW": {"amazon": "New",         "ebay": "NEW",            "ebay_id": "1000"},
    "A+":  {"amazon": "UsedLikeNew", "ebay": "USED_EXCELLENT", "ebay_id": "2500"},
    "A":   {"amazon": "UsedLikeNew", "ebay": "USED_EXCELLENT", "ebay_id": "2500"},
    # eBay Cell Phones category (9355) only accepts USED_EXCELLENT/2500 for used
    # (the granular USED_VERY_GOOD/USED_GOOD + 3000/4000 are rejected on publish);
    # the precise grade is still conveyed in the title/condition note.
    "B":   {"amazon": "UsedVeryGood","ebay": "USED_EXCELLENT", "ebay_id": "2500"},
    "C":   {"amazon": "UsedGood",    "ebay": "USED_EXCELLENT", "ebay_id": "2500"},
}


# ---------------------------------------------------------------------------
# Device category -> Amazon productType (#198 / 1D.10 #3)
# ---------------------------------------------------------------------------

# Keys are TelusWeeklyPricingMaster.DeviceType values (the category source).
# Phones keep the existing WIRELESS_PHONE (no regression to the proven path);
# the NON-phone values are best-effort and MUST be validated against Amazon's
# getDefinitionsProductType API for the CA marketplace before production —
# tracked under #198 #3 (blocked on Amazon SP-API access).
AMAZON_DEFAULT_PRODUCT_TYPE = "WIRELESS_PHONE"
AMAZON_PRODUCT_TYPE_BY_CATEGORY = {
    "Handset":     "WIRELESS_PHONE",
    "Phone":       "WIRELESS_PHONE",
    "Tablet":      "TABLET_COMPUTER",      # TODO: verify vs Amazon definitions
    "Laptop":      "NOTEBOOK_COMPUTER",    # TODO: verify
    "Smart Watch": "WATCH",                # TODO: verify
    "Modem":       "ROUTER",               # TODO: verify
}
