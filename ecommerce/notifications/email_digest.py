"""
Dashboard HTML templates for the ecommerce pricing pipeline.

Renders the batch dashboard and recommendation tables served by Flask.
"""

from jinja2 import Template


# ---------------------------------------------------------------------------
# Batch list page — shows all weekly pipeline runs
# ---------------------------------------------------------------------------
BATCH_LIST_TEMPLATE = Template("""
<!DOCTYPE html>
<html>
<head>
<title>Ecommerce Pricing Dashboard</title>
<style>
    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
    .container { max-width: 900px; margin: 0 auto; background: #fff; border-radius: 8px; padding: 30px; }
    h1 { color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 10px; }
    table { width: 100%; border-collapse: collapse; margin: 15px 0; }
    th { background: #2196F3; color: #fff; padding: 12px 10px; text-align: left; font-size: 13px; }
    td { padding: 10px; border-bottom: 1px solid #eee; font-size: 13px; }
    tr:hover { background: #f9f9f9; }
    a { color: #1565c0; text-decoration: none; font-weight: bold; }
    a:hover { text-decoration: underline; }
    .status-ready { color: #2e7d32; font-weight: bold; }
    .status-completed { color: #999; }
    .status-pending { color: #e65100; }
    .empty { color: #999; padding: 40px 0; text-align: center; }
</style>
</head>
<body>
<div class="container">
    <h1>Ecommerce Pricing Dashboard</h1>

    {% if batches %}
    <table>
        <tr>
            <th>Batch</th>
            <th>Date</th>
            <th>Status</th>
            <th></th>
        </tr>
        {% for batch in batches %}
        <tr>
            <td>#{{ batch.ID }}</td>
            <td>{{ batch.CreatedAt.strftime('%B %d, %Y at %I:%M %p') if batch.CreatedAt else 'N/A' }}</td>
            <td class="status-{{ batch.Status }}">{{ batch.Status | capitalize }}</td>
            <td><a href="/ecommerce/dashboard/{{ batch.ID }}">View &rarr;</a></td>
        </tr>
        {% endfor %}
    </table>
    {% else %}
    <p class="empty">No pipeline runs yet. The first batch will appear after the weekly cron job runs.</p>
    {% endif %}
</div>
</body>
</html>
""")


# ---------------------------------------------------------------------------
# Single batch detail page — recommendations with approve/reject
# ---------------------------------------------------------------------------
DASHBOARD_TEMPLATE = Template("""
<!DOCTYPE html>
<html>
<head>
<title>Batch #{{ batch.ID }} — Ecommerce Pricing</title>
<style>
    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
    .container { max-width: 1100px; margin: 0 auto; background: #fff; border-radius: 8px; padding: 30px; }
    h1 { color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 10px; }
    h2 { color: #555; margin-top: 30px; }
    table { width: 100%; border-collapse: collapse; margin: 15px 0; }
    th { background: #2196F3; color: #fff; padding: 12px 10px; text-align: left; font-size: 13px; }
    td { padding: 10px; border-bottom: 1px solid #eee; font-size: 13px; }
    tr:hover { background: #f9f9f9; }
    .price { font-weight: bold; color: #2e7d32; }
    .skip { color: #c62828; }
    .btn { display: inline-block; padding: 6px 16px; border-radius: 4px; text-decoration: none;
           font-size: 12px; font-weight: bold; margin-right: 5px; cursor: pointer; border: none; }
    .btn-approve { background: #4CAF50; color: #fff; }
    .btn-approve:hover { background: #388E3C; }
    .btn-reject { background: #f44336; color: #fff; }
    .btn-reject:hover { background: #c62828; }
    .btn-disabled { background: #bdbdbd; color: #fff; cursor: default; }
    .summary { background: #e3f2fd; padding: 15px; border-radius: 6px; margin-bottom: 20px; }
    .back { display: inline-block; margin-bottom: 15px; color: #1565c0; text-decoration: none; }
    .back:hover { text-decoration: underline; }
    .decision-approved { color: #2e7d32; font-weight: bold; }
    .decision-rejected { color: #c62828; font-weight: bold; }
    .decision-pending { color: #e65100; }
    .footer { margin-top: 30px; font-size: 12px; color: #999; border-top: 1px solid #eee; padding-top: 15px; }
    .toast { display: none; position: fixed; top: 20px; right: 20px; padding: 12px 24px;
             border-radius: 6px; color: #fff; font-weight: bold; z-index: 1000; }
    .toast-success { background: #4CAF50; }
    .toast-error { background: #f44336; }

    /* Listing preview modal */
    .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 2000;
                     justify-content: center; align-items: flex-start; padding: 40px 20px; overflow-y: auto; }
    .modal-overlay.active { display: flex; }
    .modal { background: #fff; border-radius: 8px; max-width: 700px; width: 100%; padding: 30px;
             position: relative; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
    .modal h2 { margin-top: 0; color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 10px; }
    .modal-close { position: absolute; top: 12px; right: 16px; font-size: 22px; cursor: pointer;
                   background: none; border: none; color: #999; }
    .modal-close:hover { color: #333; }
    .listing-field { margin-bottom: 16px; }
    .listing-field label { display: block; font-weight: bold; color: #555; margin-bottom: 4px; font-size: 12px;
                           text-transform: uppercase; letter-spacing: 0.5px; }
    .listing-field .value { background: #f5f5f5; padding: 10px 14px; border-radius: 4px; border: 1px solid #e0e0e0;
                            font-size: 14px; line-height: 1.5; white-space: pre-wrap; }
    .listing-field ul { background: #f5f5f5; padding: 10px 14px 10px 30px; border-radius: 4px;
                        border: 1px solid #e0e0e0; margin: 0; font-size: 14px; line-height: 1.8; }
    .btn-copy { background: #2196F3; color: #fff; border: none; padding: 8px 20px; border-radius: 4px;
                font-size: 13px; font-weight: bold; cursor: pointer; margin-right: 8px; }
    .btn-copy:hover { background: #1565c0; }
    .btn-copy.copied { background: #4CAF50; }
    .modal-meta { color: #777; font-size: 13px; margin-bottom: 18px; }
</style>
</head>
<body>
<div class="container">
    <a href="/ecommerce/dashboard" class="back">&larr; All Batches</a>
    <h1>Batch #{{ batch.ID }} — {{ batch.CreatedAt.strftime('%B %d, %Y') if batch.CreatedAt else '' }}</h1>

    <div class="summary">
        <strong>{{ recommendations | length }}</strong> SKUs scanned &mdash;
        <strong>{{ recommended_count }}</strong> recommended,
        <strong>{{ skipped_count }}</strong> skipped,
        <strong>{{ decided_count }}</strong> decided
    </div>

    {% if recommended %}
    <h2>Recommended Listings</h2>
    <table>
        <tr>
            <th>Product</th>
            <th>Qty</th>
            <th>Marketplace</th>
            <th>Price</th>
            <th>Amazon</th>
            <th>eBay</th>
            <th>Best Buy</th>
            <th>Reebelo</th>
            <th>Cost</th>
            <th>Action</th>
        </tr>
        {% for rec in recommended %}
        <tr id="rec-{{ rec.ID }}">
            <td>{{ rec.Manufacturer }} {{ rec.Model }}<br>
                <small>{{ rec.Colour }} / Grade {{ rec.Grade }}</small></td>
            <td>{{ rec.Quantity }}</td>
            <td><strong>{{ rec.RecommendedMarketplace }}</strong></td>
            <td class="price">${{ "%.2f" | format(rec.RecommendedPrice) }}</td>
            <td>{{ "$%.2f" | format(rec.AmazonFloor) if rec.AmazonFloor else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.EbayFloor) if rec.EbayFloor else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.BestBuyFloor) if rec.BestBuyFloor else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.ReebeloFloor) if rec.ReebeloFloor else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.DeviceCost) if rec.DeviceCost else "N/A" }}</td>
            <td>
                {% if rec.Decision %}
                    <span class="decision-{{ rec.Decision }}">{{ rec.Decision | capitalize }}</span>
                {% else %}
                    <button class="btn btn-approve" onclick="decide({{ rec.ID }}, 'approve')">Approve</button>
                    <button class="btn btn-reject" onclick="decide({{ rec.ID }}, 'reject')">Reject</button>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    {% if skipped %}
    <h2>Skipped (Margin / Data Issues)</h2>
    <table>
        <tr>
            <th>Product</th>
            <th>Qty</th>
            <th>Reason</th>
            <th>Amazon</th>
            <th>eBay</th>
            <th>Best Buy</th>
            <th>Reebelo</th>
            <th>Cost</th>
        </tr>
        {% for rec in skipped %}
        <tr>
            <td>{{ rec.Manufacturer }} {{ rec.Model }}<br>
                <small>{{ rec.Colour }} / Grade {{ rec.Grade }}</small></td>
            <td>{{ rec.Quantity }}</td>
            <td class="skip">{{ rec.SkipReason }}</td>
            <td>{{ "$%.2f" | format(rec.AmazonFloor) if rec.AmazonFloor else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.EbayFloor) if rec.EbayFloor else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.BestBuyFloor) if rec.BestBuyFloor else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.ReebeloFloor) if rec.ReebeloFloor else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.DeviceCost) if rec.DeviceCost else "N/A" }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    {% if not recommendations %}
    <p style="color: #999; text-align: center; padding: 40px 0;">
        No products were found in this batch.
    </p>
    {% endif %}

    <div class="footer">
        Generated by the Ecommerce AI Pipeline.
    </div>
</div>

<div id="toast" class="toast"></div>

<!-- Listing preview modal -->
<div id="listing-modal" class="modal-overlay" onclick="if(event.target===this)closeModal()">
    <div class="modal">
        <button class="modal-close" onclick="closeModal()">&times;</button>
        <h2>Generated Listing Preview</h2>
        <div class="modal-meta" id="modal-meta"></div>
        <div class="listing-field">
            <label>Title</label>
            <div class="value" id="listing-title"></div>
        </div>
        <div class="listing-field">
            <label>Description</label>
            <div class="value" id="listing-description"></div>
        </div>
        <div class="listing-field">
            <label>Bullet Points</label>
            <ul id="listing-bullets"></ul>
        </div>
        <div class="listing-field">
            <label>Condition Note</label>
            <div class="value" id="listing-condition"></div>
        </div>
        <div style="margin-top: 20px;">
            <button class="btn-copy" onclick="copyAll()">Copy All to Clipboard</button>
            <button class="btn-copy" onclick="copyField('listing-title')" style="background:#78909C;">Copy Title</button>
            <button class="btn-copy" onclick="copyField('listing-description')" style="background:#78909C;">Copy Description</button>
        </div>
    </div>
</div>

<script>
function decide(recId, action) {
    var row = document.getElementById('rec-' + recId);
    var buttons = row.querySelectorAll('button');
    buttons.forEach(function(btn) { btn.disabled = true; btn.className = 'btn btn-disabled'; });

    fetch('/ecommerce/' + action + '?id=' + recId, { method: 'POST' })
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            var cell = buttons[0].parentNode;
            if (data.ok) {
                var label = action === 'approve' ? 'Approved' : 'Rejected';
                var cls = action === 'approve' ? 'decision-approved' : 'decision-rejected';
                cell.innerHTML = '<span class="' + cls + '">' + label + '</span>';
                showToast(data.message, 'success');

                // Show listing preview modal on approve
                if (action === 'approve' && data.listing) {
                    showListingPreview(data);
                }
            } else {
                cell.innerHTML = '<span class="skip">' + (data.error || 'Error') + '</span>';
                showToast(data.error || 'Action failed', 'error');
            }
        })
        .catch(function() {
            showToast('Network error', 'error');
            buttons.forEach(function(btn) { btn.disabled = false; btn.className = btn.dataset.cls; });
        });
}

function showListingPreview(data) {
    var listing = data.listing;
    document.getElementById('modal-meta').textContent =
        data.product + ' \u2014 ' + data.marketplace + ' \u2014 $' + parseFloat(data.price).toFixed(2);
    document.getElementById('listing-title').textContent = listing.title || '';
    document.getElementById('listing-description').textContent = listing.description || '';
    document.getElementById('listing-condition').textContent = listing.condition_note || '';

    var bulletsEl = document.getElementById('listing-bullets');
    bulletsEl.innerHTML = '';
    if (listing.bullets) {
        listing.bullets.forEach(function(b) {
            var li = document.createElement('li');
            li.textContent = b;
            bulletsEl.appendChild(li);
        });
    }

    document.getElementById('listing-modal').classList.add('active');
}

function closeModal() {
    document.getElementById('listing-modal').classList.remove('active');
}

function copyField(elementId) {
    var text = document.getElementById(elementId).textContent;
    navigator.clipboard.writeText(text).then(function() {
        showToast('Copied!', 'success');
    });
}

function copyAll() {
    var title = document.getElementById('listing-title').textContent;
    var desc = document.getElementById('listing-description').textContent;
    var condition = document.getElementById('listing-condition').textContent;
    var bullets = [];
    document.querySelectorAll('#listing-bullets li').forEach(function(li) {
        bullets.push('- ' + li.textContent);
    });

    var full = 'TITLE:\\n' + title + '\\n\\nDESCRIPTION:\\n' + desc +
               '\\n\\nBULLET POINTS:\\n' + bullets.join('\\n') +
               '\\n\\nCONDITION NOTE:\\n' + condition;

    navigator.clipboard.writeText(full).then(function() {
        var btn = event.target;
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(function() { btn.textContent = 'Copy All to Clipboard'; btn.classList.remove('copied'); }, 2000);
    });
}

function showToast(msg, type) {
    var t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast toast-' + type;
    t.style.display = 'block';
    setTimeout(function() { t.style.display = 'none'; }, 3000);
}

// Close modal on Escape
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeModal(); });
</script>
</body>
</html>
""")


def render_batch_list(batches):
    """Render the batch list page."""
    return BATCH_LIST_TEMPLATE.render(batches=batches)


def render_dashboard(batch, recommendations):
    """Render the single-batch dashboard page."""
    # pyodbc returns DECIMAL columns as Python Decimal objects; cast to float
    # so Jinja2's "%.2f" | format() filter works correctly.
    numeric_fields = ('RecommendedPrice', 'AmazonFloor', 'EbayFloor',
                      'BestBuyFloor', 'ReebeloFloor', 'DeviceCost')
    for rec in recommendations:
        for field in numeric_fields:
            if rec.get(field) is not None:
                rec[field] = float(rec[field])

    recommended = [r for r in recommendations if r.get('MarginOK')]
    skipped = [r for r in recommendations if not r.get('MarginOK')]
    decided = [r for r in recommended if r.get('Decision')]

    return DASHBOARD_TEMPLATE.render(
        batch=batch,
        recommendations=recommendations,
        recommended=recommended,
        skipped=skipped,
        recommended_count=len(recommended),
        skipped_count=len(skipped),
        decided_count=len(decided),
    )
