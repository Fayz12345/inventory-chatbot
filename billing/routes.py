from flask import Blueprint, request, jsonify, session, redirect, url_for

from billing import tms, templates

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')


def _require_login():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return None


@billing_bp.route('/tms')
def tms_page():
    redir = _require_login()
    if redir:
        return redir
    return templates.render_tms_billing_page()


@billing_bp.route('/tms/generate', methods=['POST'])
def tms_generate():
    if not session.get('logged_in'):
        return jsonify({'ok': False, 'error': 'Not logged in'}), 401
    data = request.get_json(silent=True) or {}
    try:
        year = int(data.get('year'))
        month = int(data.get('month'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'year and month are required integers'})
    if month < 1 or month > 12:
        return jsonify({'ok': False, 'error': 'month must be 1-12'})
    try:
        report = tms.generate_report(year, month)
        return jsonify({'ok': True, 'report': report})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
