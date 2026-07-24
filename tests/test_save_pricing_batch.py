"""Unit tests for db.save_pricing_batch — the single-connection transactional save
that fixes the 'pending' batch bug (large batches never got marked 'ready' because
the per-row-connection storm throttled the final status update)."""
from unittest.mock import MagicMock, patch

import pytest

from ecommerce import db


def _rec(mp="Amazon", price=100.0, ok=True):
    return {
        "product": {"Manufacturer": "Samsung", "Model": "Galaxy S21",
                    "Colour": "Black", "Grade": "A", "Quantity": 2},
        "marketplace": mp, "price": price,
        "amazon_price": 100.0, "ebay_price": None,
        "bestbuy_price": None, "reebelo_price": None,
        "device_cost": 60.0, "margin_ok": ok, "skip_reason": None,
    }


@patch("ecommerce.db.get_db_connection")
def test_one_connection_and_marks_ready(mock_get_conn):
    conn, cursor = MagicMock(), MagicMock()
    mock_get_conn.return_value = conn
    conn.cursor.return_value = cursor
    cursor.execute.return_value.fetchone.return_value = [42]   # OUTPUT INSERTED.ID

    batch_id = db.save_pricing_batch([_rec(), _rec(mp="eBay", ok=False)])

    assert batch_id == 42
    assert mock_get_conn.call_count == 1        # ONE connection, not one-per-row
    conn.commit.assert_called_once()            # single commit for the whole batch
    conn.close.assert_called_once()
    # the final statement flips the batch to 'ready'
    last = cursor.execute.call_args_list[-1]
    assert last.args[1] == ("ready", 42)


@patch("ecommerce.db.get_db_connection")
def test_no_partial_commit_and_always_closes_on_error(mock_get_conn):
    conn, cursor = MagicMock(), MagicMock()
    mock_get_conn.return_value = conn
    conn.cursor.return_value = cursor

    def fake_execute(sql, params=None):
        m = MagicMock()
        if "INSERT INTO EcommercePricingRecommendation" in sql:
            raise RuntimeError("bad row")
        m.fetchone.return_value = [7]
        return m
    cursor.execute.side_effect = fake_execute

    with pytest.raises(RuntimeError):
        db.save_pricing_batch([_rec()])

    conn.commit.assert_not_called()             # all-or-nothing: no partial batch
    conn.close.assert_called_once()             # finally: connection always closed
