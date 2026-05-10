from flask import Blueprint, request, jsonify, session, redirect, url_for, Response
from analytics import db, pricing, templates
from io import BytesIO
from datetime import datetime

analytics_bp = Blueprint('analytics', __name__, url_prefix='/analytics')


def _require_login():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return None


@analytics_bp.route('/')
def index():
    redir = _require_login()
    if redir:
        return redir
    return templates.render_analytics_index()


@analytics_bp.route('/telus-weekly')
def telus_weekly_form():
    redir = _require_login()
    if redir:
        return redir
    return templates.render_telus_weekly_form()


@analytics_bp.route('/telus-weekly/report', methods=['POST'])
def telus_weekly_report():
    redir = _require_login()
    if redir:
        return redir

    project_tag = request.form.get('project_tag', '').strip()
    client_name = request.form.get('client_name', '').strip() or None

    if not project_tag:
        return templates.render_telus_weekly_form(error='ProjectTag is required.')

    try:
        devices = db.call_repair_assessment(project_tag, client_name)
    except Exception as e:
        return templates.render_telus_weekly_form(
            error=f'Database error: {e}',
            project_tag=project_tag,
            client_name=client_name,
        )

    if not devices:
        return templates.render_telus_weekly_form(
            error=f'No devices found for ProjectTag "{project_tag}".',
            project_tag=project_tag,
            client_name=client_name,
        )

    pricing_map = db.get_pricing_map()
    enriched, summary = pricing.compute_report(devices, pricing_map)

    return templates.render_telus_weekly_report(
        project_tag, client_name, enriched, summary,
    )


@analytics_bp.route('/telus-weekly/export', methods=['POST'])
def telus_weekly_export():
    redir = _require_login()
    if redir:
        return redir

    project_tag = request.form.get('project_tag', '').strip()
    client_name = request.form.get('client_name', '').strip() or None

    if not project_tag:
        return redirect(url_for('analytics.telus_weekly_form'))

    devices = db.call_repair_assessment(project_tag, client_name)
    pricing_map = db.get_pricing_map()
    enriched, summary = pricing.compute_report(devices, pricing_map)

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()

    # --- Repair & Resell sheet ---
    ws = wb.active
    ws.title = 'Repair & Resell'

    headers = [
        'ESN', 'Origin', 'Make', 'Model', 'Memory', 'Condition',
        'Fault 1', 'Fault 2', 'Fault 3', 'QC Notes',
        'Unassessed Price', 'Received Grade', 'Assessed Price',
        'Repair Labour', 'Repair Parts', 'Parts Used', 'Total Repair Cost',
        'Grade After Repair', 'Price After Repair', 'Upside',
        'Grade Improvement', 'Improvement Labour', 'Improvement Parts',
        'Total Improvement', 'Grade After Improvement',
        'Total Repair + Improvement', 'Price After Improvement',
        'Improvement Upside', 'Recommendation', 'Lot Value',
    ]

    header_font = Font(bold=True, color='FFFFFF', size=10)
    header_fill = PatternFill(start_color='2563EB', end_color='2563EB', fill_type='solid')

    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')

    def _val(v):
        if v is None:
            return 'N/A'
        return v

    for row_idx, row in enumerate(enriched, 2):
        vals = [
            row.get('ESN'),
            row.get('Vendor'),
            row.get('ManufacturerVerb'),
            row.get('ModelVerb'),
            row.get('Memory'),
            row.get('Conditions'),
            row.get('Defects_1'),
            row.get('Defects_2'),
            row.get('Defects_3'),
            row.get('QC_Notes'),
            row.get('unassessed_price'),
            row.get('Received_Grade'),
            row.get('assessed_price'),
            row.get('T_Level_Cost'),
            row.get('T_Part_Cost'),
            row.get('Parts_Used'),
            row.get('total_repair_cost'),
            row.get('Post-Repair_Grade'),
            row.get('price_after_repair'),
            row.get('upside'),
            row.get('Grade_Improvement'),
            row.get('T_Level_Improved_Cos'),
            row.get('T_Part_Improved_Cost'),
            row.get('total_improvement_cost'),
            row.get('Post_Improved_Grade'),
            row.get('total_repair_plus_improvement'),
            row.get('price_after_improvement'),
            row.get('improvement_upside'),
            row.get('recommendation'),
            row.get('lot_value'),
        ]
        for col_idx, v in enumerate(vals, 1):
            ws.cell(row=row_idx, column=col_idx, value=_val(v))

    # --- Models sheet ---
    ws_models = wb.create_sheet('Models')
    model_counts = {}
    for row in enriched:
        m = row.get('ModelVerb') or 'Unknown'
        model_counts[m] = model_counts.get(m, 0) + 1

    ws_models.cell(row=1, column=1, value='Model').font = Font(bold=True)
    ws_models.cell(row=1, column=2, value='Count').font = Font(bold=True)
    for i, (model, cnt) in enumerate(sorted(model_counts.items()), 2):
        ws_models.cell(row=i, column=1, value=model)
        ws_models.cell(row=i, column=2, value=cnt)

    # --- Summary sheet ---
    ws_summary = wb.create_sheet('Summary')
    ws_summary.cell(row=1, column=1, value='Total Devices').font = Font(bold=True)
    ws_summary.cell(row=1, column=2, value=summary['total_devices'])
    ws_summary.cell(row=2, column=1, value='Total Lot Value').font = Font(bold=True)
    ws_summary.cell(row=2, column=2, value=summary['total_lot_value'])
    r = 4
    ws_summary.cell(row=r, column=1, value='Recommendations').font = Font(bold=True)
    for rec, cnt in summary['recommendation_breakdown'].items():
        r += 1
        ws_summary.cell(row=r, column=1, value=rec)
        ws_summary.cell(row=r, column=2, value=cnt)
    r += 2
    ws_summary.cell(row=r, column=1, value='Conditions').font = Font(bold=True)
    for cond, cnt in summary['conditions_breakdown'].items():
        r += 1
        ws_summary.cell(row=r, column=1, value=cond)
        ws_summary.cell(row=r, column=2, value=cnt)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    today = datetime.now().strftime('%Y%m%d')
    filename = f'TW_{project_tag}_{today}.xlsx'

    return Response(
        buf.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


# ---------------------------------------------------------------------------
# Price Review
# ---------------------------------------------------------------------------

@analytics_bp.route('/price-review')
def price_review():
    redir = _require_login()
    if redir:
        return redir
    models = db.get_all_pricing_models()
    for m in models:
        for field in ('GradeA_Price', 'GradeB_Price', 'GradeC_Price',
                      'Defective_Price', 'FRP_Price'):
            if m.get(field) is not None:
                m[field] = float(m[field])
    return templates.render_price_review(models)


@analytics_bp.route('/price-review/save', methods=['POST'])
def price_review_save():
    if not session.get('logged_in'):
        return jsonify({'ok': False, 'error': 'Not logged in'}), 401

    data = request.get_json()
    updates = data.get('updates', [])
    if not updates:
        return jsonify({'ok': False, 'error': 'No updates provided'})

    try:
        db.bulk_update_pricing(updates, updated_by=session.get('username'))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@analytics_bp.route('/price-review/add', methods=['POST'])
def price_review_add():
    if not session.get('logged_in'):
        return jsonify({'ok': False, 'error': 'Not logged in'}), 401

    data = request.get_json()
    model = (data.get('model') or '').strip()
    if not model:
        return jsonify({'ok': False, 'error': 'Model name required'})

    try:
        new_id = db.insert_pricing_model(
            model,
            float(data.get('grade_a', 0)),
            float(data.get('grade_b', 0)),
            float(data.get('grade_c', 0)),
            float(data.get('defective', 0)),
            float(data.get('frp', 0)),
            data.get('device_type', 'Phone'),
        )
        return jsonify({'ok': True, 'id': new_id})
    except Exception as e:
        if 'UNIQUE' in str(e).upper() or 'duplicate' in str(e).lower():
            return jsonify({'ok': False, 'error': f'Model "{model}" already exists'})
        return jsonify({'ok': False, 'error': str(e)})
