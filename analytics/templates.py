from jinja2 import Template
from ui.shell import page_shell


# ---------------------------------------------------------------------------
# Analytics index — list of available reports
# ---------------------------------------------------------------------------
ANALYTICS_INDEX_TEMPLATE = Template("""
<div class="container">
    <div class="cards">
        <div class="section-label">Reports</div>
        <a href="/analytics/telus-weekly" class="card">
            <h3>Telus Weekly Report</h3>
            <p>Run the repair assessment report for a ProjectTag. Generates pricing, repair ROI, and sell recommendations.</p>
        </a>
        <a href="/analytics/price-review" class="card">
            <h3>Price Review</h3>
            <p>View and edit the pricing master table used for Telus Weekly report calculations.</p>
        </a>
        <div class="section-label">Monthly Billing</div>
        <a href="/billing/tms" class="card">
            <h3>TMS Billing</h3>
            <p>Generate the monthly TMS billing summary from inventory data.</p>
        </a>
        <a href="/billing/osl" class="card">
            <h3>OSL Billing</h3>
            <p>Monthly OSL billing summary by device category (Mobile Phones, Laptops, TVs, Tablets/Wearables/Buds, Accessories).</p>
        </a>
    </div>
</div>
""")


# ---------------------------------------------------------------------------
# Telus Weekly — ProjectTag input form
# ---------------------------------------------------------------------------
TELUS_WEEKLY_FORM_TEMPLATE = Template("""
<div class="container">
    <div class="form-card">
        <h2>Generate Report</h2>
        <p>Enter the ProjectTag to pull device data and calculate pricing recommendations.</p>

        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}

        <form method="POST" action="/analytics/telus-weekly/report" id="report-form">
            <label for="project_tag">ProjectTag</label>
            <input type="text" id="project_tag" name="project_tag" placeholder="e.g. TW1626"
                   value="{{ project_tag or '' }}" required>
            <div class="hint">Version = 000, ProjectName = Telus Weekly</div>

            <label for="client_name">Client Name (optional)</label>
            <input type="text" id="client_name" name="client_name" placeholder="e.g. Telus"
                   value="{{ client_name or '' }}">

            <button type="submit" class="btn btn-primary btn-block" id="submit-btn">Generate Report</button>
        </form>
    </div>
</div>
<script>
document.getElementById('report-form').addEventListener('submit', function() {
    var btn = document.getElementById('submit-btn');
    btn.disabled = true;
    btn.textContent = 'Generating...';
});
</script>
""")


# ---------------------------------------------------------------------------
# Telus Weekly — Full report with computed pricing
# ---------------------------------------------------------------------------
TELUS_WEEKLY_REPORT_TEMPLATE = Template("""
<div class="container">

    <div class="summary">
        <div class="summary-card">
            <div class="label">Total Devices</div>
            <div class="value">{{ summary.total_devices }}</div>
        </div>
        <div class="summary-card">
            <div class="label">Total Lot Value</div>
            <div class="value green">${{ "%.2f" | format(summary.total_lot_value) }}</div>
        </div>
        {% if summary.unpriced_models %}
        <div class="summary-card">
            <div class="label">Unpriced Models</div>
            <div class="value red">{{ summary.unpriced_models | length }}</div>
        </div>
        {% endif %}
        {% for rec_name, rec_count in summary.recommendation_breakdown.items() %}
        <div class="summary-card">
            <div class="label">{{ rec_name }}</div>
            <div class="value">{{ rec_count }}</div>
        </div>
        {% endfor %}
    </div>

    {% if summary.unpriced_models %}
    <div class="alert-banner">
        <div class="alert-title">{{ summary.unpriced_models | length }} model(s) not found in the pricing master</div>
        <div class="alert-models">
            {% for model, cnt in summary.unpriced_models.items() %}
            <span>{{ model }} ({{ cnt }})</span>
            {% endfor %}
        </div>
        <div style="margin-top: 10px; font-size: 13px;">
            These devices have $0 pricing. <a href="/analytics/price-review?project_tag={{ project_tag }}" target="_blank">Open Price Review for {{ project_tag }}</a> to add them, then re-run this report.
        </div>
    </div>
    {% endif %}

    <div class="breakdown">
        <span>Conditions:</span>
        {% for cond, cnt in summary.conditions_breakdown.items() %}
        <span><strong>{{ cnt }}</strong> {{ cond }}</span>
        {% endfor %}
    </div>

    <div class="actions" style="margin-top: 16px;">
        <form method="POST" action="/analytics/telus-weekly/export" style="margin:0;">
            <input type="hidden" name="project_tag" value="{{ project_tag }}">
            <input type="hidden" name="client_name" value="{{ client_name or '' }}">
            <button type="submit" class="btn btn-primary">Export to Excel</button>
        </form>
        <a href="/analytics/telus-weekly" class="btn btn-secondary">Run Another</a>
    </div>

    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>ESN</th>
                    <th>Origin</th>
                    <th>Make</th>
                    <th>Model</th>
                    <th>Memory</th>
                    <th>Condition</th>
                    <th>Fault 1</th>
                    <th>Fault 2</th>
                    <th>Fault 3</th>
                    <th>QC Notes</th>
                    <th>Unassessed Price</th>
                    <th>Received Grade</th>
                    <th>Assessed Price</th>
                    <th>Repair Labour</th>
                    <th>Repair Parts</th>
                    <th>Parts Used</th>
                    <th>Total Repair Cost</th>
                    <th>Grade After Repair</th>
                    <th>Price After Repair</th>
                    <th>Upside</th>
                    <th>Grade Improvement</th>
                    <th>Improvement Labour</th>
                    <th>Improvement Parts</th>
                    <th>Total Improvement</th>
                    <th>Grade After Improvement</th>
                    <th>Total Repair + Improvement</th>
                    <th>Price After Improvement</th>
                    <th>Improvement Upside</th>
                    <th>Recommendation</th>
                    <th>Lot Value</th>
                </tr>
            </thead>
            <tbody>
                {% for row in devices %}
                <tr>
                    <td>{{ row.ESN or '' }}</td>
                    <td>{{ row.Vendor or '' }}</td>
                    <td>{{ row.ManufacturerVerb or '' }}</td>
                    <td>{{ row.ModelVerb or '' }}
                        {% if row.pricing_error %}<br><span class="badge badge-error">{{ row.pricing_error }}</span>{% endif %}</td>
                    <td>{{ row.Memory or '' }}</td>
                    <td>{{ row.Conditions or '' }}</td>
                    <td>{{ row.Defects_1 or '' }}</td>
                    <td>{{ row.Defects_2 or '' }}</td>
                    <td>{{ row.Defects_3 or '' }}</td>
                    <td>{{ row.QC_Notes or '' }}</td>
                    <td class="price">{{ _fmt_price(row.unassessed_price) }}</td>
                    <td>{{ row.Received_Grade or '' }}</td>
                    <td class="price">{{ _fmt_price(row.assessed_price) }}</td>
                    <td>{{ _fmt_price(row.T_Level_Cost) }}</td>
                    <td>{{ _fmt_price(row.T_Part_Cost) }}</td>
                    <td>{{ row.Parts_Used or '' }}</td>
                    <td class="price">{{ _fmt_price(row.total_repair_cost) }}</td>
                    <td>{{ row['Post-Repair_Grade'] or '' }}</td>
                    <td class="price">{{ _fmt_price(row.price_after_repair) }}</td>
                    <td class="price {{ _upside_class(row.upside) }}">{{ _fmt_upside(row.upside) }}</td>
                    <td>{{ row.Grade_Improvement or '' }}</td>
                    <td>{{ _fmt_price(row.T_Level_Improved_Cos) }}</td>
                    <td>{{ _fmt_price(row.T_Part_Improved_Cost) }}</td>
                    <td class="price">{{ _fmt_price(row.total_improvement_cost) }}</td>
                    <td>{{ row.Post_Improved_Grade or '' }}</td>
                    <td class="price">{{ _fmt_price(row.total_repair_plus_improvement) }}</td>
                    <td class="price">{{ _fmt_price(row.price_after_improvement) }}</td>
                    <td class="price {{ _upside_class(row.improvement_upside) }}">{{ _fmt_upside(row.improvement_upside) }}</td>
                    <td><span class="badge {{ _rec_badge(row.recommendation) }}">{{ row.recommendation }}</span></td>
                    <td class="price positive">{{ _fmt_price(row.lot_value) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
""")


# ---------------------------------------------------------------------------
# Price Review — editable pricing master
# ---------------------------------------------------------------------------
PRICE_REVIEW_TEMPLATE = Template("""
<div class="container">
    <div style="margin-bottom: 16px;">
        <form method="GET" action="/analytics/price-review" style="display: flex; gap: 10px; align-items: center;">
            <input type="text" name="project_tag" class="search" placeholder="Enter ProjectTag to load its models..."
                   value="{{ project_tag or '' }}" style="width: 300px;">
            <button type="submit" class="btn btn-primary" style="padding: 10px 20px;">Load Project</button>
            {% if project_tag %}
            <a href="/analytics/price-review" class="btn btn-outline" style="padding: 10px 20px;">Show All Models</a>
            {% endif %}
        </form>
    </div>

    {% if error %}
    <div style="background: #fef2f2; color: #b91c1c; padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 14px; border: 1px solid #fecaca;">{{ error }}</div>
    {% endif %}

    {% if project_tag %}
    <div class="project-banner">
        <div style="font-weight: bold; color: #1d4ed8; font-size: 16px; margin-bottom: 4px;">
            ProjectTag: {{ project_tag }}
        </div>
        <div style="font-size: 14px; color: #555;">
            {{ total_project_devices }} device(s) across {{ total_project_models }} unique model(s)
            &mdash; {{ models | length }} already priced{% if new_models %},
            <span style="color: #dc2626; font-weight: bold;">{{ new_models | length }} need pricing</span>
            {% else %},
            <span style="color: #16a34a; font-weight: bold;">all models priced</span>
            {% endif %}
        </div>
    </div>
    {% endif %}

    <div class="toolbar">
        <input type="text" class="search" id="search" placeholder="Search models..." oninput="filterModels()">
        <span class="count" id="count">{{ models | length }}{% if new_models %} + {{ new_models | length }} new{% endif %} models</span>
        <div style="flex:1;"></div>
        {% if not project_tag %}
        <button class="btn btn-green" onclick="toggleAddRow()">+ Add Model</button>
        {% endif %}
        <button class="btn btn-primary" id="save-btn" onclick="saveAll()">Save Changes</button>
    </div>

    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Model</th>
                    <th>Grade A</th>
                    <th>Grade B</th>
                    <th>Grade C</th>
                    <th>Defective</th>
                    <th>FRP</th>
                    <th>Type</th>
                    <th></th>
                </tr>
            </thead>
            <tbody id="model-table">
                <tr id="add-row" class="add-row" style="display:none;">
                    <td><input type="text" id="new-model" placeholder="Model name"></td>
                    <td><input type="number" id="new-a" step="0.01" value="0"></td>
                    <td><input type="number" id="new-b" step="0.01" value="0"></td>
                    <td><input type="number" id="new-c" step="0.01" value="0"></td>
                    <td><input type="number" id="new-def" step="0.01" value="0"></td>
                    <td><input type="number" id="new-frp" step="0.01" value="0"></td>
                    <td>
                        <select id="new-type">
                            <option value="Phone">Phone</option>
                            <option value="Tablet">Tablet</option>
                            <option value="Watch">Watch</option>
                            <option value="Modem">Modem</option>
                        </select>
                    </td>
                    <td><button class="btn btn-green" onclick="addModel()" style="padding:6px 12px;font-size:12px;">Add</button></td>
                </tr>
                {% for m in models %}
                <tr class="model-row" data-id="{{ m.ID }}" data-model="{{ m.Model | lower }}">
                    <td class="model-name">{{ m.Model }}{% if project_tag %} <span class="device-count">({{ m.get('device_count', 0) }} device{{ 's' if m.get('device_count', 0) != 1 else '' }})</span>{% endif %}</td>
                    <td><input type="number" step="0.01" data-field="grade_a" value="{{ m.GradeA_Price }}" onchange="markChanged(this)"></td>
                    <td><input type="number" step="0.01" data-field="grade_b" value="{{ m.GradeB_Price }}" onchange="markChanged(this)"></td>
                    <td><input type="number" step="0.01" data-field="grade_c" value="{{ m.GradeC_Price }}" onchange="markChanged(this)"></td>
                    <td><input type="number" step="0.01" data-field="defective" value="{{ m.Defective_Price }}" onchange="markChanged(this)"></td>
                    <td><input type="number" step="0.01" data-field="frp" value="{{ m.FRP_Price }}" onchange="markChanged(this)"></td>
                    <td>
                        <select data-field="device_type" onchange="markChanged(this)">
                            <option value="Phone" {{ 'selected' if m.DeviceType == 'Phone' }}>Phone</option>
                            <option value="Tablet" {{ 'selected' if m.DeviceType == 'Tablet' }}>Tablet</option>
                            <option value="Watch" {{ 'selected' if m.DeviceType == 'Watch' }}>Watch</option>
                            <option value="Modem" {{ 'selected' if m.DeviceType == 'Modem' }}>Modem</option>
                        </select>
                    </td>
                    <td></td>
                </tr>
                {% endfor %}
                {% if new_models %}
                <tr class="section-divider">
                    <td colspan="8">New Models (not yet in pricing master) &mdash; set prices below, then click Save Changes</td>
                </tr>
                {% for nm in new_models %}
                <tr class="model-row new-model-row" data-new="true" data-model="{{ nm.Model | lower }}" data-name="{{ nm.Model }}">
                    <td class="model-name">
                        {{ nm.Model }}
                        <span class="new-badge">NEW</span>
                        <span class="device-count">({{ nm.count }} device{{ 's' if nm.count != 1 else '' }})</span>
                    </td>
                    <td><input type="number" step="0.01" data-field="grade_a" value="0"></td>
                    <td><input type="number" step="0.01" data-field="grade_b" value="0"></td>
                    <td><input type="number" step="0.01" data-field="grade_c" value="0"></td>
                    <td><input type="number" step="0.01" data-field="defective" value="0"></td>
                    <td><input type="number" step="0.01" data-field="frp" value="0"></td>
                    <td>
                        <select data-field="device_type">
                            <option value="Phone">Phone</option>
                            <option value="Tablet">Tablet</option>
                            <option value="Watch">Watch</option>
                            <option value="Modem">Modem</option>
                        </select>
                    </td>
                    <td></td>
                </tr>
                {% endfor %}
                {% endif %}
            </tbody>
        </table>
    </div>
</div>

<div id="toast" class="toast"></div>

<script>
var changedRows = new Set();

function markChanged(el) {
    el.classList.add('changed');
    var row = el.closest('tr');
    changedRows.add(row.dataset.id);
}

function filterModels() {
    var q = document.getElementById('search').value.toLowerCase();
    var rows = document.querySelectorAll('.model-row');
    var visible = 0;
    var newVisible = 0;
    rows.forEach(function(row) {
        var match = row.dataset.model.indexOf(q) !== -1;
        row.style.display = match ? '' : 'none';
        if (match) {
            visible++;
            if (row.dataset['new']) newVisible++;
        }
    });
    var divider = document.querySelector('.section-divider');
    if (divider) divider.style.display = newVisible > 0 ? '' : 'none';
    document.getElementById('count').textContent = visible + ' models';
}

function toggleAddRow() {
    var row = document.getElementById('add-row');
    row.style.display = row.style.display === 'none' ? '' : 'none';
    if (row.style.display !== 'none') document.getElementById('new-model').focus();
}

function addModel() {
    var model = document.getElementById('new-model').value.trim();
    if (!model) { showToast('Model name required', 'error'); return; }

    var body = {
        model: model,
        grade_a: parseFloat(document.getElementById('new-a').value) || 0,
        grade_b: parseFloat(document.getElementById('new-b').value) || 0,
        grade_c: parseFloat(document.getElementById('new-c').value) || 0,
        defective: parseFloat(document.getElementById('new-def').value) || 0,
        frp: parseFloat(document.getElementById('new-frp').value) || 0,
        device_type: document.getElementById('new-type').value
    };

    fetch('/analytics/price-review/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.ok) {
            showToast('Model added', 'success');
            setTimeout(function() { location.reload(); }, 800);
        } else {
            showToast(data.error || 'Failed to add', 'error');
        }
    })
    .catch(function() { showToast('Network error', 'error'); });
}

function saveAll() {
    var updates = [];
    var newModels = [];

    changedRows.forEach(function(id) {
        var row = document.querySelector('tr[data-id="' + id + '"]');
        if (!row) return;
        updates.push({
            id: parseInt(id),
            grade_a: parseFloat(row.querySelector('[data-field=grade_a]').value) || 0,
            grade_b: parseFloat(row.querySelector('[data-field=grade_b]').value) || 0,
            grade_c: parseFloat(row.querySelector('[data-field=grade_c]').value) || 0,
            defective: parseFloat(row.querySelector('[data-field=defective]').value) || 0,
            frp: parseFloat(row.querySelector('[data-field=frp]').value) || 0,
            device_type: row.querySelector('[data-field=device_type]').value
        });
    });

    document.querySelectorAll('.new-model-row').forEach(function(row) {
        newModels.push({
            model: row.dataset.name,
            grade_a: parseFloat(row.querySelector('[data-field=grade_a]').value) || 0,
            grade_b: parseFloat(row.querySelector('[data-field=grade_b]').value) || 0,
            grade_c: parseFloat(row.querySelector('[data-field=grade_c]').value) || 0,
            defective: parseFloat(row.querySelector('[data-field=defective]').value) || 0,
            frp: parseFloat(row.querySelector('[data-field=frp]').value) || 0,
            device_type: row.querySelector('[data-field=device_type]').value
        });
    });

    if (updates.length === 0 && newModels.length === 0) {
        showToast('No changes to save', 'error');
        return;
    }

    var btn = document.getElementById('save-btn');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    var promises = [];
    if (updates.length > 0) {
        promises.push(
            fetch('/analytics/price-review/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ updates: updates })
            }).then(function(r) { return r.json(); })
        );
    }
    if (newModels.length > 0) {
        promises.push(
            fetch('/analytics/price-review/bulk-add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ models: newModels })
            }).then(function(r) { return r.json(); })
        );
    }

    Promise.all(promises).then(function(results) {
        btn.disabled = false;
        btn.textContent = 'Save Changes';
        var allOk = results.every(function(r) { return r.ok; });
        if (allOk) {
            var parts = [];
            if (updates.length > 0) parts.push(updates.length + ' updated');
            if (newModels.length > 0) parts.push(newModels.length + ' added');
            showToast(parts.join(', '), 'success');
            if (newModels.length > 0) {
                setTimeout(function() { location.reload(); }, 1000);
            } else {
                changedRows.clear();
                document.querySelectorAll('.changed').forEach(function(el) { el.classList.remove('changed'); });
            }
        } else {
            var errs = results.filter(function(r) { return !r.ok; })
                              .map(function(r) { return r.error; }).join('; ');
            showToast(errs || 'Save failed', 'error');
        }
    }).catch(function() {
        btn.disabled = false;
        btn.textContent = 'Save Changes';
        showToast('Network error', 'error');
    });
}

function showToast(msg, type) {
    var t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast toast-' + type;
    t.style.display = 'block';
    setTimeout(function() { t.style.display = 'none'; }, 3000);
}
</script>
""")


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

def _fmt_price(val):
    if val is None:
        return 'N/A'
    try:
        v = float(val)
        return '${:.2f}'.format(v)
    except (ValueError, TypeError):
        return str(val)


def _fmt_upside(val):
    if val is None:
        return 'N/A'
    return '${:.2f}'.format(val)


def _upside_class(val):
    if val is None:
        return 'na'
    return 'positive' if val > 0 else 'negative'


def _rec_badge(rec):
    mapping = {
        'Sell After Repair': 'badge-repair',
        'Sell As Is': 'badge-asis',
        'Sell After Grade Improvement': 'badge-improvement',
        'Sell As Functional': 'badge-functional',
    }
    return mapping.get(rec, '')


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------

def render_analytics_index():
    return page_shell(ANALYTICS_INDEX_TEMPLATE.render(), title="Analytics", active="analytics")


def render_telus_weekly_form(error=None, project_tag=None, client_name=None):
    return page_shell(
        TELUS_WEEKLY_FORM_TEMPLATE.render(error=error, project_tag=project_tag, client_name=client_name),
        title="Telus Weekly Report", active="analytics", back=("/analytics/", "Analytics"),
    )


def render_telus_weekly_report(project_tag, client_name, devices, summary):
    return page_shell(
        TELUS_WEEKLY_REPORT_TEMPLATE.render(
            project_tag=project_tag,
            client_name=client_name,
            devices=devices,
            summary=summary,
            _fmt_price=_fmt_price,
            _fmt_upside=_fmt_upside,
            _upside_class=_upside_class,
            _rec_badge=_rec_badge,
        ),
        title="Telus Weekly: " + str(project_tag),
        active="analytics",
        back=("/analytics/", "Analytics"),
    )


def render_price_review(models, project_tag=None, new_models=None,
                        total_project_devices=0, total_project_models=0,
                        error=None):
    return page_shell(
        PRICE_REVIEW_TEMPLATE.render(
            models=models, project_tag=project_tag,
            new_models=new_models or [],
            total_project_devices=total_project_devices,
            total_project_models=total_project_models,
            error=error,
        ),
        title="Price Review",
        active="analytics",
        back=("/analytics/", "Analytics"),
    )
