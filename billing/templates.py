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
    <div class="tab-nav">
      <button class="tab-btn active" data-tab="billing">Billing Report</button>
      <button class="tab-btn" data-tab="flat">Flat Table Data</button>
    </div>
    <div id="error" class="err"></div>

    <div id="tab-billing" class="tab-panel active">
      <div id="result"></div>
      <div id="diagnostics"></div>
      <p class="hint">Manual line items are editable. The grand total updates as you type.
         Validate against the Excel report before invoicing.</p>
    </div>

    <div id="tab-flat" class="tab-panel">
      <div id="flat-result">
        <p class="hint">Generate a billing report, then open this tab to see the underlying
           <b>dbo.ReportingInventoryFlat_TMS</b> device rows for that month.</p>
      </div>
    </div>
  </div>

<script>
const SCHEDULE = {schedule_json};
const ENDPOINT = "{endpoint}";
const RAW_ENDPOINT = "{raw_endpoint}";
const FLAT_ENDPOINT = "/billing/tms/flat";
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
let lastGenYear = null, lastGenMonth = null, lastGenLabel = null;
let flatLoadedFor = null;

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

function escFlat(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

async function loadFlat() {{
  const slot = document.getElementById('flat-result');
  if (!lastGenLabel) {{
    slot.innerHTML = '<p class="hint">Generate a billing report first — the flat-table ' +
      'data loads for the same month.</p>';
    return;
  }}
  if (flatLoadedFor === lastGenLabel) return;
  slot.innerHTML = '<div class="loader"><div class="spinner"></div> Loading flat-table data for ' +
    lastGenLabel + '...</div>';
  try {{
    const resp = await fetch(FLAT_ENDPOINT + '?year=' + lastGenYear + '&month=' + lastGenMonth);
    const data = await resp.json();
    if (!data.ok) {{ slot.innerHTML = '<div class="err">' + (data.error || 'Error') + '</div>'; return; }}
    renderFlat(data);
    flatLoadedFor = lastGenLabel;
  }} catch (e) {{
    slot.innerHTML = '<div class="err">' + String(e) + '</div>';
  }}
}}

function renderFlat(data) {{
  const slot = document.getElementById('flat-result');
  if (!data.rows || !data.rows.length) {{
    slot.innerHTML = '<p class="hint">No devices touched ' + lastGenLabel + '.</p>';
    return;
  }}
  let html = '<h2>' + lastGenLabel + ' &mdash; Flat Table (dbo.ReportingInventoryFlat_TMS)</h2>';
  html += '<p class="hint">' + data.total + ' device row(s)' +
          (data.truncated ? ' &mdash; showing the first ' + data.rows.length +
           '. Use <b>Download Raw Data</b> for the full set.' : '') + '</p>';
  html += '<div class="flat-scroll"><table class="flat-table"><thead><tr>';
  data.columns.forEach(c => {{ html += '<th>' + escFlat(c) + '</th>'; }});
  html += '</tr></thead><tbody>';
  data.rows.forEach(r => {{
    html += '<tr>';
    r.forEach(v => {{ html += '<td>' + escFlat(v === null || v === undefined ? '' : v) + '</td>'; }});
    html += '</tr>';
  }});
  html += '</tbody></table></div>';
  slot.innerHTML = html;
}}

document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'flat') loadFlat();
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
    lastGenYear = year; lastGenMonth = month; lastGenLabel = monthLabel;
    flatLoadedFor = null;
    document.getElementById('flat-result').innerHTML =
      '<p class="hint">Loading when you open this tab...</p>';
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
      if (document.querySelector('.tab-btn[data-tab="flat"]').classList.contains('active')) loadFlat();
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


def render_billing_home_page():
    # Plain string concat — no .format() so no brace-doubling needed in JS.
    body = (
        '<div class="container">'
        '<div class="page-head"><h1>Billing</h1></div>'

        # --- Selector-style switcher ---
        '<div class="bh-style-switcher" role="group" aria-label="Month selector style">'
        '<button class="bh-style-btn bh-active" data-style="stepper">Stepper</button>'
        '<button class="bh-style-btn" data-style="quickmonths">Quick Months</button>'
        '<button class="bh-style-btn" data-style="calendar">Calendar</button>'
        '</div>'

        # === Selector A: Stepper ===
        '<div class="bh-selector-wrap bh-visible" id="bh-sel-stepper">'
        '<div class="bha-toolbar">'
        '<div class="bha-stepper" id="bha-root" role="group" aria-label="Month selector">'
        '<button class="bha-stepper__btn" id="bha-prev" aria-label="Previous month" title="Previous month">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>'
        '</button>'
        '<button class="bha-label" id="bha-trigger" aria-haspopup="true" aria-expanded="false" aria-controls="bha-popover">'
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>'
        '<span id="bha-label-text"></span>'
        '<svg class="bha-chevron" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>'
        '</button>'
        '<button class="bha-stepper__btn" id="bha-next" aria-label="Next month" title="Next month">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"/></svg>'
        '</button>'
        '<div class="bha-popover" id="bha-popover" role="dialog" aria-label="Month picker" aria-hidden="true">'
        '<div class="bha-year-row">'
        '<button class="bha-year-btn" id="bha-year-prev" aria-label="Previous year" title="Previous year">'
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>'
        '</button>'
        '<span class="bha-year-display" id="bha-year-display" aria-live="polite"></span>'
        '<button class="bha-year-btn" id="bha-year-next" aria-label="Next year" title="Next year">'
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"/></svg>'
        '</button>'
        '</div>'
        '<div class="bha-month-grid" id="bha-month-grid" role="listbox" aria-label="Select month"></div>'
        '</div>'
        '</div>'
        '<button class="bha-this-month" id="bha-this-month" aria-label="Jump to current month">'
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.51"/></svg>'
        'This month'
        '</button>'
        '</div>'
        '</div>'

        # === Selector B: Quick Months ===
        '<div class="bh-selector-wrap" id="bh-sel-quickmonths">'
        '<div class="bhb-bar" role="group" aria-label="Select billing period">'
        '<span class="bhb-label">Period</span>'
        '<div class="bhb-chips" id="bhb-chips" role="radiogroup" aria-label="Quick month select"></div>'
        '<span class="bhb-divider" aria-hidden="true"></span>'
        '<div class="bhb-anchor" id="bhb-anchor">'
        '<button class="bhb-pick-btn" id="bhb-pick-btn" aria-haspopup="true" aria-expanded="false" aria-controls="bhb-popover" type="button">'
        'Pick month'
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>'
        '</button>'
        '<div class="bhb-popover" id="bhb-popover" role="dialog" aria-label="Month picker" aria-modal="false">'
        '<div class="bhb-year-row">'
        '<button class="bhb-year-btn" id="bhb-year-prev" aria-label="Previous year" type="button">'
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>'
        '</button>'
        '<span class="bhb-year-label" id="bhb-year-label"></span>'
        '<button class="bhb-year-btn" id="bhb-year-next" aria-label="Next year" type="button">'
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"/></svg>'
        '</button>'
        '</div>'
        '<div class="bhb-month-grid" id="bhb-month-grid" role="listbox" aria-label="Select month"></div>'
        '</div>'
        '</div>'
        '</div>'
        '</div>'

        # === Selector C: Calendar ===
        '<div class="bh-selector-wrap" id="bh-sel-calendar">'
        '<div class="bhc-wrap" id="bhc-wrap">'
        '<button class="bhc-trigger" id="bhc-trigger" aria-haspopup="true" aria-expanded="false" aria-controls="bhc-popover" title="Select billing period">'
        '<svg class="bhc-trigger__icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>'
        '<span id="bhc-trigger-label"></span>'
        '<svg class="bhc-trigger__chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>'
        '</button>'
        '<div class="bhc-popover" id="bhc-popover" role="dialog" aria-modal="false" aria-label="Select billing period">'
        '<div class="bhc-year-nav">'
        '<button class="bhc-year-nav__btn" id="bhc-prev-year" aria-label="Previous year">'
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>'
        '</button>'
        '<div style="text-align:center"><div class="bhc-year-nav__year" id="bhc-year-display"></div></div>'
        '<button class="bhc-year-nav__btn" id="bhc-next-year" aria-label="Next year">'
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"/></svg>'
        '</button>'
        '</div>'
        '<div class="bhc-month-grid" id="bhc-month-grid" role="group" aria-label="Select month"></div>'
        '<div class="bhc-preset-row">'
        '<button class="bhc-preset-btn" id="bhc-this-month">This month</button>'
        '<button class="bhc-preset-btn" id="bhc-last-month">Last month</button>'
        '</div>'
        '</div>'
        '</div>'
        '</div>'

        # --- Period label + checkboxes ---
        '<div class="bh-period-row">'
        '<div class="bh-period-label">Showing: <span id="bh-period-text"></span></div>'
        '<div class="bh-checks">'
        '<label><input type="checkbox" id="bh-chk-tms" checked> TMS</label>'
        '<label><input type="checkbox" id="bh-chk-osl" checked> OSL</label>'
        '</div>'
        '</div>'

        # --- Report slots ---
        '<div id="tms-report" class="bh-report-slot"></div>'
        '<div id="osl-report" class="bh-report-slot"></div>'
        '</div>'
    )

    # JS block — plain string, no format(), no brace issues
    js = r"""
<script>
(function () {
  'use strict';

  /* ---- Shared constants ---- */
  var MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  var MONTHS_LONG  = ['January','February','March','April','May','June',
                      'July','August','September','October','November','December'];

  var _today = new Date();
  var CURRENT_YEAR  = _today.getFullYear();
  var CURRENT_MONTH = _today.getMonth(); // 0-based

  /* ---- HTML escape helper ---- */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;');
  }

  /* ---- money helper ---- */
  function money(n) { return '$' + Number(n).toFixed(2); }

  /* ---- Period label ---- */
  function fmtPeriod(year, month1) {
    return MONTHS_LONG[month1 - 1] + ' ' + year;
  }

  /* ======================================================
     BillingPage controller
     ====================================================== */
  window.BillingPage = {
    year:  CURRENT_YEAR,
    month: CURRENT_MONTH + 1, // 1-based

    setPeriod: function(y, m) {
      this.year  = y;
      this.month = m;
      updatePeriodLabel();
      this.refresh();
    },

    refresh: function() {
      var tmsChk = document.getElementById('bh-chk-tms');
      var oslChk = document.getElementById('bh-chk-osl');
      var tmsSlot = document.getElementById('tms-report');
      var oslSlot = document.getElementById('osl-report');
      if (tmsChk && tmsChk.checked) {
        loadReport('tms', tmsSlot, BillingPage.year, BillingPage.month);
      } else if (tmsSlot) {
        tmsSlot.innerHTML = '';
        tmsSlot.style.display = 'none';
      }
      if (oslChk && oslChk.checked) {
        loadReport('osl', oslSlot, BillingPage.year, BillingPage.month);
      } else if (oslSlot) {
        oslSlot.innerHTML = '';
        oslSlot.style.display = 'none';
      }
    }
  };

  function updatePeriodLabel() {
    var el = document.getElementById('bh-period-text');
    if (el) el.textContent = fmtPeriod(BillingPage.year, BillingPage.month);
  }

  /* ======================================================
     loadReport / renderReport
     ====================================================== */
  function loadReport(kind, slot, year, month) {
    if (!slot) return;
    slot.style.display = '';
    slot.innerHTML = '<div class="bh-slot-loader"><div class="spinner" aria-hidden="true"></div><span>Loading ' + fmtPeriod(year, month) + '...</span></div>';
    var endpoint = kind === 'tms' ? '/billing/tms/generate' : '/billing/osl/generate';
    fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({year: year, month: month})
    }).then(function(r) { return r.json(); }).then(function(data) {
      if (!data.ok) {
        slot.innerHTML = '<div class="bh-slot-error">' + esc(data.error || 'Error generating report') + '</div>';
        return;
      }
      renderReport(slot, data.report, kind);
    }).catch(function(e) {
      slot.innerHTML = '<div class="bh-slot-error">' + esc(String(e)) + '</div>';
    });
  }

  function renderReport(slot, report, kind) {
    var kindLabel = kind === 'tms' ? 'TMS' : 'OSL';
    var fullLink  = kind === 'tms' ? '/billing/tms' : '/billing/osl';
    var linkLabel = 'Open full ' + kindLabel + ' report →';

    var html = '<h3>' + esc(report.period_label) + ' — ' + kindLabel + ' Billing</h3>';
    html += '<div class="table-wrap"><table>';
    html += '<thead><tr>'
          + '<th>Section / Line Item</th>'
          + '<th class="num">Units</th>'
          + '<th class="num">Fee</th>'
          + '<th class="num">Charge</th>'
          + '</tr></thead><tbody>';

    (report.sections || []).forEach(function(sec) {
      html += '<tr class="bh-section-row"><td colspan="3">' + esc(sec.name) + '</td>'
            + '<td class="num">' + money(sec.section_total) + '</td></tr>';
      (sec.line_items || []).forEach(function(li) {
        var units, fee;
        if (li.mode === 'sum_repair_fee') {
          units = '-'; fee = 'SUM';
        } else if (li.mode === 'manual') {
          units = '—';
          fee = (li.fee == null) ? '—' : money(li.fee);
        } else {
          units = (li.units == null ? '' : li.units);
          fee   = money(li.fee);
        }
        html += '<tr><td>&nbsp;&nbsp;' + esc(li.label) + '</td>'
              + '<td class="num">' + esc(String(units)) + '</td>'
              + '<td class="num">' + esc(String(fee))   + '</td>'
              + '<td class="num">' + money(li.charge)   + '</td></tr>';
      });
    });

    html += '<tr class="bh-total-row">'
          + '<td colspan="3">Auto total (excl. manual items)</td>'
          + '<td class="num">' + money(report.grand_total_auto) + '</td></tr>';
    html += '</tbody></table></div>';
    html += '<p class="bh-note">Manual line items (Accessories, Kitting, …) are entered on the full report. '
          + '<a href="' + esc(fullLink) + '">' + esc(linkLabel) + '</a></p>';
    slot.innerHTML = html;
  }

  /* ======================================================
     Selector-style switcher
     ====================================================== */
  var styleBtns = document.querySelectorAll('.bh-style-btn');
  var styleWraps = document.querySelectorAll('.bh-selector-wrap');

  styleBtns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      styleBtns.forEach(function(b) { b.classList.remove('bh-active'); });
      styleWraps.forEach(function(w) { w.classList.remove('bh-visible'); });
      btn.classList.add('bh-active');
      var wrap = document.getElementById('bh-sel-' + btn.dataset.style);
      if (wrap) wrap.classList.add('bh-visible');
    });
  });

  /* ======================================================
     Checkbox toggle
     ====================================================== */
  ['bh-chk-tms','bh-chk-osl'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('change', function() { BillingPage.refresh(); });
  });

  /* ======================================================
     SELECTOR A — Stepper
     ====================================================== */
  (function() {
    var selA = { month: CURRENT_MONTH, year: CURRENT_YEAR };
    var browseYearA = CURRENT_YEAR;
    var popOpenA = false;

    var rootA     = document.getElementById('bha-root');
    var triggerA  = document.getElementById('bha-trigger');
    var labelA    = document.getElementById('bha-label-text');
    var prevA     = document.getElementById('bha-prev');
    var nextA     = document.getElementById('bha-next');
    var popoverA  = document.getElementById('bha-popover');
    var yearDispA = document.getElementById('bha-year-display');
    var yrPrevA   = document.getElementById('bha-year-prev');
    var yrNextA   = document.getElementById('bha-year-next');
    var gridA     = document.getElementById('bha-month-grid');
    var thisMonA  = document.getElementById('bha-this-month');

    function fmtA(m, y) { return MONTHS_LONG[m] + ' ' + y; }

    function updateLabelA() {
      if (labelA) labelA.textContent = fmtA(selA.month, selA.year);
    }

    function updateThisMonA() {
      if (!thisMonA) return;
      if (selA.month === CURRENT_MONTH && selA.year === CURRENT_YEAR) {
        thisMonA.classList.add('bha-is-current');
      } else {
        thisMonA.classList.remove('bha-is-current');
      }
    }

    function renderGridA() {
      if (!gridA || !yearDispA) return;
      yearDispA.textContent = browseYearA;
      gridA.innerHTML = '';
      MONTHS_SHORT.forEach(function(abbr, idx) {
        var btn = document.createElement('button');
        btn.className = 'bha-month-btn';
        btn.type = 'button';
        btn.textContent = abbr;
        btn.setAttribute('role', 'option');
        if (idx === selA.month && browseYearA === selA.year) {
          btn.classList.add('bha-selected');
          btn.setAttribute('aria-selected', 'true');
        } else {
          btn.setAttribute('aria-selected', 'false');
        }
        if (idx === CURRENT_MONTH && browseYearA === CURRENT_YEAR) {
          btn.classList.add('bha-today');
          btn.setAttribute('aria-label', abbr + ' (current month)');
        }
        btn.addEventListener('click', function() { selectMonthA(idx, browseYearA); });
        btn.addEventListener('keydown', function(e) {
          var ni = idx;
          if (e.key==='ArrowRight') ni=(idx+1)%12;
          else if (e.key==='ArrowLeft') ni=(idx+11)%12;
          else if (e.key==='ArrowDown') ni=Math.min(idx+3,11);
          else if (e.key==='ArrowUp')   ni=Math.max(idx-3,0);
          else return;
          e.preventDefault();
          var btns = gridA.querySelectorAll('.bha-month-btn');
          if (btns[ni]) btns[ni].focus();
        });
        gridA.appendChild(btn);
      });
    }

    function openPopA() {
      browseYearA = selA.year;
      renderGridA();
      if (popoverA) { popoverA.classList.add('bha-open'); popoverA.setAttribute('aria-hidden','false'); }
      if (triggerA) triggerA.setAttribute('aria-expanded','true');
      popOpenA = true;
      requestAnimationFrame(function() {
        var s = gridA && gridA.querySelector('.bha-selected, .bha-month-btn');
        if (s) s.focus();
      });
    }

    function closePopA() {
      if (popoverA) { popoverA.classList.remove('bha-open'); popoverA.setAttribute('aria-hidden','true'); }
      if (triggerA) triggerA.setAttribute('aria-expanded','false');
      popOpenA = false;
    }

    function selectMonthA(m, y) {
      selA = {month: m, year: y};
      closePopA();
      updateLabelA();
      updateThisMonA();
      // Only call BillingPage if this selector is visible
      var wrap = document.getElementById('bh-sel-stepper');
      if (wrap && wrap.classList.contains('bh-visible')) {
        BillingPage.setPeriod(y, m + 1);
      }
    }

    if (triggerA) triggerA.addEventListener('click', function(e) {
      e.stopPropagation(); if (popOpenA) closePopA(); else openPopA();
    });
    if (prevA) prevA.addEventListener('click', function() {
      var m = selA.month - 1, y = selA.year;
      if (m < 0) { m = 11; y--; } selectMonthA(m, y);
    });
    if (nextA) nextA.addEventListener('click', function() {
      var m = selA.month + 1, y = selA.year;
      if (m > 11) { m = 0; y++; } selectMonthA(m, y);
    });
    if (thisMonA) thisMonA.addEventListener('click', function() {
      if (!thisMonA.classList.contains('bha-is-current')) selectMonthA(CURRENT_MONTH, CURRENT_YEAR);
    });
    if (yrPrevA) yrPrevA.addEventListener('click', function(e) { e.stopPropagation(); browseYearA--; renderGridA(); });
    if (yrNextA) yrNextA.addEventListener('click', function(e) { e.stopPropagation(); browseYearA++; renderGridA(); });
    if (popoverA) popoverA.addEventListener('click', function(e) { e.stopPropagation(); });

    document.addEventListener('click', function(e) {
      if (popOpenA && rootA && !rootA.contains(e.target)) closePopA();
    });
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && popOpenA) { closePopA(); if (triggerA) triggerA.focus(); }
    });

    // Init
    updateLabelA();
    updateThisMonA();
  })();

  /* ======================================================
     SELECTOR B — Quick Months
     ====================================================== */
  (function() {
    var selB = { month: CURRENT_MONTH, year: CURRENT_YEAR };
    var pickerYearB = CURRENT_YEAR;
    var popOpenB = false;

    var chipsEl  = document.getElementById('bhb-chips');
    var pickBtn  = document.getElementById('bhb-pick-btn');
    var popoverB = document.getElementById('bhb-popover');
    var yrLabel  = document.getElementById('bhb-year-label');
    var yrPrevB  = document.getElementById('bhb-year-prev');
    var yrNextB  = document.getElementById('bhb-year-next');
    var gridB    = document.getElementById('bhb-month-grid');
    var anchorB  = document.getElementById('bhb-anchor');

    function chipWindow() {
      var chips = [];
      for (var i = 5; i >= 0; i--) {
        var m = CURRENT_MONTH - i, y = CURRENT_YEAR;
        if (m < 0) { m += 12; y -= 1; }
        chips.push({year: y, month: m});
      }
      return chips;
    }

    function renderChipsB() {
      if (!chipsEl) return;
      chipsEl.innerHTML = '';
      var win = chipWindow();
      win.forEach(function(item, idx) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'bhb-chip';
        btn.setAttribute('role', 'radio');
        var showYear = idx === 0 || item.year !== win[idx-1].year;
        if (showYear) {
          btn.textContent = MONTHS_SHORT[item.month] + " '" + String(item.year).slice(2);
          btn.classList.add('bhb-year-shown');
        } else {
          btn.textContent = MONTHS_SHORT[item.month];
        }
        if (selB.year === item.year && selB.month === item.month) {
          btn.classList.add('bhb-active');
          btn.setAttribute('aria-checked', 'true');
        } else {
          btn.setAttribute('aria-checked', 'false');
        }
        btn.addEventListener('click', function() { selectMonthB(item.year, item.month); });
        chipsEl.appendChild(btn);
      });
    }

    function renderPopoverB() {
      if (!yrLabel || !gridB) return;
      yrLabel.textContent = pickerYearB;
      if (yrPrevB) yrPrevB.disabled = pickerYearB <= 2020;
      if (yrNextB) yrNextB.disabled = pickerYearB >= CURRENT_YEAR;
      gridB.innerHTML = '';
      MONTHS_SHORT.forEach(function(abbr, m) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'bhb-month-cell';
        btn.setAttribute('role', 'option');
        btn.textContent = abbr;
        var isActive  = selB.year === pickerYearB && selB.month === m;
        var isFuture  = pickerYearB === CURRENT_YEAR && m > CURRENT_MONTH;
        if (isActive)  { btn.classList.add('bhb-selected'); btn.setAttribute('aria-selected','true'); }
        if (isFuture)  { btn.classList.add('bhb-future'); btn.setAttribute('aria-disabled','true'); }
        if (!isFuture) {
          btn.addEventListener('click', function() { selectMonthB(pickerYearB, m); closePopB(); });
        }
        gridB.appendChild(btn);
      });
    }

    function openPopB() {
      pickerYearB = selB.year;
      renderPopoverB();
      if (popoverB) popoverB.classList.add('bhb-open');
      if (pickBtn)  pickBtn.setAttribute('aria-expanded','true');
      popOpenB = true;
      var first = gridB && gridB.querySelector('.bhb-month-cell:not(.bhb-future)');
      if (first) first.focus();
    }

    function closePopB() {
      if (popoverB) popoverB.classList.remove('bhb-open');
      if (pickBtn)  pickBtn.setAttribute('aria-expanded','false');
      popOpenB = false;
    }

    function selectMonthB(y, m) {
      selB = {year: y, month: m};
      renderChipsB();
      renderPopoverB();
      var wrap = document.getElementById('bh-sel-quickmonths');
      if (wrap && wrap.classList.contains('bh-visible')) {
        BillingPage.setPeriod(y, m + 1);
      }
    }

    if (pickBtn) pickBtn.addEventListener('click', function(e) {
      e.stopPropagation(); if (popOpenB) closePopB(); else openPopB();
    });
    if (yrPrevB) yrPrevB.addEventListener('click', function(e) {
      e.stopPropagation();
      pickerYearB = Math.max(2020, pickerYearB - 1); renderPopoverB();
    });
    if (yrNextB) yrNextB.addEventListener('click', function(e) {
      e.stopPropagation();
      pickerYearB = Math.min(CURRENT_YEAR, pickerYearB + 1); renderPopoverB();
    });
    if (popoverB) popoverB.addEventListener('click', function(e) { e.stopPropagation(); });

    document.addEventListener('click', function(e) {
      if (popOpenB && anchorB && !anchorB.contains(e.target)) closePopB();
    });
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && popOpenB) { closePopB(); if (pickBtn) pickBtn.focus(); }
    });

    // Init
    renderChipsB();
  })();

  /* ======================================================
     SELECTOR C — Calendar
     ====================================================== */
  (function() {
    var selC = { month: CURRENT_MONTH, year: CURRENT_YEAR };
    var browseYearC = CURRENT_YEAR;
    var popOpenC = false;

    var wrapC    = document.getElementById('bhc-wrap');
    var triggerC = document.getElementById('bhc-trigger');
    var popoverC = document.getElementById('bhc-popover');
    var yearC    = document.getElementById('bhc-year-display');
    var gridC    = document.getElementById('bhc-month-grid');
    var prevYrC  = document.getElementById('bhc-prev-year');
    var nextYrC  = document.getElementById('bhc-next-year');
    var thisMonC = document.getElementById('bhc-this-month');
    var lastMonC = document.getElementById('bhc-last-month');
    var labelC   = document.getElementById('bhc-trigger-label');

    function updateLabelC() {
      if (labelC) labelC.textContent = MONTHS_LONG[selC.month] + ' ' + selC.year;
    }

    function renderGridC() {
      if (!gridC || !yearC) return;
      yearC.textContent = browseYearC;
      gridC.innerHTML = '';
      MONTHS_SHORT.forEach(function(abbr, m) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'bhc-month-btn';
        btn.textContent = abbr;
        btn.setAttribute('aria-label', MONTHS_LONG[m] + ' ' + browseYearC);
        if (m === CURRENT_MONTH && browseYearC === CURRENT_YEAR) btn.classList.add('bhc-today');
        if (m === selC.month && browseYearC === selC.year) btn.classList.add('bhc-selected');
        btn.addEventListener('click', function() { selectMonthC(browseYearC, m); });
        gridC.appendChild(btn);
      });
    }

    function openPopC() {
      browseYearC = selC.year;
      renderGridC();
      if (popoverC) popoverC.classList.add('bhc-open');
      if (triggerC) triggerC.setAttribute('aria-expanded','true');
      popOpenC = true;
      var first = gridC && gridC.querySelector('.bhc-month-btn');
      if (first) setTimeout(function() { first.focus(); }, 60);
    }

    function closePopC() {
      if (popoverC) popoverC.classList.remove('bhc-open');
      if (triggerC) triggerC.setAttribute('aria-expanded','false');
      popOpenC = false;
      if (triggerC) triggerC.focus();
    }

    function selectMonthC(y, m) {
      selC = {year: y, month: m};
      closePopC();
      updateLabelC();
      var wrap = document.getElementById('bh-sel-calendar');
      if (wrap && wrap.classList.contains('bh-visible')) {
        BillingPage.setPeriod(y, m + 1);
      }
    }

    if (triggerC) triggerC.addEventListener('click', function(e) {
      e.stopPropagation(); if (popOpenC) closePopC(); else openPopC();
    });
    if (prevYrC) prevYrC.addEventListener('click', function() { browseYearC--; renderGridC(); });
    if (nextYrC) nextYrC.addEventListener('click', function() { browseYearC++; renderGridC(); });
    if (thisMonC) thisMonC.addEventListener('click', function() {
      selectMonthC(CURRENT_YEAR, CURRENT_MONTH);
    });
    if (lastMonC) lastMonC.addEventListener('click', function() {
      var d = new Date(CURRENT_YEAR, CURRENT_MONTH - 1, 1);
      selectMonthC(d.getFullYear(), d.getMonth());
    });

    document.addEventListener('click', function(e) {
      if (popOpenC && wrapC && !wrapC.contains(e.target)) closePopC();
    });
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && popOpenC) closePopC();
    });

    // Popover tab-trap
    if (popoverC) popoverC.addEventListener('keydown', function(e) {
      if (e.key !== 'Tab') return;
      var focusable = Array.from(popoverC.querySelectorAll('button:not([disabled])'));
      if (!focusable.length) return;
      var first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });

    // Init
    updateLabelC();
  })();

  /* ======================================================
     Boot — run on DOMContentLoaded
     ====================================================== */
  function boot() {
    updatePeriodLabel();
    BillingPage.refresh();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

})();
</script>
"""

    return page_shell(body + js, title="Billing", active="billing")


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
