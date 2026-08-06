"""Telus Weekly form fixes: comboboxes stay populated on an error re-render,
ProjectTag -> Client auto-fill endpoint, and the report's one-step-back link."""
import os
os.environ.setdefault("USERS_DB_PATH", "/tmp/test_users_chat.db")
os.environ.setdefault("CHAT_LOG_DB_PATH", "/tmp/test_chat_log.db")

from unittest.mock import patch
import app
from analytics import templates


def _client():
    c = app.chatbot_app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'tester'
        s['role'] = 'admin'
        s['is_admin'] = True
    return c


# --- Issue 1: error re-render must keep the combobox options ---------------

@patch("analytics.db.call_repair_assessment", return_value=[])
@patch("analytics.db.get_telus_client_names", return_value=['Telus', 'Bridge Wireless'])
@patch("analytics.db.get_telus_project_tags", return_value=['TW1626', 'TW1700'])
def test_report_error_rerender_keeps_combobox_options(_pt, _cn, _call):
    # "No devices found" re-renders the form — the comboboxes must still carry
    # their options (previously they came back empty and unusable).
    r = _client().post('/analytics/telus-weekly/report', data={'project_tag': 'X'})
    html = r.get_data(as_text=True)
    assert 'No devices found' in html
    assert 'TW1626' in html and 'TW1700' in html          # ProjectTag options present
    assert 'Bridge Wireless' in html                       # Client options present


@patch("analytics.db.get_telus_client_names", return_value=[])
@patch("analytics.db.get_telus_project_tags", return_value=['TW1626'])
def test_missing_projecttag_rerender_keeps_options(_pt, _cn):
    r = _client().post('/analytics/telus-weekly/report', data={'project_tag': ''})
    html = r.get_data(as_text=True)
    assert 'ProjectTag is required' in html and 'TW1626' in html


# --- Issue 2: ProjectTag -> Client name endpoint ---------------------------

@patch("analytics.db.get_client_for_project_tag", return_value=['Telus'])
def test_client_for_tag_single_client_autofills(_g):
    body = _client().get('/analytics/telus-weekly/client-for-tag?project_tag=TW1626').get_json()
    assert body['ok'] is True
    assert body['client'] == 'Telus' and body['clients'] == ['Telus']


@patch("analytics.db.get_client_for_project_tag", return_value=['Client A', 'Client B'])
def test_client_for_tag_ambiguous_returns_no_autofill(_g):
    # More than one client -> don't guess; client is null, field left for the user.
    body = _client().get('/analytics/telus-weekly/client-for-tag?project_tag=X').get_json()
    assert body['ok'] is True and body['client'] is None and body['clients'] == ['Client A', 'Client B']


def test_client_for_tag_requires_login():
    r = app.chatbot_app.test_client().get('/analytics/telus-weekly/client-for-tag?project_tag=X')
    assert r.status_code == 401


def test_form_wires_projecttag_autofill():
    html = templates.render_telus_weekly_form(project_tags=['TW1'], client_names=['Telus'])
    assert 'function fillClientForTag' in html
    assert '/analytics/telus-weekly/client-for-tag?project_tag=' in html


# --- Issue 3: report back link goes one step back to the form --------------

def test_report_back_link_points_to_telus_weekly_form():
    html = templates.render_telus_weekly_report(
        'TW1626', 'Telus', [],
        {'total_devices': 0, 'total_lot_value': 0,
         'recommendation_breakdown': {}, 'conditions_breakdown': {}})
    # The back control specifically points one step back to the Telus Weekly form
    # (the nav bar still links to /analytics/, which is fine).
    assert 'class="back" href="/analytics/telus-weekly"' in html
    assert '&larr; Telus Weekly' in html
