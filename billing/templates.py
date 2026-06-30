"""HTML for the TMS and OSL billing pages.

Both pages share a single parameterized template. Schedule is embedded as
JSON so the browser can render rows (including manual inputs) and recompute
totals live. Generate fetches the parameterized endpoint.
"""
import json

from billing import osl_schedule, schedule
from ui.shell import page_shell


_BILLING_PAGE_TEMPLATE = """
  <div class="container">
    <div class="page-head"><h1>{title}</h1></div>
    <div class="controls">
      <div>
        <label>Month</label>
        <select id="month"></select>
      </div>
      <div>
        <label>Year</label>
        <select id="year"></select>
      </div>
      <button id="generate" class="btn btn-primary">Generate Billing Report</button>
      <button id="copy" class="secondary" disabled>Copy</button>
      <button id="csv" class="secondary" disabled>Download CSV</button>
      <button id="raw" class="secondary">Download Raw Data</button>
    </div>
    <div id="error" class="err"></div>
    <div id="result"></div>
    <div id="diagnostics"></div>
    <p class="hint">Manual line items are editable. The grand total updates as you type.
       Validate against the Excel report before invoicing.</p>
  </div>

<script>
const SCHEDULE = {schedule_json};
const ENDPOINT = "{endpoint}";
const RAW_ENDPOINT = "{raw_endpoint}";
const CSV_PREFIX = "{csv_prefix}";
const MONTHS = ["January","February","March","April","May","June","July","August",
                "September","October","November","December"];

function initControls() {{
  const now = new Date();
  // default to previous month
  let y = now.getFullYear(), m = now.getMonth(); // 0-based; getMonth()-1 -> prev
  m = m - 1; if (m < 0) {{ m = 11; y -= 1; }}
  const monthSel = document.getElementById('month');
  MONTHS.forEach((name, i) => {{
    const o = document.createElement('option'); o.value = i + 1; o.textContent = name;
    if (i === m) o.selected = true; monthSel.appendChild(o);
  }});
  const yearSel = document.getElementById('year');
  for (let yy = now.getFullYear(); yy >= now.getFullYear() - 5; yy--) {{
    const o = document.createElement('option'); o.value = yy; o.textContent = yy;
    if (yy === y) o.selected = true; yearSel.appendChild(o);
  }}
}}

function money(n) {{ return '$' + Number(n).toFixed(2); }}

let lastReport = null;

function recompute() {{
  if (!lastReport) return;
  let grand = 0;
  lastReport.sections.forEach(sec => {{
    let secTotal = 0;
    sec.line_items.forEach(li => {{
      let charge = li.charge;
      if (li.mode === 'manual') {{
        const u = document.getElementById('u_' + li._id);
        const f = document.getElementById('f_' + li._id);
        const units = u ? parseFloat(u.value || '0') : 0;
        const fee = f ? parseFloat(f.value || '0') : (li.fee || 0);
        charge = units * fee;
        const cell = document.getElementById('c_' + li._id);
        if (cell) cell.textContent = money(charge);
      }}
      secTotal += charge;
    }});
    const st = document.getElementById('st_' + sec._id);
    if (st) st.textContent = money(secTotal);
    grand += secTotal;
  }});
  document.getElementById('grand').textContent = money(grand);
}}

function renderReport(report) {{
  lastReport = report;
  let sid = 0, lid = 0;
  let html = '<h2>' + report.period_label + '</h2>';
  html += '<table><thead><tr><th>Section / Line Item</th><th class="num">Units</th>' +
          '<th class="num">Fee</th><th class="num">Charge</th></tr></thead><tbody>';
  report.sections.forEach(sec => {{
    sec._id = sid++;
    html += '<tr class="section"><td colspan="3">' + sec.name +
            '</td><td class="num" id="st_' + sec._id + '"></td></tr>';
    sec.line_items.forEach(li => {{
      li._id = lid++;
      let unitsCell, feeCell;
      if (li.mode === 'manual') {{
        unitsCell = '<input class="manual" type="number" min="0" step="1" value="0" ' +
                    'id="u_' + li._id + '">';
        const feeVal = (li.fee === null || li.fee === undefined) ? '' : li.fee;
        feeCell = '<input class="manual" type="number" min="0" step="0.01" value="' +
                  feeVal + '" id="f_' + li._id + '">';
      }} else if (li.mode === 'sum_repair_fee') {{
        unitsCell = '-';
        feeCell = 'SUM';
      }} else {{
        unitsCell = li.units;
        feeCell = money(li.fee);
      }}
      html += '<tr><td>&nbsp;&nbsp;' + li.label + '</td>' +
              '<td class="num">' + unitsCell + '</td>' +
              '<td class="num">' + feeCell + '</td>' +
              '<td class="num" id="c_' + li._id + '">' + money(li.charge) + '</td></tr>';
    }});
  }});
  html += '<tr class="grand"><td colspan="3">GRAND TOTAL</td>' +
          '<td class="num" id="grand"></td></tr>';
  html += '</tbody></table>';
  document.getElementById('result').innerHTML = html;

  // wire manual inputs
  report.sections.forEach(sec => sec.line_items.forEach(li => {{
    if (li.mode === 'manual') {{
      const u = document.getElementById('u_' + li._id);
      const f = document.getElementById('f_' + li._id);
      if (u) u.addEventListener('input', recompute);
      if (f) f.addEventListener('input', recompute);
    }}
  }}));
  recompute();
  renderDiagnostics(report);
  document.getElementById('copy').disabled = false;
  document.getElementById('csv').disabled = false;
}}

function renderDiagnostics(report) {{
  const slot = document.getElementById('diagnostics');
  if (!slot) return;
  const d = report.diagnostics || {{}};
  const n = Number(d.unmapped_in_month || 0);
  if (n > 0) {{
    slot.innerHTML = '<div class="diag"><b>' + n + ' device(s)</b> touched this month ' +
      "don't fall into any of the auto-categorized sections " +
      '(Mobile Phones, Laptops, TVs, Tablets/Wearables/Buds). ' +
      'Use the Accessories rows to bill them manually if applicable.</div>';
  }} else {{
    slot.innerHTML = '';
  }}
}}

function tableRows() {{
  // returns array of [section, label, units, fee, charge] for current report+inputs
  const rows = [];
  lastReport.sections.forEach(sec => {{
    sec.line_items.forEach(li => {{
      let units = li.units, fee = li.fee, charge = li.charge;
      if (li.mode === 'manual') {{
        const u = document.getElementById('u_' + li._id);
        const f = document.getElementById('f_' + li._id);
        units = u ? parseFloat(u.value || '0') : 0;
        fee = f ? parseFloat(f.value || '0') : (li.fee || 0);
        charge = units * fee;
      }}
      rows.push([sec.name, li.label,
                 units === null || units === undefined ? '' : units,
                 fee === null || fee === undefined ? '' : fee,
                 Number(charge).toFixed(2)]);
    }});
  }});
  return rows;
}}

document.addEventListener('DOMContentLoaded', () => {{
  initControls();
  document.getElementById('generate').addEventListener('click', async () => {{
    document.getElementById('error').textContent = '';
    const year = document.getElementById('year').value;
    const month = document.getElementById('month').value;
    const btn = document.getElementById('generate');
    const monthLabel = MONTHS[parseInt(month, 10) - 1] + ' ' + year;
    // show loading state
    btn.disabled = true;
    btn.textContent = 'Generating...';
    document.getElementById('copy').disabled = true;
    document.getElementById('csv').disabled = true;
    document.getElementById('result').innerHTML =
      '<div class="loader"><div class="spinner"></div> Generating billing report for ' +
      monthLabel + '...</div>';
    document.getElementById('diagnostics').innerHTML = '';
    try {{
      const resp = await fetch(ENDPOINT, {{
        method: 'POST', headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{year: year, month: month}})
      }});
      const data = await resp.json();
      if (!data.ok) {{
        document.getElementById('result').innerHTML = '';
        document.getElementById('error').textContent = data.error || 'Error';
        return;
      }}
      renderReport(data.report);
    }} catch (e) {{
      document.getElementById('result').innerHTML = '';
      document.getElementById('error').textContent = String(e);
    }} finally {{
      btn.disabled = false;
      btn.textContent = 'Generate Billing Report';
    }}
  }});
  document.getElementById('raw').addEventListener('click', () => {{
    const year = document.getElementById('year').value;
    const month = document.getElementById('month').value;
    window.location = RAW_ENDPOINT + '?year=' + year + '&month=' + month;
  }});

  document.getElementById('copy').addEventListener('click', () => {{
    const tsv = tableRows().map(r => r.join('\\t')).join('\\n');
    navigator.clipboard.writeText(tsv);
  }});
  document.getElementById('csv').addEventListener('click', () => {{
    const header = ['Section','Line Item','Units','Fee','Charge'];
    const csv = [header].concat(tableRows()).map(
      r => r.map(c => '"' + String(c).replace(/"/g, '""') + '"').join(',')
    ).join('\\n');
    const blob = new Blob([csv], {{type: 'text/csv'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = CSV_PREFIX + lastReport.period_label.replace(' ', '_') + '.csv';
    a.click();
  }});
}});
</script>"""


_OSL_BILLING_PAGE_TEMPLATE = """
  <div class="container">
    <div class="page-head"><h1>OSL Billing Report</h1></div>
    <div class="controls">
      <div>
        <label>Month</label>
        <select id="month"></select>
      </div>
      <div>
        <label>Year</label>
        <select id="year"></select>
      </div>
      <button id="generate" class="btn btn-primary">Generate</button>
      <button id="copy" class="secondary" disabled>Copy</button>
      <button id="csv" class="secondary" disabled>Download CSV</button>
      <button id="raw" class="secondary">Download Raw Data</button>
    </div>
    <div class="tab-nav">
      <button class="tab-btn active" data-tab="billing">Billing Report</button>
      <button class="tab-btn" data-tab="categories">Category Review</button>
    </div>
    <div id="error" class="err"></div>

    <div id="tab-billing" class="tab-panel active">
      <div id="result"></div>
      <div id="diagnostics"></div>
      <p class="hint">Manual line items are editable. The grand total updates as you type.
         Validate against the Excel report before invoicing.</p>
    </div>

    <div id="tab-categories" class="tab-panel">
      <div class="cat-toolbar">
        <button id="ai-btn" class="ai-btn" disabled
          title="Coming soon — will use Claude to suggest categories for unmapped models">
          AI Assign Categories
        </button>
        <span class="hint">Reassign a model's category in the <b>Assigned Category</b> column — the
          Billing Report recalculates automatically. Changes apply to this session only.
          AI auto-assignment coming soon.</span>
      </div>
      <div id="cat-result"></div>
    </div>
  </div>

<script>
const SECTION_CATEGORIES = {section_categories_json};
const MONTHS = ["January","February","March","April","May","June","July","August",
                "September","October","November","December"];

const CAT_TO_SECTION = {{}};
const CATEGORY_OPTIONS = [];
Object.entries(SECTION_CATEGORIES).forEach(([section, cats]) => {{
  cats.forEach(c => {{ CAT_TO_SECTION[c] = section; CATEGORY_OPTIONS.push(c); }});
}});

const OVR_SEP = "\\u241f";
function ovrKey(mfr, model) {{ return (mfr || '') + OVR_SEP + (model || ''); }}

// in-session state (not persisted)
let lastReport = null;
let lastModels = [];
let overrides = {{}};      // ovrKey -> category ('' = none / Accessories)
let manualState = {{}};    // "section||label" -> {{units, fee}}
let curYear = null, curMonth = null, curLabel = '';

function initControls() {{
  const now = new Date();
  let y = now.getFullYear(), m = now.getMonth();
  m = m - 1; if (m < 0) {{ m = 11; y -= 1; }}
  const monthSel = document.getElementById('month');
  MONTHS.forEach((name, i) => {{
    const o = document.createElement('option'); o.value = i + 1; o.textContent = name;
    if (i === m) o.selected = true; monthSel.appendChild(o);
  }});
  const yearSel = document.getElementById('year');
  for (let yy = now.getFullYear(); yy >= now.getFullYear() - 5; yy--) {{
    const o = document.createElement('option'); o.value = yy; o.textContent = yy;
    if (yy === y) o.selected = true; yearSel.appendChild(o);
  }}
}}

function money(n) {{ return '$' + Number(n).toFixed(2); }}
function esc(s) {{
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}
function manualKey(secName, label) {{ return secName + '||' + label; }}

function recompute() {{
  if (!lastReport) return;
  let grand = 0;
  lastReport.sections.forEach(sec => {{
    let secTotal = 0;
    sec.line_items.forEach(li => {{
      let charge = li.charge;
      if (li.mode === 'manual') {{
        const u = document.getElementById('u_' + li._id);
        const f = document.getElementById('f_' + li._id);
        const units = u ? parseFloat(u.value || '0') : 0;
        const fee = f ? parseFloat(f.value || '0') : (li.fee || 0);
        charge = units * fee;
        const cell = document.getElementById('c_' + li._id);
        if (cell) cell.textContent = money(charge);
        // persist manual inputs so they survive re-render on override changes
        manualState[manualKey(sec.name, li.label)] = {{units: units, fee: fee}};
      }}
      secTotal += charge;
    }});
    const st = document.getElementById('st_' + sec._id);
    if (st) st.textContent = money(secTotal);
    grand += secTotal;
  }});
  document.getElementById('grand').textContent = money(grand);
}}

function renderReport(report) {{
  lastReport = report;
  let sid = 0, lid = 0;
  let html = '<h2>' + report.period_label + '</h2>';
  html += '<table><thead><tr><th>Section / Line Item</th><th class="num">Units</th>' +
          '<th class="num">Fee</th><th class="num">Charge</th></tr></thead><tbody>';
  report.sections.forEach(sec => {{
    sec._id = sid++;
    html += '<tr class="section"><td colspan="3">' + sec.name +
            '</td><td class="num" id="st_' + sec._id + '"></td></tr>';
    sec.line_items.forEach(li => {{
      li._id = lid++;
      let unitsCell, feeCell;
      if (li.mode === 'manual') {{
        const saved = manualState[manualKey(sec.name, li.label)] || {{}};
        const uVal = (saved.units !== undefined) ? saved.units : 0;
        const feeDefault = (li.fee === null || li.fee === undefined) ? '' : li.fee;
        const fVal = (saved.fee !== undefined) ? saved.fee : feeDefault;
        unitsCell = '<input class="manual" type="number" min="0" step="1" value="' + uVal + '" id="u_' + li._id + '">';
        feeCell = '<input class="manual" type="number" min="0" step="0.01" value="' + fVal + '" id="f_' + li._id + '">';
      }} else {{
        unitsCell = li.units; feeCell = money(li.fee);
      }}
      html += '<tr><td>&nbsp;&nbsp;' + li.label + '</td>' +
              '<td class="num">' + unitsCell + '</td>' +
              '<td class="num">' + feeCell + '</td>' +
              '<td class="num" id="c_' + li._id + '">' + money(li.charge) + '</td></tr>';
    }});
  }});
  html += '<tr class="grand"><td colspan="3">GRAND TOTAL</td><td class="num" id="grand"></td></tr>';
  html += '</tbody></table>';
  document.getElementById('result').innerHTML = html;
  report.sections.forEach(sec => sec.line_items.forEach(li => {{
    if (li.mode === 'manual') {{
      const u = document.getElementById('u_' + li._id);
      const f = document.getElementById('f_' + li._id);
      if (u) u.addEventListener('input', recompute);
      if (f) f.addEventListener('input', recompute);
    }}
  }}));
  recompute();
  renderDiagnostics(report);
  document.getElementById('copy').disabled = false;
  document.getElementById('csv').disabled = false;
}}

function renderDiagnostics(report) {{
  const slot = document.getElementById('diagnostics');
  if (!slot) return;
  const n = Number((report.diagnostics || {{}}).unmapped_in_month || 0);
  slot.innerHTML = n > 0
    ? '<div class="diag"><b>' + n + ' device(s)</b> touched this month that fall outside ' +
      'every auto-categorized billing section. Reassign their category on the ' +
      '<b>Category Review</b> tab, or bill them manually via the Accessories rows.</div>'
    : '';
}}

// effective category = override if set, else the ERP/lookup value
function effectiveCategory(m) {{
  const k = ovrKey(m.manufacturer, m.model);
  return (k in overrides) ? overrides[k] : (m.category || '');
}}
function modelNeedsReview(m) {{
  const c = effectiveCategory(m);
  return !c || !CAT_TO_SECTION[c];
}}

function renderCategories(models) {{
  const slot = document.getElementById('cat-result');
  if (!models || !models.length) {{
    slot.innerHTML = '<p class="hint">No devices found for this period.</p>';
    document.getElementById('ai-btn').disabled = true;
    return;
  }}
  // needs-review rows first, then alphabetical
  const sorted = models.slice().sort((a, b) => {{
    const ar = modelNeedsReview(a) ? 0 : 1, br = modelNeedsReview(b) ? 0 : 1;
    if (ar !== br) return ar - br;
    const mfr = (a.manufacturer || '').localeCompare(b.manufacturer || '');
    return mfr !== 0 ? mfr : (a.model || '').localeCompare(b.model || '');
  }});
  const reviewCount = sorted.filter(modelNeedsReview).length;
  let html = '<h2>' + esc(curLabel) + ' — Model Categories</h2>';
  if (reviewCount > 0) {{
    html += '<div class="diag" style="margin-bottom:12px"><b>' + reviewCount +
            ' model(s) need review</b>, shown at top — no billable category assigned. ' +
            'Pick a category in the <b>Assigned Category</b> column and the Billing Report ' +
            'updates automatically. These are the models behind the unmapped-device count.</div>';
  }}
  html += '<table><thead><tr><th>Manufacturer</th><th>Model</th><th class="num">Units</th>' +
          '<th>ERP Category</th><th>Assigned Category</th><th>Billing Section</th></tr></thead><tbody>';
  sorted.forEach(m => {{
    const erp = m.category || '';
    const eff = effectiveCategory(m);
    const k = ovrKey(m.manufacturer, m.model);
    const overridden = (k in overrides) && (overrides[k] !== erp);
    let opts = '<option value="">(none / Accessories)</option>';
    CATEGORY_OPTIONS.forEach(c => {{
      opts += '<option value="' + esc(c) + '"' + (c === eff ? ' selected' : '') + '>' + esc(c) + '</option>';
    }});
    const sel = '<select class="cat-select" data-key="' + esc(k) + '">' + opts + '</select>';
    const erpCell = erp ? esc(erp) : '<span class="badge badge-amber">none</span>';
    const section = CAT_TO_SECTION[eff] || (eff ? 'Accessories (manual)' : '—');
    const rowStyle = modelNeedsReview(m) ? ' style="background:#fffbeb"' : '';
    const tag = overridden ? ' <span class="hint">(overridden)</span>' : '';
    html += '<tr' + rowStyle + '><td>' + esc(m.manufacturer) + '</td><td>' + esc(m.model) + '</td>' +
            '<td class="num">' + (m.touch || 0) + '</td>' +
            '<td>' + erpCell + tag + '</td>' +
            '<td>' + sel + '</td><td>' + esc(section) + '</td></tr>';
  }});
  html += '</tbody></table>';
  slot.innerHTML = html;
  slot.querySelectorAll('.cat-select').forEach(s => s.addEventListener('change', onCategoryChange));
  document.getElementById('ai-btn').disabled = true; // phase 2
}}

function overridesToList() {{
  return Object.keys(overrides).map(k => {{
    const i = k.indexOf(OVR_SEP);
    return {{manufacturer: k.slice(0, i), model: k.slice(i + 1), category: overrides[k]}};
  }});
}}

async function onCategoryChange(e) {{
  overrides[e.target.getAttribute('data-key')] = e.target.value;
  await recomputeFromServer();
}}

// Recompute the report from the cached breakdown + current overrides.
// Sends `models` back so the server skips the DB and only re-assembles.
async function recomputeFromServer() {{
  if (!curYear) return;
  document.getElementById('error').textContent = '';
  try {{
    const resp = await fetch('/billing/osl/generate', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{year: curYear, month: curMonth,
                            models: lastModels, overrides: overridesToList()}})
    }});
    const data = await resp.json();
    if (data.ok) {{
      renderReport(data.report);
      renderCategories(lastModels);
    }} else {{
      document.getElementById('error').textContent = data.error || 'Recompute failed';
    }}
  }} catch (e) {{
    document.getElementById('error').textContent = String(e);
  }}
}}

function tableRows() {{
  const rows = [];
  lastReport.sections.forEach(sec => {{
    sec.line_items.forEach(li => {{
      let units = li.units, fee = li.fee, charge = li.charge;
      if (li.mode === 'manual') {{
        const u = document.getElementById('u_' + li._id);
        const f = document.getElementById('f_' + li._id);
        units = u ? parseFloat(u.value || '0') : 0;
        fee = f ? parseFloat(f.value || '0') : (li.fee || 0);
        charge = units * fee;
      }}
      rows.push([sec.name, li.label,
                 units == null ? '' : units,
                 fee == null ? '' : fee,
                 Number(charge).toFixed(2)]);
    }});
  }});
  return rows;
}}

// tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  }});
}});

document.addEventListener('DOMContentLoaded', () => {{
  initControls();

  document.getElementById('generate').addEventListener('click', async () => {{
    document.getElementById('error').textContent = '';
    const year = document.getElementById('year').value;
    const month = document.getElementById('month').value;
    const btn = document.getElementById('generate');
    const monthLabel = MONTHS[parseInt(month, 10) - 1] + ' ' + year;
    // new period -> reset in-session overrides and manual inputs
    overrides = {{}}; manualState = {{}}; lastModels = [];
    curYear = year; curMonth = month; curLabel = monthLabel;
    btn.disabled = true; btn.textContent = 'Generating...';
    document.getElementById('copy').disabled = true;
    document.getElementById('csv').disabled = true;
    document.getElementById('result').innerHTML =
      '<div class="loader"><div class="spinner"></div>Generating billing report for ' + monthLabel + '...</div>';
    document.getElementById('diagnostics').innerHTML = '';
    document.getElementById('cat-result').innerHTML =
      '<div class="loader"><div class="spinner"></div>Loading model categories...</div>';

    try {{
      const resp = await fetch('/billing/osl/generate', {{
        method: 'POST', headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{year, month}})
      }});
      const data = await resp.json();
      if (!data.ok) {{
        document.getElementById('result').innerHTML = '';
        document.getElementById('cat-result').innerHTML = '';
        document.getElementById('error').textContent = data.error || 'Error generating report';
        return;
      }}
      lastModels = data.models || [];
      renderReport(data.report);
      renderCategories(lastModels);
    }} catch (e) {{
      document.getElementById('result').innerHTML = '';
      document.getElementById('cat-result').innerHTML = '';
      document.getElementById('error').textContent = String(e);
    }} finally {{
      btn.disabled = false; btn.textContent = 'Generate';
    }}
  }});

  document.getElementById('raw').addEventListener('click', () => {{
    const year = document.getElementById('year').value;
    const month = document.getElementById('month').value;
    window.location = '/billing/osl/raw?year=' + year + '&month=' + month;
  }});

  document.getElementById('copy').addEventListener('click', () => {{
    navigator.clipboard.writeText(tableRows().map(r => r.join('\\t')).join('\\n'));
  }});

  document.getElementById('csv').addEventListener('click', () => {{
    const header = ['Section','Line Item','Units','Fee','Charge'];
    const csv = [header].concat(tableRows()).map(
      r => r.map(c => '"' + String(c).replace(/"/g,'""') + '"').join(',')
    ).join('\\n');
    const blob = new Blob([csv], {{type:'text/csv'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'OSL_Billing_' + lastReport.period_label.replace(' ','_') + '.csv';
    a.click();
  }});
}});
</script>"""


def render_tms_billing_page():
    body = _BILLING_PAGE_TEMPLATE.format(
        title="TMS Billing Report",
        endpoint="/billing/tms/generate",
        raw_endpoint="/billing/tms/raw",
        csv_prefix="TMS_Billing_",
        schedule_json=json.dumps(schedule.TMS_FEE_SCHEDULE),
    )
    return page_shell(body, title="TMS Billing Report", active="analytics", back=("/analytics/", "Analytics"))


def render_osl_billing_page():
    body = _OSL_BILLING_PAGE_TEMPLATE.format(
        section_categories_json=json.dumps(osl_schedule.OSL_SECTION_CATEGORIES),
    )
    return page_shell(body, title="OSL Billing Report", active="analytics", back=("/analytics/", "Analytics"))
