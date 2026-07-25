"""
Reebelo Canada competitor pricing via reebelo.ca's first-party catalog JSON API.

Replaces the broken `adminbridge/reebelo-ca-scraper` Apify actor (HTML scraping that
timed out on batches and returned 0 products on clean runs). reebelo.ca is a Next.js
app backed by a public, no-auth JSON search API:

    GET https://reebelo.ca/api/catalog-v2/search/skus?q=<keyword>
      -> { "items": [ { "title", "price" (cents), "product", "variants" }, ... ], "total" }

We take the lowest CAD price across items whose title matches the searched device.

Routed through the Apify RESIDENTIAL proxy by default (REEBELO_USE_APIFY_PROXY):
reebelo.ca blocks datacenter IPs, so a blocked EC2 IP is rotated out on retry. See
ecommerce/pricing/proxy.py. A block is logged loudly rather than silently zeroing prices.
"""

import logging
import re
import time

import requests

from ecommerce import config
from ecommerce.pricing import proxy
from ecommerce.pricing.filters import is_accessory

log = logging.getLogger(__name__)

SEARCH_URL = "https://reebelo.ca/api/catalog-v2/search/skus"

DEFAULT_MIN_PRICE = 30.0
REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.5      # seconds between keyword queries (API rate limit is 500/window)
RETRIES = 2             # retry on a block/transport error (a residential retry = fresh IP)
MAX_ITEMS_SCAN = 60     # search returns ~24 items/page; scan the (relevance-sorted) first page

# Browser-like UA so the CloudFront edge treats us like the site's own frontend.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

# Brand words to drop from the keyword before title-matching (reebelo titles usually
# omit the brand, e.g. "iPhone 13 - 128GB - Blue - Unlocked").
_BRANDS = {"apple", "samsung", "google", "motorola", "sonim", "tcl", "huawei", "alcatel", "lg"}

# Model-distinguishing qualifiers. A match requires each of these to be present on
# BOTH sides or NEITHER — so "iPhone 13" (keyword) does NOT match "iPhone 13 mini"
# or "iPhone 13 Pro" (which are different, differently-priced devices).
_MODEL_QUALIFIERS = {"mini", "pro", "max", "plus", "ultra", "se", "fe", "air",
                     "classic", "lite", "neo", "active"}


def scrape_prices(keywords_list, min_price=DEFAULT_MIN_PRICE):
    """Lowest reebelo.ca CAD price per keyword via the catalog search API.

    Returns:
        dict mapping keyword -> lowest matching price (float) or None.
    """
    keywords = list(dict.fromkeys(keywords_list or []))
    prices = {kw: None for kw in keywords}
    if not keywords:
        return prices

    proxies, via = proxy.proxies_for(config.REEBELO_USE_APIFY_PROXY, "reebelo")
    log.info("Fetching Reebelo CA prices via reebelo.ca catalog API for %d keyword(s) (%s)...",
             len(keywords), via)

    for i, kw in enumerate(keywords):
        if i:
            time.sleep(REQUEST_DELAY)
        prices[kw] = _fetch_one(kw, min_price, proxies, via)

    found = sum(1 for v in prices.values() if v is not None)
    log.info("Reebelo CA (catalog API): %d/%d keywords with prices.", found, len(keywords))
    if keywords and found == 0:
        log.warning("Reebelo returned 0 prices for all %d keywords — reebelo.ca may be "
                    "blocking (%s). Check the block warnings above.", len(keywords), via)
    return prices


def _fetch_one(keyword, min_price, proxies, via):
    items = _search(keyword, proxies, via)
    if not items:
        return None

    tokens = _match_tokens(keyword)
    floor = None
    winner = None
    for it in items[:MAX_ITEMS_SCAN]:
        title = it.get("title") or ""
        if is_accessory(title):
            continue
        if not _title_matches(title, tokens):
            continue
        cents = it.get("price")
        if not isinstance(cents, (int, float)) or cents <= 0:
            continue
        price = round(cents / 100.0, 2)
        if min_price and price < min_price:
            continue
        if floor is None or price < floor:
            floor, winner = price, title

    if floor is not None:
        log.info("Reebelo CA floor for '%s': $%.2f  (matched: %s)", keyword, floor, winner)
    else:
        log.info("Reebelo CA: no matching priced result for '%s' (%d items scanned).",
                 keyword, len(items))
    return floor


def _search(keyword, proxies, via):
    """One search request. Returns the items list (possibly empty), or None on failure.
    Retries on a block/transport error — a residential retry gets a fresh exit IP."""
    for attempt in range(RETRIES + 1):
        if attempt:
            time.sleep(2 * attempt)
        try:
            r = requests.get(SEARCH_URL, params={"q": keyword}, headers=_HEADERS,
                             proxies=proxies, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log.warning("[reebelo] request error via %s for '%s' (attempt %d/%d): %s",
                        via, keyword, attempt + 1, RETRIES + 1, e)
            continue
        if proxy.looks_blocked(r.status_code):
            proxy.log_block("reebelo", r.status_code, via, r.text)
            continue  # retry -> fresh residential IP
        if r.status_code != 200:
            log.info("[reebelo] HTTP %s for '%s' (not a block).", r.status_code, keyword)
            return None
        try:
            return (r.json() or {}).get("items") or []
        except ValueError:
            log.warning("[reebelo] non-JSON response for '%s'.", keyword)
            return None
    return None


def _normalize(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _match_tokens(keyword):
    """Significant tokens the reebelo title must contain (brand words dropped)."""
    return [t for t in _normalize(keyword).split() if t not in _BRANDS and len(t) >= 2]


def _title_matches(title, tokens):
    """True if the reebelo title is the same device as the keyword.

    (1) every significant keyword token must be a substring of the title —
        substring (not equality) so 'watch 6' matches reebelo's 'Watch6' and
        storage/size tokens like '256gb'/'47mm' gate the model; and
    (2) each model qualifier (mini/pro/max/...) must be present on BOTH sides or
        NEITHER, so 'iPhone 13' does not match 'iPhone 13 mini' / 'iPhone 13 Pro'.
    """
    if not tokens:
        return False
    norm = _normalize(title)
    if not all(t in norm for t in tokens):
        return False
    kw = set(tokens)
    title_words = set(norm.split())
    for q in _MODEL_QUALIFIERS:
        if (q in kw) != (q in title_words):
            return False
    return True
