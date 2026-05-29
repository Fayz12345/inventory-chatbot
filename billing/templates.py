"""HTML for the TMS billing page. Single function returning a full page.

Schedule is embedded as JSON so the browser can render rows (including manual
inputs) and recompute totals live. Generate fetches /billing/tms/generate.
"""
import json

from billing import schedule


def render_tms_billing_page():
    schedule_json = json.dumps(schedule.TMS_FEE_SCHEDULE)
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>TMS Billing Report - Bridge Platform</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f0f2f5; color: #333; }}
    .header {{ background: #2563eb; color: #fff; padding: 14px 24px; display: flex;
              justify-content: space-between; align-items: center; }}
    .header h1 {{ margin: 0; font-size: 22px; }}
    .header a {{ color: #fff; text-decoration: none; opacity: 0.85; }}
    .container {{ max-width: 1000px; margin: 32px auto; padding: 0 20px; }}
    .controls {{ background: #fff; border-radius: 10px; padding: 20px 24px; margin-bottom: 24px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.08); display: flex; gap: 16px; align-items: flex-end;
                flex-wrap: wrap; }}
    label {{ display: block; font-size: 13px; color: #666; margin-bottom: 4px; }}
    select, input[type=number] {{ padding: 8px 10px; border: 1px solid #ccc; border-radius: 6px;
                font-size: 14px; }}
    button {{ background: #2563eb; color: #fff; border: none; padding: 10px 20px; border-radius: 6px;
             font-size: 14px; cursor: pointer; }}
    button.secondary {{ background: #e5e7eb; color: #333; }}
    button:disabled {{ opacity: 0.5; cursor: default; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px;
            overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
    th, td {{ padding: 8px 12px; text-align: left; font-size: 14px; border-bottom: 1px solid #eee; }}
    th {{ background: #2563eb; color: #fff; }}
    td.num, th.num {{ text-align: right; }}
    tr.section td {{ background: #f3f4f6; font-weight: bold; }}
    tr.subtotal td {{ font-weight: bold; background: #fafafa; }}
    tr.grand td {{ font-weight: bold; background: #dbeafe; font-size: 15px; }}
    input.manual {{ width: 80px; }}
    .err {{ color: #b91c1c; margin: 12px 0; }}
    .hint {{ color: #999; font-size: 12px; }}
    .loader {{ display: flex; align-items: center; gap: 12px; color: #2563eb; font-size: 15px;
              padding: 32px; background: #fff; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
    .spinner {{ width: 22px; height: 22px; border: 3px solid #dbeafe; border-top-color: #2563eb;
               border-radius: 50%; animation: spin 0.8s linear infinite; }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  </style>
</head>
<body>
  <div class="header">
    <h1>TMS Billing Report</h1>
    <div><a href="/home">Home</a> &nbsp; <a href="/logout">Sign out</a></div>
  </div>
  <div class="container">
    <div class="controls">
      <div>
        <label>Month</label>
        <select id="month"></select>
      </div>
      <div>
        <label>Year</label>
        <select id="year"></select>
      </div>
      <button id="generate">Generate Billing Report</button>
      <button id="copy" class="secondary" disabled>Copy</button>
      <button id="csv" class="secondary" disabled>Download CSV</button>
    </div>
    <div id="error" class="err"></div>
    <div id="result"></div>
    <p class="hint">Manual line items are editable. The grand total updates as you type.
       Validate against the Excel report before invoicing.</p>
  </div>

<script>
const SCHEDULE = {schedule_json};
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
  document.getElementById('copy').disabled = false;
  document.getElementById('csv').disabled = false;
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
    try {{
      const resp = await fetch('/billing/tms/generate', {{
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
    a.download = 'TMS_Billing_' + lastReport.period_label.replace(' ', '_') + '.csv';
    a.click();
  }});
}});
</script>
</body>
</html>"""
