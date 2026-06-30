"""
Dashboard HTML templates for the ecommerce pricing pipeline.

Renders the batch dashboard and recommendation tables served by Flask.
"""

from jinja2 import Template
from ui.shell import page_shell


# ---------------------------------------------------------------------------
# Batch list page — shows all weekly pipeline runs
# ---------------------------------------------------------------------------
BATCH_LIST_TEMPLATE = Template("""
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
""")


# ---------------------------------------------------------------------------
# Single batch detail page — recommendations with approve/reject
# ---------------------------------------------------------------------------
DASHBOARD_TEMPLATE = Template("""
<div class="container">
    <h1>Batch #{{ batch.ID }} — {{ batch.CreatedAt.strftime('%B %d, %Y') if batch.CreatedAt else '' }}</h1>

    <div class="alert-banner">
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
                    <div class="actions actions--inline">
                        <button class="btn btn-approve" onclick="decide({{ rec.ID }}, 'approve')">Approve</button>
                        <button class="btn btn-reject" onclick="decide({{ rec.ID }}, 'reject')">Reject</button>
                    </div>
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
    <div class="modal modal--wide">
        <button class="modal-close" onclick="closeModal()">&times;</button>
        <h2>Generated Listing Preview</h2>

        <div id="modal-loader" class="modal-loader">
            <div class="spinner"></div>
            <span id="modal-loader-text">Generating listing copy…</span>
        </div>

        <div id="modal-body" class="modal-body">
            <div class="modal-meta" id="modal-meta"></div>
            <div id="post-status" style="display:none; padding:10px 14px; margin:12px 0;
                 border-radius:6px; font-size:14px; font-weight:bold;"></div>
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
</div>

<script>
function decide(recId, action) {
    var row = document.getElementById('rec-' + recId);
    var buttons = row.querySelectorAll('button');
    var originalLabels = [];
    buttons.forEach(function(btn) {
        originalLabels.push(btn.textContent);
        btn.disabled = true;
        btn.className = 'btn btn-disabled';
    });
    // Show inline "Approving..." / "Rejecting..." text in the first button so
    // the row gives feedback even if the modal is off-screen.
    if (buttons[0]) {
        buttons[0].textContent = action === 'approve' ? 'Approving…' : 'Rejecting…';
    }

    // Open the modal immediately on approve so the user sees a spinner
    // instead of an idle page while Claude + the marketplace API runs.
    if (action === 'approve') {
        openModalWithLoader('Generating listing copy and posting…');
    }

    fetch('/ecommerce/' + action + '?id=' + recId, { method: 'POST' })
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            var cell = buttons[0].parentNode;
            if (data.ok) {
                var label = action === 'approve' ? 'Approved' : 'Rejected';
                var cls = action === 'approve' ? 'decision-approved' : 'decision-rejected';
                cell.innerHTML = '';
                var span = document.createElement('span');
                span.className = cls;
                span.textContent = label;
                cell.appendChild(span);
                showToast(data.message, 'success');

                if (action === 'approve' && data.listing) {
                    showListingPreview(data);
                } else {
                    closeModal();
                }
            } else {
                // Restore the buttons so the user can retry (per #138 AC:
                // on API failure the recommendation is NOT marked approved).
                closeModal();
                buttons.forEach(function(btn, i) {
                    btn.disabled = false;
                    btn.className = btn.dataset.cls || (i === 0 ? 'btn btn-approve' : 'btn btn-reject');
                    btn.textContent = originalLabels[i];
                });
                showToast(data.error || 'Action failed', 'error');
            }
        })
        .catch(function() {
            closeModal();
            showToast('Network error', 'error');
            buttons.forEach(function(btn, i) {
                btn.disabled = false;
                btn.className = btn.dataset.cls || (i === 0 ? 'btn btn-approve' : 'btn btn-reject');
                btn.textContent = originalLabels[i];
            });
        });
}

function openModalWithLoader(message) {
    var modal = document.getElementById('listing-modal');
    var loader = document.getElementById('modal-loader');
    var body = document.getElementById('modal-body');
    if (loader) {
        loader.style.display = 'flex';
        var txt = document.getElementById('modal-loader-text');
        if (txt) txt.textContent = message || 'Loading…';
    }
    if (body) body.classList.remove('ready');
    modal.classList.add('active');
}

function showListingPreview(data) {
    var listing = data.listing;
    // Hide the spinner and reveal the populated body.
    document.getElementById('modal-loader').style.display = 'none';
    document.getElementById('modal-body').classList.add('ready');

    document.getElementById('modal-meta').textContent =
        data.product + ' \u2014 ' + data.marketplace + ' \u2014 $' + parseFloat(data.price).toFixed(2);

    // 1D.6: green banner when auto-posted, yellow when preview-only.
    // Build with createElement + textContent to avoid innerHTML interpolation
    // of marketplace / env / listing_id values.
    var status = document.getElementById('post-status');
    status.textContent = '';
    status.style.display = 'block';
    if (data.posted) {
        status.style.background = '#e8f5e9';
        status.style.color = '#2e7d32';
        status.style.border = '1px solid #a5d6a7';
        status.appendChild(document.createTextNode('\u2705 Auto-posted to '));
        var mp = document.createElement('b');
        mp.textContent = data.marketplace;
        status.appendChild(mp);
        status.appendChild(document.createTextNode(' ('));
        var envEl = document.createElement('b');
        envEl.textContent = data.env || 'production';
        status.appendChild(envEl);
        status.appendChild(document.createTextNode(') \u2014 listing ID: '));
        var idEl = document.createElement('code');
        idEl.textContent = data.public_listing_id || data.listing_id || '?';
        status.appendChild(idEl);
        if (data.listing_url) {
            status.appendChild(document.createTextNode('  '));
            var viewLink = document.createElement('a');
            viewLink.href = data.listing_url;
            viewLink.target = '_blank';
            viewLink.rel = 'noopener';
            viewLink.textContent = 'View listing \u2192';
            viewLink.style.fontWeight = 'bold';
            viewLink.style.color = '#1b5e20';
            status.appendChild(viewLink);
        }
    } else {
        status.style.background = '#fffde7';
        status.style.color = '#f57f17';
        status.style.border = '1px solid #fff59d';
        status.appendChild(document.createTextNode('\U0001F4CB '));
        var pv = document.createElement('b');
        pv.textContent = 'Preview only';
        status.appendChild(pv);
        status.appendChild(document.createTextNode(' \u2014 no API for '));
        var mp2 = document.createElement('b');
        mp2.textContent = data.marketplace;
        status.appendChild(mp2);
        status.appendChild(document.createTextNode(
            '. Copy the content below and paste it into the marketplace manually.'));
    }

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
""")


def render_batch_list(batches):
    """Render the batch list page."""
    return page_shell(BATCH_LIST_TEMPLATE.render(batches=batches), title="Ecommerce Pricing Dashboard", active="ecommerce")


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

    return page_shell(
        DASHBOARD_TEMPLATE.render(
            batch=batch,
            recommendations=recommendations,
            recommended=recommended,
            skipped=skipped,
            recommended_count=len(recommended),
            skipped_count=len(skipped),
            decided_count=len(decided),
        ),
        title="Ecommerce Pricing",
        active="ecommerce",
        back=("/ecommerce/dashboard", "All Batches"),
    )
