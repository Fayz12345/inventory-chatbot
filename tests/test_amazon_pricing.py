"""Unit tests for Amazon pricing variant matching.

Amazon's actor is pure keyword search — its top relevance results mix wrong
years/storages/models. These lock the variant gate (title tokens + plus/pro/max
parity) using the REAL titles Amazon.ca returned for batch #21, plus the
accessory/min-price backstops and the Amazon-specific "RAM+storage" `+` handling.
The actor is mocked at the apify_client seam.
"""
from unittest.mock import patch

from ecommerce.pricing import amazon


def _row(name, price):
    return {"name": name, "price": price}


def _floor(rows, keyword, **kw):
    with patch("ecommerce.pricing.amazon.apify_client") as mock_ac:
        mock_ac.run_actor.return_value = rows
        return amazon.scrape_prices_by_keyword([keyword], **kw)[keyword]


# --- real batch #21 regression cases ---------------------------------------

def test_g_play_2026_excludes_wrong_year_and_keeps_ram_plus_storage_title():
    # Real batch #21 set. Today the 2024 ($119.99) sets the floor. The 2026 rows
    # must win — including the "64GB + 4GB RAM" one, whose join "+" must NOT be read
    # as the model "Plus" (that would wrongly drop it on qualifier parity).
    rows = [
        _row("Moto G Play 5G (2026) (64GB) 6.7 120Hz, 32MP Camera, Unlocked - Pantone Tapestry", None),
        _row("Motorola Moto G Play 5G (2026) (64GB) 6.7 120Hz, Unlocked - Pantone Tapestry (Renewed)", 160.0),
        _row("Motorola Moto G Play 2026, 64GB + 4GB RAM, Pantone Tapestry - Unlocked (Renewed)", 158.58),
        _row("Motorola Moto G Play 2024 (64GB) 6.5\" Display, 50MP Camera, Sapphire Blue (Renewed)", 119.99),
    ]
    assert _floor(rows, "Motorola Moto G Play 2026 -64GB") == 158.58


def test_edge_plus_no_true_variant_returns_none():
    # Real batch #21 Edge+ set — none is the Edge PLUS or 512GB. Returning no price
    # beats the bogus $177.99 (a 2022 128GB). Note "8GB+256GB"/"512GB+12GB" joins
    # must not fabricate a "plus" token that fakes a match.
    rows = [
        _row("Motorola Moto Edge 2023 8GB+256GB Black (Renewed)", 233.75),
        _row("Moto Edge 2023 8GB+256GB Black", 399.99),
        _row("Motorola Edge 5G 2023 (256GB) Unlocked - Eclipse Black (Renewed)", 227.99),
        _row("Motorola Edge 5G (2025) (256GB) Unlocked - Deep Forest (Renewed)", 374.99),
        _row("Moto Edge 50 Fusion 5G (XT2429-2) 8GB Ram 256GB Storage - (Forest Green)", 379.0),
        _row("Moto Edge 60 Pro 5G (512GB+12GB) XT2507-1 (Pantone Dazzling Blue)", 875.0),
        _row("Motorola Edge 5G (2024) (256GB+8GB RAM) Unlocked Midnight Blue (Renewed)", 290.0),
        _row("Motorola Moto Edge 5G (2022) 128GB + 8GB RAM Unlocked - Mineral Gray (Renewed)", 177.99),
    ]
    assert _floor(rows, "Motorola Moto Edge+ 2023 512GB") is None


def test_edge_plus_matches_a_real_plus_512gb():
    rows = [
        _row("Motorola Moto Edge Plus 2023 XT2301-1 512GB Unlocked (Renewed)", 480.0),
        _row("Motorola Moto Edge 5G 2023 512GB Unlocked (Renewed)", 300.0),   # non-plus -> drop
    ]
    assert _floor(rows, "Motorola Moto Edge+ 2023 512GB") == 480.0


def test_g_stylus_excludes_wrong_year_2025():
    # Real batch #21: floor $219 is a real 2024; the 2025 ($299.99) must be dropped.
    rows = [
        _row("Motorola Moto G Stylus 5G 2024 (256GB, 8GB) Unlocked (Caramel Latte) (Renewed)", 231.0),
        _row("Moto G Stylus 5G | 8/256GB | 2024 | Factory Unlocked | Caramel Latte (Renewed)", 232.0),
        _row("Motorola Moto G Stylus 5G 2025 | 128GB, 8GB | Unlocked (Renewed)", 299.99),
        _row("Motorola Moto G Stylus 5G 2024 (128GB, 8GB) Unlocked (Caramel Latte) (Renewed)", 219.0),
    ]
    assert _floor(rows, "Motorola Moto G Stylus 5G 2024") == 219.0


# --- gate mechanics ---------------------------------------------------------

def test_wrong_storage_excluded_when_keyword_has_storage():
    rows = [
        _row("Samsung Galaxy S24 256GB Unlocked Black", 700.0),
        _row("Samsung Galaxy S24 128GB Unlocked Black", 600.0),   # wrong storage -> drop
    ]
    assert _floor(rows, "Samsung Galaxy S24 256GB") == 700.0


def test_accessory_and_min_price_backstops_still_apply():
    rows = [
        _row("(3 Pack) Screen Protector for Motorola Moto G Stylus 5G 2024 Tempered Glass", 9.85),  # accessory
        _row("Motorola Moto G Stylus 5G 2024 128GB Unlocked", 30.0),           # < $40 backstop -> drop
        _row("Motorola Moto G Stylus 5G 2024 128GB Unlocked (Renewed)", 205.0),  # keep
    ]
    assert _floor(rows, "Motorola Moto G Stylus 5G 2024") == 205.0


def test_no_variant_match_returns_none():
    rows = [_row("Apple iPhone 15 Pro 256GB", 1200.0)]
    assert _floor(rows, "Samsung Galaxy S24 256GB") is None


def test_no_results_returns_none():
    assert _floor([], "Samsung Galaxy S24 256GB") is None
