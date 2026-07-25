"""Unit tests for ecommerce.pricing.proxy (Apify residential proxy + block detection)."""
from ecommerce.pricing import proxy
from ecommerce import config


def test_apify_proxy_url_present(monkeypatch):
    monkeypatch.setattr(config, "APIFY_PROXY_PASSWORD", "pw123")
    assert proxy.apify_proxy_url() == \
        "http://groups-RESIDENTIAL,country-CA:pw123@proxy.apify.com:8000"


def test_apify_proxy_url_absent(monkeypatch):
    monkeypatch.setattr(config, "APIFY_PROXY_PASSWORD", "")
    assert proxy.apify_proxy_url() is None


def test_proxies_for_on(monkeypatch):
    monkeypatch.setattr(config, "APIFY_PROXY_PASSWORD", "pw")
    proxies, via = proxy.proxies_for(True, "reebelo")
    assert proxies["http"] == proxies["https"]
    assert proxies["https"].endswith("@proxy.apify.com:8000")
    assert via == "apify-residential"


def test_proxies_for_on_but_unconfigured(monkeypatch):
    monkeypatch.setattr(config, "APIFY_PROXY_PASSWORD", "")
    proxies, via = proxy.proxies_for(True, "reebelo")
    assert proxies is None
    assert "unconfigured" in via


def test_proxies_for_off():
    proxies, via = proxy.proxies_for(False, "bestbuy")
    assert proxies is None
    assert via == "direct(datacenter-IP)"


def test_looks_blocked():
    for s in (403, 429, 500, 503):
        assert proxy.looks_blocked(s), s
    for s in (200, 301, 404):
        assert not proxy.looks_blocked(s), s
