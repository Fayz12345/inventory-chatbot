"""Unit tests for the eBay offer body's publish prerequisites (ticket 1D.5 - #137).

publishOffer requires a merchant location + the three business policies. These
lock that the offer body carries `merchantLocationKey` + `listingPolicies` when
configured, and degrades cleanly (createOffer still attempted) when they are not.
"""
from unittest.mock import MagicMock, patch

from ecommerce.listings import ebay
from ecommerce import config


def _resp(status, payload=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload or {}
    m.text = str(payload or "")
    return m


def _product():
    return {"Manufacturer": "Samsung", "Model": "Galaxy S21",
            "Colour": "Black", "Grade": "A", "Quantity": 1}


def _copy():
    return {"title": "T", "description": "D", "bullets": ["b"], "condition_note": "C"}


def _base_creds(monkeypatch):
    monkeypatch.setattr(config, "EBAY_APP_ID", "app")
    monkeypatch.setattr(config, "EBAY_CERT_ID", "cert")
    monkeypatch.setattr(config, "EBAY_REFRESH_TOKEN", "rt")
    monkeypatch.setattr(config, "EBAY_CATEGORY_ID", "9355")


@patch.object(ebay, "_get_access_token", return_value="TKN")
@patch.object(ebay, "requests")
def test_offer_body_includes_location_and_policies(mock_requests, _tok, monkeypatch):
    _base_creds(monkeypatch)
    monkeypatch.setattr(config, "EBAY_MERCHANT_LOCATION_KEY", "BRIDGE-CA-01")
    monkeypatch.setattr(config, "EBAY_FULFILLMENT_POLICY_ID", "F1")
    monkeypatch.setattr(config, "EBAY_PAYMENT_POLICY_ID", "P1")
    monkeypatch.setattr(config, "EBAY_RETURN_POLICY_ID", "R1")

    mock_requests.put.return_value = _resp(204)
    mock_requests.post.side_effect = [
        _resp(201, {"offerId": "OF1"}),     # createOffer
        _resp(200, {"listingId": "LST1"}),  # publishOffer
    ]

    result = ebay.create_listing(_product(), 299.99, _copy())

    # listing_id is the offerId (what withdraw/delist operate on), not the
    # public listingId.
    assert result == {"ok": True, "listing_id": "OF1", "env": config.EBAY_ENV}
    offer_body = mock_requests.post.call_args_list[0].kwargs["json"]
    assert offer_body["merchantLocationKey"] == "BRIDGE-CA-01"
    assert offer_body["listingPolicies"] == {
        "fulfillmentPolicyId": "F1", "paymentPolicyId": "P1", "returnPolicyId": "R1",
    }


@patch.object(ebay, "_get_access_token", return_value="TKN")
@patch.object(ebay, "requests")
def test_offer_body_omits_prereqs_when_unconfigured(mock_requests, _tok, monkeypatch):
    _base_creds(monkeypatch)
    monkeypatch.setattr(config, "EBAY_MERCHANT_LOCATION_KEY", "")
    monkeypatch.setattr(config, "EBAY_FULFILLMENT_POLICY_ID", "")
    monkeypatch.setattr(config, "EBAY_PAYMENT_POLICY_ID", "")
    monkeypatch.setattr(config, "EBAY_RETURN_POLICY_ID", "")

    mock_requests.put.return_value = _resp(204)
    mock_requests.post.side_effect = [
        _resp(201, {"offerId": "OF1"}),
        _resp(200, {"listingId": "LST1"}),
    ]

    result = ebay.create_listing(_product(), 299.99, _copy())

    assert result["ok"] is True  # createOffer still attempted, no crash
    offer_body = mock_requests.post.call_args_list[0].kwargs["json"]
    assert "merchantLocationKey" not in offer_body
    assert "listingPolicies" not in offer_body
