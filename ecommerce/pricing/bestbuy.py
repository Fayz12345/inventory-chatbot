"""
Best Buy Canada competitor pricing via bestbuy.ca's front-end search API.

Replaces the Mirakl **P11** seller API (UPC-keyed), which only saw the sparse
third-party *marketplace* and returned 0 products for most of our devices (a
measurement across iPhone 13 / Moto G Stylus / Galaxy Watch5 confirmed ~0 coverage
even with valid GTINs). bestbuy.ca's own search API is **keyword-based** and surfaces
Best Buy's large **refurbished / open-box** inventory — the right competitor set for
our used devices, and no UPC required (same shape as Reebelo/eBay):

    GET https://www.bestbuy.ca/api/v2/json/search?query=<kw>&lang=en-CA&pageSize=N
      -> { "products": [ { "name", "salePrice", "regularPrice", "sku",
                           "isMarketplace" }, ... ], "total": N }

We keep only refurbished/open-box listings (dropping carrier-financing and
accessories), title-match the model, filter by condition→grade, and take the lowest
price. Routed through the Apify RESIDENTIAL proxy by default (BESTBUY_USE_APIFY_PROXY):
bestbuy.ca is Akamai-fronted and blocks datacenter IPs, so a blocked EC2 IP is rotated
out on retry. See ecommerce/pricing/proxy.py. Blocks are logged loudly, not silently zeroed.
"""

import logging
import re
import time

import requests

from ecommerce import config
from ecommerce.pricing import proxy
from ecommerce.pricing.filters import is_accessory

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.bestbuy.ca/api/v2/json/search"

DEFAULT_MIN_PRICE = 50.0   # also filters out carrier "$15-30/mo" financing entries
REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.5        # seconds between keyword queries
RETRIES = 2                # retry on block/transport error (a residential retry = fresh IP)
PAGE_SIZE = 24             # search results per keyword (relevance-sorted first page)

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Accept-Language": "en-CA",
}

# Carrier names -> a monthly-financing/contract listing (the shown price is a
# per-month payment, not the device price). From the retired google_shopping.py.
_CARRIER_NAMES = ("telus", "koodo", "bell", "rogers", "fido", "virgin",
                  "public mobile", "chatr", "freedom")

# The used competitor set we compare against. Anything else (new, financing) is dropped.
_REFURB_MARKERS = ("refurbished", "open box", "open-box", "pre-owned", "preowned",
                   "geek squad")

# Map internal grade -> acceptable Best Buy condition markers (substring, lowercase).
# Best Buy conditions seen: "Refurbished (Excellent|Good|Fair)", "Open Box", "Pre-Owned".
GRADE_CONDITION_MAP = {
    "NEW": ("open box", "excellent"),
    "A+":  ("excellent", "open box"),
    "A":   ("excellent", "open box"),
    "B":   ("good", "open box", "pre-owned"),
    "C":   ("fair", "acceptable", "good", "pre-owned"),
}

# Title-matching (mirrors ecommerce/pricing/reebelo.py): drop brand words, require every
# significant keyword token as a substring, and require model qualifiers on both sides or
# neither so "Watch5 44mm" != "Watch5 Pro 45mm" and "Stylus 2024" != "Stylus 2022".
_BRANDS = {"apple", "samsung", "google", "motorola", "moto", "sonim", "tcl",
           "huawei", "alcatel", "lg", "oneplus", "nokia"}
_MODEL_QUALIFIERS = {"mini", "pro", "max", "plus", "ultra", "se", "fe", "air",
                     "classic", "lite", "neo", "active"}


def scrape_and_return_all(keywords_list, min_price=DEFAULT_MIN_PRICE, max_results=PAGE_SIZE):
    """Search bestbuy.ca once per keyword; return refurbished/open-box listings.

    Returns:
        dict mapping keyword -> list of {title, price, condition, sku}.
    """
    keywords = list(dict.fromkeys(keywords_list or []))
    grouped = {kw: [] for kw in keywords}
    if not keywords:
        return grouped

    proxies, via = proxy.proxies_for(config.BESTBUY_USE_APIFY_PROXY, "bestbuy")
    log.info("Fetching Best Buy CA prices via bestbuy.ca search for %d keyword(s) (%s)...",
             len(keywords), via)

    for i, kw in enumerate(keywords):
        if i:
            time.sleep(REQUEST_DELAY)
        grouped[kw] = _search_one(kw, min_price, max_results, proxies, via)

    hits = sum(1 for v in grouped.values() if v)
    log.info("Best Buy CA (bestbuy.ca search): %d/%d keywords with refurb listings.",
             hits, len(keywords))
    if keywords and hits == 0:
        log.warning("Best Buy returned 0 refurb listings for all %d keywords — bestbuy.ca "
                    "may be blocking (%s). Check the block warnings above.", len(keywords), via)
    return grouped


def _search_one(keyword, min_price, max_results, proxies, via):
    products = _search(keyword, max_results, proxies, via)
    if products is None:
        return []

    tokens = _match_tokens(keyword)
    out = []
    for p in products:
        name = p.get("name") or ""
        if is_accessory(name) or not _is_refurb(name):
            continue
        price = _price(p)
        if price is None or (min_price and price < min_price):
            continue                       # drops carrier "$/mo" financing prices too
        if _is_carrier_financing(name):
            continue
        if not _title_matches(name, tokens):
            continue
        out.append({"title": name, "price": price,
                    "condition": _condition(name), "sku": p.get("sku")})
    log.info("Best Buy CA: %d refurb match(es) for '%s'.", len(out), keyword)
    return out


def find_product_sku(keyword, colour=None):
    """Resolve the Best Buy CATALOG product SKU for a device, on the fly, from the
    same bestbuy.ca search used for pricing. Lets a Mirakl offer reference the
    product by SKU (product-id-type=SKU) so auto-post needs no seeded UPC.

    Matches the device VARIANT (model + storage tokens, via _title_matches). Does
    NOT filter by refurb condition — the product-page SKU is the same regardless of
    the listed offers' conditions. When `colour` is given, prefer a result whose
    name contains it (Best Buy SKUs are per-colour); else fall back to the best
    variant match and log that colour wasn't confirmed.

    Returns the SKU string, or None if nothing matches / the search is blocked.
    """
    proxies, via = proxy.proxies_for(config.BESTBUY_USE_APIFY_PROXY, "bestbuy")
    products = _search(keyword, PAGE_SIZE, proxies, via)
    if not products:
        log.info("Best Buy CA: no product SKU resolvable for '%s' (no results / blocked).", keyword)
        return None

    tokens = _match_tokens(keyword)
    matches = [p for p in products
               if p.get("sku")
               and not is_accessory(p.get("name") or "")
               and _title_matches(p.get("name") or "", tokens)]
    if not matches:
        log.info("Best Buy CA: %d results but no variant match for '%s' — no SKU.",
                 len(products), keyword)
        return None

    if colour:
        c = _normalize(colour)
        for p in matches:
            if c and c in _normalize(p.get("name") or ""):
                log.info("Best Buy CA: product SKU %s for '%s' (%s).", p["sku"], keyword, colour)
                return p["sku"]

    chosen = matches[0]
    log.info("Best Buy CA: product SKU %s for '%s' (variant match; colour '%s' not "
             "confirmed in title).", chosen["sku"], keyword, colour)
    return chosen["sku"]


def _search(keyword, max_results, proxies, via):
    """One search request. Returns the products list (possibly empty), or None on failure.
    Retries on a block/transport error — a residential retry gets a fresh exit IP."""
    params = {"query": keyword, "lang": "en-CA", "page": 1, "pageSize": max_results}
    for attempt in range(RETRIES + 1):
        if attempt:
            time.sleep(2 * attempt)
        try:
            r = requests.get(SEARCH_URL, params=params, headers=_HEADERS,
                             proxies=proxies, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log.warning("[bestbuy] request error via %s for '%s' (attempt %d/%d): %s",
                        via, keyword, attempt + 1, RETRIES + 1, e)
            continue
        if proxy.looks_blocked(r.status_code):
            proxy.log_block("bestbuy", r.status_code, via, r.text)
            continue  # retry -> fresh residential IP
        if r.status_code != 200:
            log.info("[bestbuy] HTTP %s for '%s' (not a block).", r.status_code, keyword)
            return None
        try:
            return (r.json() or {}).get("products") or []
        except ValueError:
            log.warning("[bestbuy] non-JSON response for '%s'.", keyword)
            return None
    return None


def get_floor_price_for_grade(grouped_results, keyword, grade):
    """Lowest Best Buy refurb price for a keyword whose condition matches the grade.

    Prefers a grade-matched listing; falls back to the overall refurb floor so a
    device with only off-grade refurb stock still gets a competitor signal.
    Returns float or None.
    """
    items = grouped_results.get(keyword) or []
    acceptable = GRADE_CONDITION_MAP.get(grade, GRADE_CONDITION_MAP["C"])

    graded, overall = None, None
    for it in items:
        price = it.get("price")
        if not price or price <= 0:
            continue
        if overall is None or price < overall:
            overall = price
        cond = it.get("condition") or ""
        if any(m in cond for m in acceptable) and (graded is None or price < graded):
            graded = price

    floor = graded if graded is not None else overall
    if floor is not None:
        log.info("Best Buy CA floor for '%s' Grade %s: $%.2f%s",
                 keyword, grade, floor, "" if graded is not None else " (off-grade fallback)")
    else:
        log.info("Best Buy CA: no refurb match for '%s' Grade %s.", keyword, grade)
    return floor


# --- helpers ---------------------------------------------------------------

def _price(product):
    """A listing's price: prefer salePrice, fall back to regularPrice."""
    for key in ("salePrice", "regularPrice"):
        v = product.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
        if isinstance(v, str):
            m = re.search(r"[\d,]+\.?\d*", v.replace(",", ""))
            if m:
                try:
                    f = float(m.group())
                    if f > 0:
                        return f
                except ValueError:
                    pass
    return None


def _is_refurb(name):
    n = (name or "").lower()
    return any(m in n for m in _REFURB_MARKERS)


def _is_carrier_financing(name):
    """A carrier-named listing is a monthly-financing/contract price, not a device price."""
    n = (name or "").lower()
    return any(c in n for c in _CARRIER_NAMES) or "monthly financing" in n


def _condition(name):
    """Extract a lowercase condition token from the listing name."""
    n = (name or "").lower()
    m = re.search(r"refurbished\s*\(([^)]+)\)", n)
    if m:
        return m.group(1).strip()          # 'excellent' | 'good' | 'fair'
    if "open box" in n or "open-box" in n:
        return "open box"
    if "pre-owned" in n or "preowned" in n:
        return "pre-owned"
    if "geek squad" in n:
        return "excellent"
    return "refurbished"


def _normalize(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _match_tokens(keyword):
    return [t for t in _normalize(keyword).split() if t not in _BRANDS and len(t) >= 2]


def _title_matches(title, tokens):
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
