"""Unit tests for ecommerce.pricing.query.clean_search_query.

The function turns raw (Manufacturer, Model) values from ReportingInventoryFlat
into shopper-style search queries. Failures here cascade across all four
marketplaces (Amazon/eBay/Best Buy/Reebelo) because every scraper takes the
output of this function as input.
"""
import pytest

from ecommerce.pricing.query import clean_search_query


@pytest.mark.parametrize("manufacturer, model, expected", [
    # Canonical examples from the module docstring.
    ("Motorola", "XT2417-1 (Moto G 5G (2024))",       "Motorola Moto G 5G 2024"),
    ("Samsung",  "L315F (Galaxy watch 7 44 MM) LTE",  "Samsung Galaxy watch 7 44mm LTE"),
    ("Apple",    "iPhone 14 Pro Max",                  "Apple iPhone 14 Pro Max"),

    # Real-world OSL/TMS shapes that surfaced during the billing audit.
    ("Samsung",  "S938W (S25 Ultra 256 GB)",          "Samsung S25 Ultra 256 GB"),
    ("Samsung",  "A366W (A36 128GB)",                 "Samsung A36 128GB"),
    ("Samsung",  "Q502 (Galaxy Ring - Size 12)",      "Samsung Galaxy Ring - Size 12"),
    ("Samsung",  "R390 (Galaxy Fit3)",                "Samsung Galaxy Fit3"),
    ("Samsung",  "NP960XHA-KG1CA (Galaxy Book 5 Pro 1TB)",
                                                     "Samsung Galaxy Book 5 Pro 1TB"),

    # Galaxy Book Pro 950XDB — old part code that starts with digits, was a
    # blind-spot of the original regex; verifies the permissive before-paren
    # pattern handles digit-leading SKUs.
    ("Samsung",  "950XDB-KA1 (Galaxy Book Pro)",     "Samsung Galaxy Book Pro"),
])
def test_canonical_inputs(manufacturer, model, expected):
    assert clean_search_query(manufacturer, model) == expected


def test_strips_simple_sku_code_when_no_parens():
    # Model with no parenthetical description: just drop the SKU code.
    assert clean_search_query("Samsung", "XT2417-1") == "Samsung"


def test_no_sku_code_passthrough():
    # Already-clean model name should round-trip with manufacturer prefixed.
    assert clean_search_query("Apple", "iPhone 16 Pro Max 256GB") == "Apple iPhone 16 Pro Max 256GB"


def test_mm_normalised_lowercase():
    # 44 MM -> 44mm (shopper-friendly), no extra space before unit.
    out = clean_search_query("Samsung", "R955 (Galaxy Watch 6 Classic 43 MM LTE)")
    assert "43mm" in out
    assert "43 MM" not in out
    assert "R955" not in out  # SKU dropped


def test_empty_inputs_return_empty_string():
    assert clean_search_query("", "") == ""
    assert clean_search_query(None, None) == ""


def test_manufacturer_only():
    # Some rows have no Model — should still return something usable.
    assert clean_search_query("Samsung", None) == "Samsung"
    assert clean_search_query("Samsung", "") == "Samsung"


def test_model_only():
    # Some rows have no Manufacturer — should not crash.
    out = clean_search_query("", "iPhone 14")
    assert "iPhone 14" in out


def test_multiple_whitespace_collapsed():
    # Internal multi-spaces should be a single space (output cleanliness).
    out = clean_search_query("Samsung", "S938W   (S25 Ultra)")
    assert "  " not in out
    assert out == "Samsung S25 Ultra"


def test_no_orphaned_parens():
    # Output should never leak literal '(' or ')' from the source Model.
    out = clean_search_query("Motorola", "XT2417-1 (Moto G 5G (2024))")
    assert "(" not in out
    assert ")" not in out


def test_non_idempotent_documented():
    """Documented behavior: the no-parens branch applies the conservative SKU
    regex to the whole string. Names like 'S25' or 'iPhone 14' in isolation
    look SKU-shaped and would be stripped. Production never feeds cleaned
    output back through the function (it's called once on raw DB rows), so
    this is acceptable. Lock the behavior so a future change doesn't regress
    the parens-branch silently.
    """
    cleaned = clean_search_query("Samsung", "S938W (S25 Ultra 256 GB)")
    assert cleaned == "Samsung S25 Ultra 256 GB"   # parens branch preserves S25
    twice = clean_search_query("", cleaned)        # no parens -> conservative strip
    assert twice == "Samsung Ultra 256 GB"         # S25 stripped — known behavior
