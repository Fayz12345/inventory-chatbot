"""Unit tests for config credential resolution + _have_creds (ADO #198 / 1D.10 #8).

`_resolve()` picks the sandbox or production credential off a `*_ENV` toggle;
`_have_creds()` in each listing module gates whether a post is attempted.
"""
from ecommerce import config
from ecommerce.listings import amazon as amazon_listings
from ecommerce.listings import ebay as ebay_listings


# ---------------------------------------------------------------------------
# _resolve sandbox/prod toggle
# ---------------------------------------------------------------------------

def test_resolve_uses_sandbox_when_toggle_is_sandbox(monkeypatch):
    monkeypatch.setenv("DEMO_ENV", "sandbox")
    monkeypatch.setenv("DEMO_KEY", "prod-value")
    monkeypatch.setenv("DEMO_KEY_SANDBOX", "sandbox-value")
    assert config._resolve("DEMO_ENV", "DEMO_KEY", "DEMO_KEY_SANDBOX") == "sandbox-value"


def test_resolve_uses_production_when_toggle_is_production(monkeypatch):
    monkeypatch.setenv("DEMO_ENV", "production")
    monkeypatch.setenv("DEMO_KEY", "prod-value")
    monkeypatch.setenv("DEMO_KEY_SANDBOX", "sandbox-value")
    assert config._resolve("DEMO_ENV", "DEMO_KEY", "DEMO_KEY_SANDBOX") == "prod-value"


def test_resolve_defaults_to_sandbox_when_toggle_unset(monkeypatch):
    monkeypatch.delenv("DEMO_ENV", raising=False)
    monkeypatch.setenv("DEMO_KEY_SANDBOX", "sandbox-value")
    assert config._resolve("DEMO_ENV", "DEMO_KEY", "DEMO_KEY_SANDBOX") == "sandbox-value"


def test_resolve_is_case_insensitive_on_production(monkeypatch):
    monkeypatch.setenv("DEMO_ENV", "PRODUCTION")
    monkeypatch.setenv("DEMO_KEY", "prod-value")
    monkeypatch.setenv("DEMO_KEY_SANDBOX", "sandbox-value")
    assert config._resolve("DEMO_ENV", "DEMO_KEY", "DEMO_KEY_SANDBOX") == "prod-value"


# ---------------------------------------------------------------------------
# _have_creds — eBay
# ---------------------------------------------------------------------------

def test_ebay_have_creds_false_when_any_missing(monkeypatch):
    monkeypatch.setattr(config, "EBAY_APP_ID", "")
    monkeypatch.setattr(config, "EBAY_CERT_ID", "cert")
    monkeypatch.setattr(config, "EBAY_REFRESH_TOKEN", "refresh")
    assert ebay_listings._have_creds() is False


def test_ebay_have_creds_true_when_all_present(monkeypatch):
    monkeypatch.setattr(config, "EBAY_APP_ID", "app")
    monkeypatch.setattr(config, "EBAY_CERT_ID", "cert")
    monkeypatch.setattr(config, "EBAY_REFRESH_TOKEN", "refresh")
    assert ebay_listings._have_creds() is True


# ---------------------------------------------------------------------------
# _have_creds — Amazon
# ---------------------------------------------------------------------------

def test_amazon_have_creds_false_when_any_missing(monkeypatch):
    monkeypatch.setattr(config, "AMAZON_SELLER_ID", "seller")
    monkeypatch.setattr(config, "AMAZON_REFRESH_TOKEN", "")
    monkeypatch.setattr(config, "AMAZON_LWA_APP_ID", "lwa")
    monkeypatch.setattr(config, "AMAZON_LWA_CLIENT_SECRET", "secret")
    assert amazon_listings._have_creds() is False


def test_amazon_have_creds_true_when_all_present(monkeypatch):
    monkeypatch.setattr(config, "AMAZON_SELLER_ID", "seller")
    monkeypatch.setattr(config, "AMAZON_REFRESH_TOKEN", "refresh")
    monkeypatch.setattr(config, "AMAZON_LWA_APP_ID", "lwa")
    monkeypatch.setattr(config, "AMAZON_LWA_CLIENT_SECRET", "secret")
    assert amazon_listings._have_creds() is True


# ---------------------------------------------------------------------------
# Amazon productType mapping (#198 / 1D.10 #3)
# ---------------------------------------------------------------------------

def test_product_type_defaults_to_phone_when_unknown():
    assert amazon_listings._product_type(None) == "WIRELESS_PHONE"
    assert amazon_listings._product_type("Wearable Gizmo") == "WIRELESS_PHONE"


def test_product_type_maps_known_categories():
    assert amazon_listings._product_type("Handset") == "WIRELESS_PHONE"
    assert amazon_listings._product_type("Tablet") == "TABLET_COMPUTER"
    assert amazon_listings._product_type("Laptop") == "NOTEBOOK_COMPUTER"
    assert amazon_listings._product_type("Smart Watch") == "WATCH"
