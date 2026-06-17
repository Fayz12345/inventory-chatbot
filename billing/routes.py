import calendar

from flask import Blueprint, request, jsonify, session, redirect, url_for, Response

from billing import osl, templates, tms, export

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _raw_download(engine, prefix, sheet_title):
    redir = _require_login()
    if redir:
        return redir
    year, month, err = _parse_year_month(request.args)
    if err:
        return err, 400
    try:
        columns, rows = engine.get_raw_rows(year, month)
        data = export.rows_to_xlsx(columns, rows, sheet_title=sheet_title)
    except Exception as e:
        return f'Error generating raw data: {e}', 500
    label = f'{calendar.month_name[month]}_{year}'
    resp = Response(data, mimetype=XLSX_MIME)
    resp.headers['Content-Disposition'] = f'attachment; filename="{prefix}_{label}.xlsx"'
    return resp


def _require_login():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return None


def _parse_year_month(data):
    try:
        year = int(data.get('year'))
        month = int(data.get('month'))
    except (TypeError, ValueError):
        return None, None, 'year and month are required integers'
    if month < 1 or month > 12:
        return None, None, 'month must be 1-12'
    return year, month, None


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
    year, month, err = _parse_year_month(data)
    if err:
        return jsonify({'ok': False, 'error': err})
    try:
        report = tms.generate_report(year, month)
        return jsonify({'ok': True, 'report': report})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@billing_bp.route('/tms/raw')
def tms_raw():
    return _raw_download(tms, 'TMS_Raw', 'TMS Raw Data')


@billing_bp.route('/osl')
def osl_page():
    redir = _require_login()
    if redir:
        return redir
    return templates.render_osl_billing_page()


@billing_bp.route('/osl/generate', methods=['POST'])
def osl_generate():
    if not session.get('logged_in'):
        return jsonify({'ok': False, 'error': 'Not logged in'}), 401
    data = request.get_json(silent=True) or {}
    year, month, err = _parse_year_month(data)
    if err:
        return jsonify({'ok': False, 'error': err})
    # `models` (cached breakdown) + `overrides` are optional. When models is
    # provided the recompute is pure Python — no DB round-trip.
    overrides = data.get('overrides') or []
    models = data.get('models')
    try:
        result = osl.generate(year, month, overrides=overrides, models=models)
        return jsonify({
            'ok': True,
            'report': result['report'],
            'models': result['models'],
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@billing_bp.route('/osl/raw')
def osl_raw():
    return _raw_download(osl, 'OSL_Raw', 'OSL Raw Data')
