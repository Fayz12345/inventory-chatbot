"""Unit tests for apify_client.run_actor retry behaviour.

Covers the Batch #17 eBay fix: an actor that exits SUCCEEDED with 0 items (antibot
block) must be retried when retry_on_empty=True, but empty is accepted as-is by
default so we don't pay for pointless retries on genuine no-match actors.
"""
from unittest.mock import patch

from ecommerce.pricing import apify_client


@patch("ecommerce.pricing.apify_client.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.apify_client._get_client", lambda: object())
@patch("ecommerce.pricing.apify_client._run_actor_once")
def test_retry_on_empty_recovers(mock_once):
    mock_once.side_effect = [[], [{"price": 5}]]     # blocked-empty, then data
    out = apify_client.run_actor("x", {}, max_retries=2, retry_on_empty=True)
    assert out == [{"price": 5}]
    assert mock_once.call_count == 2


@patch("ecommerce.pricing.apify_client.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.apify_client._get_client", lambda: object())
@patch("ecommerce.pricing.apify_client._run_actor_once")
def test_retry_on_empty_exhausts(mock_once):
    mock_once.side_effect = [[], [], []]             # empty every attempt
    out = apify_client.run_actor("x", {}, max_retries=2, retry_on_empty=True)
    assert out == []
    assert mock_once.call_count == 3


@patch("ecommerce.pricing.apify_client.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.apify_client._get_client", lambda: object())
@patch("ecommerce.pricing.apify_client._run_actor_once")
def test_default_accepts_empty_without_retry(mock_once):
    mock_once.side_effect = [[]]                     # empty accepted as "no match"
    out = apify_client.run_actor("x", {})            # retry_on_empty defaults False
    assert out == []
    assert mock_once.call_count == 1


@patch("ecommerce.pricing.apify_client.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.apify_client._get_client", lambda: object())
@patch("ecommerce.pricing.apify_client._run_actor_once")
def test_retries_on_non_succeeded(mock_once):
    mock_once.side_effect = [None, [{"price": 9}]]   # None = non-SUCCEEDED -> retry
    out = apify_client.run_actor("x", {}, max_retries=1)
    assert out == [{"price": 9}]
    assert mock_once.call_count == 2
