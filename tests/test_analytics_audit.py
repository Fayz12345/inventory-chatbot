"""Tests that the Telus Weekly report/export and price-review routes enrich
the admin audit trail via admin_audit.stash(...) (the central app.py hook
writes the actual row; these tests verify the blueprint's stash calls, per
the Phase 1B audit design). Patches analytics.routes.admin_audit.stash
directly so no real DB/audit write is needed.
"""
import os
os.environ.setdefault("USERS_DB_PATH", "/tmp/test_users_chat.db")
os.environ.setdefault("CHAT_LOG_DB_PATH", "/tmp/test_chat_log.db")

from unittest.mock import patch

import app


def _client():
    c = app.chatbot_app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'tester'
        s['role'] = 'admin'
        s['is_admin'] = True
    return c


def _merged_stash_kwargs(mock_stash):
    """Merge every stash(...) call's kwargs (later calls overwrite scalars,
    like the real g.audit accumulator) so tests can assert on the net result
    regardless of how many times the handler called stash()."""
    merged = {}
    for call in mock_stash.call_args_list:
        merged.update(call.kwargs)
    return merged


_SUMMARY = {'total_devices': 5, 'total_lot_value': 1234.5,
            'recommendation_breakdown': {}, 'conditions_breakdown': {}}


def _enriched_row(esn):
    """A fully-populated fake `enriched` row — the Telus Weekly report/export
    templates read many keys off each row, so a sparse fake dict raises a
    Jinja UndefinedError deep in rendering that has nothing to do with the
    audit stash these tests actually check."""
    return {
        'ESN': esn, 'Vendor': 'V', 'ManufacturerVerb': 'Apple', 'ModelVerb': 'iPhone 14',
        'Memory': '128 GB', 'Conditions': 'A', 'Defects_1': None, 'Defects_2': None,
        'Defects_3': None, 'QC_Notes': None, 'unassessed_price': 100, 'Received_Grade': 'A',
        'assessed_price': 100, 'T_Level_Cost': 0, 'T_Part_Cost': 0, 'Parts_Used': None,
        'total_repair_cost': 0, 'Post-Repair_Grade': 'A', 'price_after_repair': 100,
        'upside': 0, 'Grade_Improvement': None, 'T_Level_Improved_Cos': 0,
        'T_Part_Improved_Cost': 0, 'total_improvement_cost': 0, 'Post_Improved_Grade': 'A',
        'total_repair_plus_improvement': 0, 'price_after_improvement': 100,
        'improvement_upside': 0, 'recommendation': 'Sell', 'lot_value': 100,
    }


# ---------------------------------------------------------------------------
# telus_weekly_report
# ---------------------------------------------------------------------------

@patch("analytics.routes.admin_audit.stash")
@patch("analytics.routes.pricing.compute_report", return_value=([_enriched_row('1')], _SUMMARY))
@patch("analytics.routes.db.get_pricing_map", return_value={})
@patch("analytics.routes.db.call_repair_assessment", return_value=[{'ESN': '1'}])
def test_telus_weekly_report_stashes_target_client_and_result(
        _call, _pmap, _compute, mock_stash):
    r = _client().post('/analytics/telus-weekly/report',
                       data={'project_tag': 'TW1626', 'client_name': 'Telus'})
    assert r.status_code == 200
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "telus_report"
    assert detail["target"] == "TW1626"
    assert detail["client"] == "Telus"
    assert detail["device_count"] == 5
    assert detail["total_lot_value"] == 1234.5


@patch("analytics.routes.admin_audit.stash")
@patch("analytics.routes.db.call_repair_assessment", side_effect=Exception("conn refused"))
def test_telus_weekly_report_db_error_stashes_result(_call, mock_stash):
    r = _client().post('/analytics/telus-weekly/report', data={'project_tag': 'TW1626'})
    assert r.status_code == 200   # error re-render, not an HTTP error
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "telus_report"
    assert detail["result"] == "db_error"
    assert "conn refused" in detail["error"]


@patch("analytics.routes.admin_audit.stash")
@patch("analytics.routes.db.call_repair_assessment", return_value=[])
def test_telus_weekly_report_no_devices_stashes_result(_call, mock_stash):
    r = _client().post('/analytics/telus-weekly/report', data={'project_tag': 'TW9999'})
    assert r.status_code == 200
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["result"] == "no_devices"


# ---------------------------------------------------------------------------
# telus_weekly_export
# ---------------------------------------------------------------------------

@patch("analytics.routes.admin_audit.stash")
@patch("analytics.routes.pricing.compute_report",
       return_value=([_enriched_row('1'), _enriched_row('2')], _SUMMARY))
@patch("analytics.routes.db.get_pricing_map", return_value={})
@patch("analytics.routes.db.call_repair_assessment", return_value=[{'ESN': '1'}, {'ESN': '2'}])
def test_telus_weekly_export_stashes_target_client_device_count_and_filename(
        _call, _pmap, _compute, mock_stash):
    r = _client().post('/analytics/telus-weekly/export',
                       data={'project_tag': 'TW1626', 'client_name': 'Telus'})
    assert r.status_code == 200
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "telus_export"
    assert detail["target"] == "TW1626"
    assert detail["client"] == "Telus"
    assert detail["device_count"] == 2
    assert detail["filename"].startswith("TW_TW1626_") and detail["filename"].endswith(".xlsx")


# ---------------------------------------------------------------------------
# price_review_save — old->new changes
# ---------------------------------------------------------------------------

@patch("analytics.routes.admin_audit.stash")
@patch("analytics.routes.db.bulk_update_pricing")
@patch("analytics.routes.db.get_all_pricing_models")
def test_price_review_save_stashes_old_new_changes(mock_all, mock_bulk, mock_stash):
    mock_all.return_value = [
        {'ID': 1, 'Model': 'iPhone 14', 'GradeA_Price': 300.0, 'GradeB_Price': 250.0,
         'GradeC_Price': 200.0, 'Defective_Price': 50.0, 'FRP_Price': 100.0,
         'DeviceType': 'Phone'},
    ]
    updates = [{'id': 1, 'grade_a': 320.0, 'grade_b': 250.0, 'grade_c': 200.0,
                'defective': 50.0, 'frp': 100.0, 'device_type': 'Phone'}]
    r = _client().post('/analytics/price-review/save', json={'updates': updates})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "price_update"
    assert detail["count"] == 1
    changes = detail["changes"]
    assert changes["iPhone 14"] == {"grade_a": {"old": 300.0, "new": 320.0}}


@patch("analytics.routes.admin_audit.stash")
@patch("analytics.routes.db.bulk_update_pricing")
@patch("analytics.routes.db.get_all_pricing_models", side_effect=Exception("db down"))
def test_price_review_save_falls_back_to_values_when_old_fetch_fails(
        mock_all, mock_bulk, mock_stash):
    updates = [{'id': 1, 'grade_a': 320.0, 'grade_b': 250.0, 'grade_c': 200.0,
                'defective': 50.0, 'frp': 100.0, 'device_type': 'Phone'}]
    r = _client().post('/analytics/price-review/save', json={'updates': updates})
    assert r.status_code == 200 and r.get_json()['ok'] is True   # save must not be blocked
    mock_bulk.assert_called_once()
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "price_update"
    assert detail["count"] == 1
    assert "values" in detail
    assert "changes" not in detail


# ---------------------------------------------------------------------------
# price_review_bulk_add
# ---------------------------------------------------------------------------

@patch("analytics.routes.admin_audit.stash")
@patch("analytics.routes.db.bulk_insert_pricing_models", return_value=[10, 11])
def test_price_review_bulk_add_stashes_count_and_model_names(mock_insert, mock_stash):
    models = [{'model': 'iPhone 15', 'grade_a': 400}, {'model': 'iPhone 16', 'grade_a': 500}]
    r = _client().post('/analytics/price-review/bulk-add', json={'models': models})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "price_bulk_add"
    assert detail["count"] == 2
    assert detail["models"] == ["iPhone 15", "iPhone 16"]


# ---------------------------------------------------------------------------
# price_review_add
# ---------------------------------------------------------------------------

@patch("analytics.routes.admin_audit.stash")
@patch("analytics.routes.db.insert_pricing_model", return_value=99)
def test_price_review_add_stashes_target_and_prices(mock_insert, mock_stash):
    body = {'model': 'Pixel 9', 'grade_a': 300, 'grade_b': 250, 'grade_c': 200,
            'defective': 40, 'frp': 80, 'device_type': 'Phone'}
    r = _client().post('/analytics/price-review/add', json=body)
    assert r.status_code == 200 and r.get_json()['ok'] is True
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "price_add"
    assert detail["target"] == "Pixel 9"
    assert detail["prices"] == {'grade_a': 300.0, 'grade_b': 250.0, 'grade_c': 200.0,
                                'defective': 40.0, 'frp': 80.0, 'device_type': 'Phone'}
