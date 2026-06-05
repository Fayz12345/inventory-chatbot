"""OSL billing fee schedule — sections keyed by DEVICE CATEGORY.

Verified 2026-06-01 against the team's `OSL Billing March.xlsx`. The category
mapping uses `MasterCarrierManufacturerLookup.Device_Handset` (TOP 1 by
LastUpdateDate, joined on ManufacturerVerb+Model). The OSL flat table's own
`ML_Device_Handset` column is misleadingly named — it holds status (Open Box
/ New / Disposal List), NOT device category — so we resolve category via the
master-data lookup at query time.

Section -> list of Device_Handset values:
  Mobile Phones            -> ['Handset']
  Laptops                  -> ['Laptop']
  TVs                      -> ['TV']
  Tablets, Wearables, Buds -> ['Tablet', 'Smart Watch', 'Earphones']
  Accessories              -> manual (everything else; needs business sign-off)

Item fields:
  label      : str — line item name shown in the report
  column     : str | None — flat-table datetime column to count (None = manual)
  fee        : float | None — $ per unit (None = editable manual TBD)
  mode       : 'count' | 'manual'
"""

# Datetime columns we are allowed to COUNT over (defense-in-depth allowlist).
COUNT_COLUMNS = {
    "Receive_OSL_Created",
    "QC_Assessment_Created",
    "Shipping_OSL_Created",
}

# Section name -> Device_Handset values that fall into that section.
# Accessories is intentionally absent — it's manual + a diagnostic count of
# unmapped devices is shown in the UI.
OSL_SECTION_CATEGORIES = {
    "Mobile Phones":            ["Handset"],
    "Laptops":                  ["Laptop"],
    "TVs":                      ["TV"],
    "Tablets, Wearables, Buds": ["Tablet", "Smart Watch", "Earphones"],
}

# Categories with explicit section mapping (used by the unmapped diagnostic).
MAPPED_CATEGORIES = sorted(
    {c for cats in OSL_SECTION_CATEGORIES.values() for c in cats}
)


def _count(label, column, fee):
    return {
        "label": label, "column": column,
        "fee": float(fee), "mode": "count",
    }


def _manual(label, fee):
    return {
        "label": label, "column": None,
        "fee": None if fee is None else float(fee), "mode": "manual",
    }


OSL_FEE_SCHEDULE = [
    {"name": "Mobile Phones", "items": [
        _count("Receive",  "Receive_OSL_Created",     2.50),
        _count("QC",       "QC_Assessment_Created",   6.00),
        _count("Shipping", "Shipping_OSL_Created",    1.50),
    ]},
    {"name": "Laptops", "items": [
        _count("Receive",  "Receive_OSL_Created",     2.50),
        _count("QC",       "QC_Assessment_Created",  13.50),
        _count("Shipping", "Shipping_OSL_Created",    1.50),
    ]},
    {"name": "TVs", "items": [
        _count("Receive",  "Receive_OSL_Created",     2.50),
        _count("QC",       "QC_Assessment_Created",  13.50),
        _count("Shipping", "Shipping_OSL_Created",    1.50),
    ]},
    {"name": "Tablets, Wearables, Buds", "items": [
        _count("Receive",  "Receive_OSL_Created",     2.50),
        _count("QC",       "QC_Assessment_Created",   6.00),
        _count("Shipping", "Shipping_OSL_Created",    1.50),
    ]},
    {"name": "Accessories", "items": [
        _manual("Receive & Dispose", 1.50),
        _manual("(secondary rate — clarify before invoicing)", 0.25),
    ]},
]
