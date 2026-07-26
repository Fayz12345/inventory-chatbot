"""Tests for the post-scrape run report (#3): the RunReport collector/renderer,
the M365 mailer guards, and that run_pipeline always emails a report — including
capturing a scrape source that failed (e.g. eBay antibot)."""
from unittest.mock import patch

from ecommerce.notifications.run_report import RunReport
from ecommerce.notifications import mailer


# ---------------------------------------------------------------------------
# RunReport
# ---------------------------------------------------------------------------

def test_report_flags_failures_with_reasons():
    r = RunReport()
    r.record_source("Amazon CA", "Apify actor", ok=True, hits=10, total=12)
    r.record_source("eBay CA", "Apify actor", ok=False, hits=0, total=12)         # antibot
    r.record_source("Reebelo CA", "browser API", ok=False, total=12,
                    detail="scrape raised: ConnectionError: proxy 403")
    assert r.has_failures()
    names = [n for n, _ in r.failures()]
    assert "eBay CA" in names and "Reebelo CA" in names and "Amazon CA" not in names
    html = r.render_html()
    assert "failure(s) this run" in html
    assert "antibot" in html                      # inferred reason for 0/total
    assert "proxy 403" in html                    # explicit exception reason


def test_report_all_ok_has_no_failures_and_green_banner():
    r = RunReport()
    r.record_source("Amazon CA", "Apify actor", ok=True, hits=12, total=12)
    r.set_batch(22, 12, 0)
    assert not r.has_failures()
    assert "All scraping sources succeeded" in r.render_html()
    assert "OK" in r.subject() and "#22" in r.subject()


def test_report_pipeline_error_is_a_failure():
    r = RunReport()
    r.record_source("Amazon CA", "Apify actor", ok=True, hits=1, total=1)
    r.set_error(RuntimeError("DB unreachable"))
    assert r.has_failures()
    assert "DB unreachable" in r.render_html() and "FAILURES" in r.subject()


# ---------------------------------------------------------------------------
# mailer guards
# ---------------------------------------------------------------------------

def test_recipients_parses_comma_and_semicolon():
    assert mailer.recipients("a@x.com, b@y.com; c@z.com") == ["a@x.com", "b@y.com", "c@z.com"]
    assert mailer.recipients(["a@x.com", " ", "b@y.com"]) == ["a@x.com", "b@y.com"]


def test_send_email_skips_when_no_recipients():
    assert mailer.send_email("", "s", "<p>x</p>") is False


@patch("ecommerce.notifications.mailer.is_configured", return_value=False)
def test_send_email_skips_when_m365_unconfigured(_cfg):
    assert mailer.send_email("a@x.com", "s", "<p>x</p>") is False


# ---------------------------------------------------------------------------
# run_pipeline always sends the report, capturing a failed source
# ---------------------------------------------------------------------------

_PROD = {"Manufacturer": "Samsung", "Model": "S25", "Colour": "Black", "Grade": "A", "Quantity": 3}


@patch("ecommerce.notifications.mailer.send_email")
@patch("ecommerce.main.db.save_pricing_batch", return_value=99)
@patch("ecommerce.main.recommend",
       return_value={"margin_ok": True, "marketplace": "Amazon CA", "price": 150.0})
@patch("ecommerce.main.db.fetch_device_cost", return_value=100.0)
@patch("ecommerce.main.reebelo_pricing.scrape_and_return_all", return_value={})
@patch("ecommerce.main.bestbuy_pricing.scrape_and_return_all", return_value={})
@patch("ecommerce.main.ebay_pricing.scrape_and_return_all",
       side_effect=RuntimeError("antibot boom"))
@patch("ecommerce.main.amazon_pricing.scrape_prices_by_keyword",
       return_value={"Samsung S25": 150.0})
@patch("ecommerce.main.clean_search_query", return_value="Samsung S25")
@patch("ecommerce.main.categorize.apply_scope",
       return_value=([_PROD], {"groups_after": 1, "models": 1, "by_category": {"phone": 1}}))
@patch("ecommerce.main.db.get_scrape_settings",
       return_value={"categories": ["phone"], "scope_mode": "all", "top_n": None})
@patch("ecommerce.main.db.fetch_all_pending_products", return_value=[_PROD])
def test_pipeline_sends_report_and_captures_scrape_failure(
        _prod, _settings, _scope, _ckw, _amz, _ebay, _bb, _reb, _cost, _rec, _save, mock_send):
    from ecommerce.main import run_pipeline
    run_pipeline()
    mock_send.assert_called_once()
    subject, html = mock_send.call_args.args[1], mock_send.call_args.args[2]
    assert "FAILURES" in subject                       # eBay raised -> failures
    assert "eBay CA" in html and "antibot boom" in html
    assert "Amazon CA" in html                          # a successful source still listed
