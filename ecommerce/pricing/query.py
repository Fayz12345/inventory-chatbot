"""
Search query construction for marketplace scrapers.

Converts internal (Manufacturer, Model) identifiers from ReportingInventoryFlat
into shopper-style search queries. The raw Model values embed SKU codes and
nested descriptions (e.g. "XT2417-1 (Moto G 5G (2024))") which match parts
catalogs on the marketplaces instead of whole devices, so we strip the codes
and lift the human-readable description out of the parentheses.

Examples:
    ('Motorola', 'XT2417-1 (Moto G 5G (2024))')      -> 'Motorola Moto G 5G 2024'
    ('Samsung',  'L315F (Galaxy watch 7 44 MM) LTE')  -> 'Samsung Galaxy watch 7 44mm LTE'
    ('Apple',    'iPhone 14 Pro Max')                 -> 'Apple iPhone 14 Pro Max'
"""

import re

# Two SKU regexes:
# - _SKU_BEFORE_PAREN: permissive — catches Galaxy Book "NP960XHA-KG1CA" and
#   old Tab "950XDB-KA1". Applied ONLY to tokens before the parens, where the
#   manufacturer name + SKU live; safe because legitimate product names like
#   "S25" never appear in that position.
# - _SKU_FALLBACK: conservative — used when the Model has no parens at all, to
#   avoid stripping legitimate names like "S25" or "iPhone 14" that look like
#   SKUs in isolation.
_SKU_BEFORE_PAREN = re.compile(r"^(?:[A-Z]{1,4}\d+|\d{3,4}[A-Z]+)[A-Z0-9-]*$")
_SKU_FALLBACK = re.compile(r"\b[A-Z]{1,4}\d+(?:-\d+)?[A-Z]?\b")
_OUTER_PAREN_PATTERN = re.compile(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
_MM_PATTERN = re.compile(r"\b(\d+)\s*MM\b")
_MULTI_WS = re.compile(r"\s+")


def clean_search_query(manufacturer: str, model: str) -> str:
    """Build a shopper-style search query from raw Manufacturer + Model fields."""
    if not manufacturer and not model:
        return ""

    text = f"{manufacturer or ''} {model or ''}".strip()

    paren_match = _OUTER_PAREN_PATTERN.search(text)
    if paren_match:
        inside = re.sub(r"[()]", " ", paren_match.group(1))
        before = text[: paren_match.start()]
        after = text[paren_match.end():]
        before_words = [w for w in before.split() if not _SKU_BEFORE_PAREN.fullmatch(w)]
        result = " ".join(before_words + [inside, after])
    else:
        result = _SKU_FALLBACK.sub("", text)

    result = _MM_PATTERN.sub(lambda m: f"{m.group(1)}mm", result)
    result = _MULTI_WS.sub(" ", result).strip()

    return result
