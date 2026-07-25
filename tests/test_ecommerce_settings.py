"""Tests for scrape-scope settings: pure defaults/validation (ecommerce_settings)
plus the SQL Server read/write (ecommerce.db.get_scrape_settings/save_scrape_settings),
with the DB connection mocked (mirrors tests/test_save_pricing_batch.py)."""
import json
from unittest.mock import MagicMock, patch

import ecommerce_settings as es
from ecommerce import db


# --- pure helpers -----------------------------------------------------------

def test_defaults():
    assert es.DEFAULTS == {"categories": ["phone", "wearable", "tablet"],
                           "scope_mode": "top_sku", "top_n": 30}


def test_sanitize_filters_junk_and_bad_values():
    cats, mode, n = es.sanitize(["phone", "junk", "laptop"], "sideways", "abc")
    assert cats == ["phone"] and mode == "all" and n == 30


def test_sanitize_accepts_top_sku():
    cats, mode, n = es.sanitize(["phone"], "top_sku", 4)
    assert mode == "top_sku" and n == 4


def test_sanitize_empty_categories_falls_back():
    cats, mode, n = es.sanitize([], "top", 5)
    assert cats == ["phone", "wearable", "tablet"] and mode == "top" and n == 5


def test_sanitize_top_n_clamped():
    assert es.sanitize(["phone"], "top", 0)[2] == 1
    assert es.sanitize(["phone"], "top", 999999)[2] == 10000


# --- SQL Server read (get_scrape_settings) ----------------------------------

@patch("ecommerce.db.get_db_connection")
def test_get_returns_defaults_when_no_row(mock_conn):
    conn, cur = MagicMock(), MagicMock()
    mock_conn.return_value = conn
    conn.cursor.return_value = cur
    cur.fetchone.return_value = None
    assert db.get_scrape_settings() == es.DEFAULTS


@patch("ecommerce.db.get_db_connection")
def test_get_parses_row(mock_conn):
    conn, cur = MagicMock(), MagicMock()
    mock_conn.return_value = conn
    conn.cursor.return_value = cur
    row = MagicMock()
    row.Categories = json.dumps(["phone", "accessory"])
    row.ScopeMode = "top"
    row.TopN = 25
    row.UpdatedAt = "2026-07-25"
    row.UpdatedBy = "tester"
    cur.fetchone.return_value = row
    s = db.get_scrape_settings()
    assert s["categories"] == ["phone", "accessory"]
    assert s["scope_mode"] == "top"
    assert s["top_n"] == 25
    assert s["updated_by"] == "tester"


@patch("ecommerce.db.get_db_connection")
def test_get_defaults_when_table_missing(mock_conn):
    # e.g. the one-time CREATE TABLE hasn't been run yet -> never crash the pipeline.
    mock_conn.side_effect = Exception("Invalid object name 'EcommerceScrapeSettings'")
    assert db.get_scrape_settings() == es.DEFAULTS


# --- SQL Server write (save_scrape_settings) --------------------------------

@patch("ecommerce.db.get_db_connection")
def test_save_updates_existing_row(mock_conn):
    conn, cur = MagicMock(), MagicMock()
    mock_conn.return_value = conn
    conn.cursor.return_value = cur
    cur.rowcount = 1                       # UPDATE hit the row
    out = db.save_scrape_settings(["phone", "accessory"], "top", 25, actor="t")
    assert out == {"categories": ["phone", "accessory"], "scope_mode": "top", "top_n": 25}
    assert cur.execute.call_count == 1     # UPDATE only, no INSERT
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


@patch("ecommerce.db.get_db_connection")
def test_save_inserts_when_no_row(mock_conn):
    conn, cur = MagicMock(), MagicMock()
    mock_conn.return_value = conn
    conn.cursor.return_value = cur
    cur.rowcount = 0                       # UPDATE matched nothing -> INSERT
    db.save_scrape_settings(["phone"], "all", 30, actor="t")
    assert cur.execute.call_count == 2     # UPDATE then INSERT
    conn.commit.assert_called_once()


@patch("ecommerce.db.get_db_connection")
def test_save_sanitizes_before_persisting(mock_conn):
    conn, cur = MagicMock(), MagicMock()
    mock_conn.return_value = conn
    conn.cursor.return_value = cur
    cur.rowcount = 1
    out = db.save_scrape_settings(["phone", "junk"], "weird", "abc", actor="t")
    assert out == {"categories": ["phone"], "scope_mode": "all", "top_n": 30}
    # the JSON persisted is the sanitised category list
    persisted = json.loads(cur.execute.call_args.args[1][0])
    assert persisted == ["phone"]
