"""
eBay Canada competitor pricing via SOLD listings (caffein.dev/ebay-sold-listings Apify actor).

Replaces `khadinakbar/ebay-all-in-one-scraper` (active listings), which ebay.ca antibot-blocked
constantly (Batch #17: 160/172 runs empty; a live dry-run returned 0/2). The sold-listings actor
is far more reliable (99.6% success, verified live: 25 CAD listings in 6s) and is a better signal
for used devices: what they ACTUALLY sold for, not asking prices.

Per keyword we take the **median of comparable CAD sold prices** as eBay's competitor number,
after excluding the noise that pollutes sold data:
  - carrier-LOCKED units (DISH/Cricket/Boost/Rogers/…) — sell far below unlocked, not comparable;
  - parts / damaged / "read description" / bulk lots;
  - accessories and off-model results (title-match gate).

Note: sold data isn't grade-tagged (mostly "Pre-Owned"), so we map each grade to a percentile of
the model's sold-price distribution (A+ high end, C low end) rather than a flat median. The
finer-grained "asking price" path is the eBay Browse API, which is parked on eBay keyset/compliance
work — see docs/ebay-browse-api-status.md.
"""

import logging
import re
import statistics
import time

from ecommerce.pricing import apify_client
from ecommerce.pricing.filters import is_accessory

log = logging.getLogger(__name__)

ACTOR_ID = 'caffein.dev/ebay-sold-listings'

DEFAULT_MIN_PRICE = 50.0     # drops sub-$50 carrier-locked/parts junk
SOLD_WINDOW_DAYS = 90        # look back this many days for sold comps
PER_KEYWORD = 30             # sold listings to pull per keyword (before filtering)
INTER_KEYWORD_DELAY = 0.5    # seconds between keyword runs

# eBay sold data doesn't tag fine grades, so map each internal grade to a percentile of the
# model's sold-price distribution — better condition sells at the higher end of the range.
GRADE_PERCENTILE = {"NEW": 0.80, "A+": 0.75, "A": 0.62, "B": 0.45, "C": 0.30}

# Carrier names -> a carrier-LOCKED unit (sells well below our unlocked stock, not comparable).
_CARRIER_LOCKED = (
    "telus", "koodo", "bell", "rogers", "fido", "virgin", "public mobile", "chatr", "freedom",
    "dish", "cricket", "boost", "metro", "t-mobile", "tmobile", "straight talk", "at&t", "att ",
    "verizon", "tracfone", "mint", "xfinity", "spectrum", "us cellular", "consumer cellular",
)
# Non-comparable listings: damaged / for-parts / bulk lots.
_EXCLUDE_PHRASES = (
    "for parts", "parts only", "parts/repair", "not working", "doesn't work", "does not work",
    "broken", "cracked", "damaged", "as is", "as-is", "read description", "read desc", "spares",
    "faulty", "lot of", "bundle", "wholesale", "x2", "x3", "x 2", "x 3",
    "case for", "cover for", "screen protector",   # accessories is_accessory's phrases can miss
)

# Title-matching (mirrors reebelo/bestbuy): drop brand words, require every keyword token as a
# substring, and require model qualifiers on both sides or neither.
_BRANDS = {"apple", "samsung", "google", "motorola", "moto", "sonim", "tcl", "huawei",
           "alcatel", "lg", "oneplus", "nokia"}
_MODEL_QUALIFIERS = {"mini", "pro", "max", "plus", "ultra", "se", "fe", "air",
                     "classic", "lite", "neo", "active"}


def scrape_and_return_all(keywords_list, min_price=DEFAULT_MIN_PRICE, max_results=PER_KEYWORD):
    """Fetch comparable eBay CA sold listings per keyword.

    Returns:
        dict mapping keyword -> list of {title, price, condition, url, sold_at}.
    """
    keywords = list(dict.fromkeys(keywords_list or []))
    grouped = {kw: [] for kw in keywords}
    if not keywords:
        return grouped

    log.info("Fetching eBay CA SOLD comps via %s for %d keyword(s)...", ACTOR_ID, len(keywords))
    for i, kw in enumerate(keywords):
        if i:
            time.sleep(INTER_KEYWORD_DELAY)
        grouped[kw] = _fetch_one(kw, min_price, max_results)

    hits = sum(1 for v in grouped.values() if v)
    log.info("eBay CA (sold comps): %d/%d keywords with comparable sold listings.", hits, len(keywords))
    return grouped


def _fetch_one(keyword, min_price, max_results):
    run_input = {
        "keywords": [keyword],
        "ebaySite": "ebay.ca",
        "count": max_results,
        "daysToScrape": SOLD_WINDOW_DAYS,
        "itemCondition": "used",
    }
    rows = apify_client.run_actor(ACTOR_ID, run_input)
    tokens = _match_tokens(keyword)
    out = []
    for row in rows:
        title = row.get("title") or ""
        price = _to_price(row.get("soldPrice"))
        if price is None or (min_price and price < min_price):
            continue
        if (row.get("soldCurrency") or "CAD") != "CAD":
            continue
        if is_accessory(title) or _excluded(title):
            continue
        if not _title_matches(title, tokens):
            continue
        out.append({"title": title, "price": price, "condition": row.get("condition") or "",
                    "url": row.get("url"), "sold_at": row.get("endedAt")})
    log.info("eBay CA: %d comparable sold for '%s' (of %d rows).", len(out), keyword, len(rows))
    return out


def get_floor_price_for_grade(grouped_results, keyword, grade):
    """eBay competitor price for the keyword at this grade.

    Sold data isn't grade-tagged, so we map the grade to a percentile of the comparable
    sold-price distribution (better condition sells at the higher end): A+/A high, B mid,
    C low. Unknown grades fall back to the median. Returns float or None.
    """
    items = grouped_results.get(keyword) or []
    prices = sorted(it["price"] for it in items if it.get("price"))
    if not prices:
        log.info("eBay CA: no comparable sold for '%s' Grade %s.", keyword, grade)
        return None
    q = GRADE_PERCENTILE.get(grade, 0.50)
    val = round(_percentile(prices, q), 2)
    log.info("eBay CA sold p%d for '%s' Grade %s: $%.2f (n=%d, median $%.2f).",
             int(q * 100), keyword, grade, val, len(prices), statistics.median(prices))
    return val


def _percentile(sorted_vals, q):
    """Linear-interpolated percentile (q in [0,1]) of a pre-sorted list."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = q * (len(sorted_vals) - 1)
    lo = int(idx)
    frac = idx - lo
    if lo + 1 < len(sorted_vals):
        return sorted_vals[lo] + frac * (sorted_vals[lo + 1] - sorted_vals[lo])
    return sorted_vals[lo]


# --- helpers ---------------------------------------------------------------

def _to_price(value):
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        m = re.search(r"[\d,]+\.?\d*", value.replace(",", ""))
        if m:
            try:
                f = float(m.group())
                return f if f > 0 else None
            except ValueError:
                return None
    return None


def _excluded(title):
    t = (title or "").lower()
    return any(c in t for c in _CARRIER_LOCKED) or any(p in t for p in _EXCLUDE_PHRASES)


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
