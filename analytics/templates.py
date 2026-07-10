import html as _html
import json as _json
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
# Telus Weekly — ProjectTag input form (custom combobox, no datalist)
# ---------------------------------------------------------------------------

def _telus_weekly_form_html(error, project_tag, client_name, project_tags, client_names):
    """Return the inner HTML for the Telus Weekly Generate Report form."""
    pt_json = _json.dumps(project_tags)
    cn_json = _json.dumps(client_names)
    error_block = ''
    if error:
        error_block = f'<div class="error">{_html.escape(error)}</div>'
    pt_val = _html.escape(project_tag or '')
    cn_val = _html.escape(client_name or '')
    return f"""
<style>
/* ── Telus Weekly combobox component ────────────────────────── */
.cb-wrap {{
  position: relative;
  display: flex;
  align-items: center;
}}
.cb-wrap input[type="text"] {{
  flex: 1;
  padding-right: 36px !important;
}}
.cb-chevron {{
  position: absolute;
  right: 0;
  top: 0;
  height: 100%;
  width: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
  color: #6b7280;
  flex-shrink: 0;
}}
.cb-chevron:hover {{ color: #2563eb; }}
.cb-chevron svg {{
  transition: transform 200ms ease;
  pointer-events: none;
}}
@media (prefers-reduced-motion: reduce) {{
  .cb-chevron svg {{ transition: none; }}
}}
.cb-chevron.open svg {{ transform: rotate(180deg); }}
.cb-panel {{
  display: none;
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 200;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(2,6,23,.12);
  max-height: 320px;
  overflow-y: auto;
  overflow-x: hidden;
}}
.cb-panel.open {{ display: block; }}
.cb-panel ul {{
  list-style: none;
  margin: 0;
  padding: 4px 0;
}}
.cb-panel ul li {{
  padding: 10px 14px;
  min-height: 40px;
  display: flex;
  align-items: center;
  cursor: pointer;
  font-size: 14px;
  color: #111827;
  line-height: 1.4;
  box-sizing: border-box;
}}
.cb-panel ul li:hover,
.cb-panel ul li.cb-hover {{
  background: #eff6ff;
}}
.cb-panel ul li.cb-active {{
  background: #dbeafe;
  border-left: 3px solid #2563eb;
  padding-left: 11px;
  color: #1e40af;
  font-weight: 500;
}}
.cb-panel ul li.cb-meta {{
  color: #9ca3af;
  font-size: 12px;
  cursor: default;
  justify-content: center;
  font-style: italic;
}}
.cb-panel ul li.cb-meta:hover,
.cb-panel ul li.cb-meta.cb-hover {{
  background: transparent;
}}
.cb-match {{ font-weight: 700; color: #2563eb; }}
</style>

<div class="container">
  <div class="form-card">
    <h2>Generate Report</h2>
    <p>Enter the ProjectTag to pull device data and calculate pricing recommendations.</p>

    {error_block}

    <form method="POST" action="/analytics/telus-weekly/report" id="report-form">
      <label for="project_tag">ProjectTag</label>
      <div class="cb-wrap" id="pt-wrap">
        <input type="text" id="project_tag" name="project_tag"
               placeholder="e.g. TW1626"
               value="{pt_val}"
               autocomplete="off"
               required
               role="combobox"
               aria-autocomplete="list"
               aria-expanded="false"
               aria-controls="pt-panel"
               aria-activedescendant="">
        <button type="button" class="cb-chevron" id="pt-chevron" aria-label="Show ProjectTag options" tabindex="-1">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <div class="cb-panel" id="pt-panel" role="listbox" aria-label="ProjectTag options">
          <ul id="pt-list"></ul>
        </div>
      </div>
      <div class="hint">Version = 000, ProjectName = Telus Weekly</div>

      <label for="client_name">Client Name (optional)</label>
      <div class="cb-wrap" id="cn-wrap">
        <input type="text" id="client_name" name="client_name"
               placeholder="e.g. Telus"
               value="{cn_val}"
               autocomplete="off"
               role="combobox"
               aria-autocomplete="list"
               aria-expanded="false"
               aria-controls="cn-panel"
               aria-activedescendant="">
        <button type="button" class="cb-chevron" id="cn-chevron" aria-label="Show Client Name options" tabindex="-1">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <div class="cb-panel" id="cn-panel" role="listbox" aria-label="Client Name options">
          <ul id="cn-list"></ul>
        </div>
      </div>

      <button type="submit" class="btn btn-primary btn-block" id="submit-btn">Generate Report</button>
    </form>
  </div>
</div>

<script>
(function () {{
  'use strict';

  var PROJECTTAG_OPTIONS = {pt_json};
  var CLIENTNAME_OPTIONS = {cn_json};

  var MAX = 50;

  function escapeHtml(s) {{
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }}

  // Highlight matched substring in label
  function highlight(label, q) {{
    if (!q) return escapeHtml(label);
    var idx = label.toLowerCase().indexOf(q.toLowerCase());
    if (idx === -1) return escapeHtml(label);
    return (
      escapeHtml(label.slice(0, idx)) +
      '<span class="cb-match">' + escapeHtml(label.slice(idx, idx + q.length)) + '</span>' +
      escapeHtml(label.slice(idx + q.length))
    );
  }}

  // Filter and rank: prefix matches first, then substring
  function filterOptions(options, q) {{
    if (!q) return options.slice(0, MAX);
    var ql = q.toLowerCase();
    var prefix = [], sub = [];
    for (var i = 0; i < options.length; i++) {{
      var ol = options[i].toLowerCase();
      if (ol.indexOf(ql) === 0) prefix.push(options[i]);
      else if (ol.indexOf(ql) !== -1) sub.push(options[i]);
    }}
    return prefix.concat(sub).slice(0, MAX);
  }}

  function initCombobox(inputEl, panelEl, chevronEl, listEl, options) {{
    var activeIdx = -1;
    var currentQuery = '';
    var isOpen = false;
    var closeTimer = null;
    var totalMatched = 0;

    function openPanel() {{
      isOpen = true;
      panelEl.classList.add('open');
      chevronEl.classList.add('open');
      inputEl.setAttribute('aria-expanded', 'true');
      renderList(inputEl.value);
    }}

    function closePanel() {{
      isOpen = false;
      panelEl.classList.remove('open');
      chevronEl.classList.remove('open');
      inputEl.setAttribute('aria-expanded', 'false');
      inputEl.setAttribute('aria-activedescendant', '');
      activeIdx = -1;
    }}

    function renderList(q) {{
      currentQuery = q;
      var ql = q.toLowerCase();
      var prefix = [], sub = [];
      for (var i = 0; i < options.length; i++) {{
        var ol = options[i].toLowerCase();
        if (ol.indexOf(ql) === 0) prefix.push(options[i]);
        else if (ol.indexOf(ql) !== -1) sub.push(options[i]);
      }}
      totalMatched = prefix.length + sub.length;
      var visible = prefix.concat(sub).slice(0, MAX);

      var html = '';
      if (visible.length === 0) {{
        html = '<li class="cb-meta" role="option" aria-disabled="true">No matches</li>';
      }} else {{
        var panelId = panelEl.id;
        for (var j = 0; j < visible.length; j++) {{
          var optId = panelId + '-opt-' + j;
          html += '<li id="' + optId + '" role="option" aria-selected="false" data-value="' + escapeHtml(visible[j]) + '">' +
                  highlight(visible[j], q) + '</li>';
        }}
        if (totalMatched > MAX) {{
          var more = totalMatched - MAX;
          html += '<li class="cb-meta" role="option" aria-disabled="true">…' + more + ' more — keep typing to narrow</li>';
        }}
      }}
      listEl.innerHTML = html;
      activeIdx = -1;

      // Mouse events on rendered items
      var items = listEl.querySelectorAll('li[data-value]');
      for (var k = 0; k < items.length; k++) {{
        (function(item) {{
          item.addEventListener('mouseover', function() {{
            setActive(Array.prototype.indexOf.call(listEl.querySelectorAll('li[data-value]'), item));
          }});
          item.addEventListener('mousedown', function(e) {{
            e.preventDefault(); // prevent blur before click
            selectValue(item.dataset.value);
          }});
        }})(items[k]);
      }}
    }}

    function setActive(idx) {{
      var items = listEl.querySelectorAll('li[data-value]');
      if (items.length === 0) {{ activeIdx = -1; return; }}
      // clamp
      if (idx < 0) idx = 0;
      if (idx >= items.length) idx = items.length - 1;
      // remove old
      for (var i = 0; i < items.length; i++) {{
        items[i].classList.remove('cb-active');
        items[i].setAttribute('aria-selected', 'false');
      }}
      activeIdx = idx;
      items[idx].classList.add('cb-active');
      items[idx].setAttribute('aria-selected', 'true');
      inputEl.setAttribute('aria-activedescendant', items[idx].id);
      // scroll into view
      items[idx].scrollIntoView({{ block: 'nearest' }});
    }}

    function selectValue(val) {{
      inputEl.value = val;
      closePanel();
      inputEl.focus();
    }}

    // Input events
    inputEl.addEventListener('focus', function() {{
      if (closeTimer) {{ clearTimeout(closeTimer); closeTimer = null; }}
      openPanel();
    }});

    inputEl.addEventListener('click', function() {{
      if (!isOpen) openPanel();
    }});

    inputEl.addEventListener('input', function() {{
      if (!isOpen) openPanel();
      renderList(inputEl.value);
    }});

    inputEl.addEventListener('blur', function() {{
      closeTimer = setTimeout(function() {{ closePanel(); }}, 150);
    }});

    inputEl.addEventListener('keydown', function(e) {{
      if (!isOpen) {{
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {{
          openPanel();
          e.preventDefault();
          return;
        }}
      }}
      if (e.key === 'ArrowDown') {{
        e.preventDefault();
        setActive(activeIdx + 1);
      }} else if (e.key === 'ArrowUp') {{
        e.preventDefault();
        setActive(activeIdx - 1);
      }} else if (e.key === 'Enter') {{
        var items = listEl.querySelectorAll('li[data-value]');
        if (isOpen && activeIdx >= 0 && activeIdx < items.length) {{
          e.preventDefault();
          selectValue(items[activeIdx].dataset.value);
        }}
        // else allow form submit
      }} else if (e.key === 'Escape') {{
        e.preventDefault();
        closePanel();
      }} else if (e.key === 'Tab') {{
        closePanel();
      }}
    }});

    // Chevron click
    chevronEl.addEventListener('click', function() {{
      if (isOpen) {{
        closePanel();
      }} else {{
        inputEl.focus();
        openPanel();
      }}
    }});

    // Close on outside click
    document.addEventListener('mousedown', function(e) {{
      if (!panelEl.parentElement.contains(e.target)) {{
        closePanel();
      }}
    }});
  }}

  // Init both fields
  initCombobox(
    document.getElementById('project_tag'),
    document.getElementById('pt-panel'),
    document.getElementById('pt-chevron'),
    document.getElementById('pt-list'),
    PROJECTTAG_OPTIONS
  );
  initCombobox(
    document.getElementById('client_name'),
    document.getElementById('cn-panel'),
    document.getElementById('cn-chevron'),
    document.getElementById('cn-list'),
    CLIENTNAME_OPTIONS
  );

  // Submit loading state
  document.getElementById('report-form').addEventListener('submit', function() {{
    var btn = document.getElementById('submit-btn');
    btn.disabled = true;
    btn.textContent = 'Generating...';
  }});
}})();
</script>
"""


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
        <form method="POST" action="/analytics/telus-weekly/export" style="margin:0;" data-no-loading>
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


def render_telus_weekly_form(error=None, project_tag=None, client_name=None,
                             project_tags=None, client_names=None):
    return page_shell(
        _telus_weekly_form_html(
            error=error,
            project_tag=project_tag,
            client_name=client_name,
            project_tags=project_tags or [],
            client_names=client_names or [],
        ),
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
