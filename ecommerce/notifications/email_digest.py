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

    <div class="card scope-card">
        <h3>Scrape scope</h3>
        <p class="muted">Controls what the weekly pricing run scrapes. Applies to the next scheduled run (Mon 6 AM) &mdash; devices we can't classify count as Phones.</p>

        <div class="scope-row">
            <span class="scope-row__label">Categories</span>
            <div class="bh-checks scope-cats">
                <label><input type="checkbox" class="scope-cat" value="phone" {{ 'checked' if 'phone' in settings.categories else '' }}> Phones</label>
                <label><input type="checkbox" class="scope-cat" value="wearable" {{ 'checked' if 'wearable' in settings.categories else '' }}> Wearables</label>
                <label><input type="checkbox" class="scope-cat" value="tablet" {{ 'checked' if 'tablet' in settings.categories else '' }}> Tablets</label>
                <label><input type="checkbox" class="scope-cat" value="accessory" {{ 'checked' if 'accessory' in settings.categories else '' }}> Accessories</label>
            </div>
        </div>

        <div class="scope-row">
            <span class="scope-row__label">Products</span>
            <div class="scope-scope">
                <label class="scope-radio"><input type="radio" name="scope_mode" value="all" {{ 'checked' if settings.scope_mode != 'top' else '' }}> All products</label>
                <label class="scope-radio"><input type="radio" name="scope_mode" value="top" {{ 'checked' if settings.scope_mode == 'top' else '' }}> Top
                    <input type="number" id="scope-topn" min="1" value="{{ settings.top_n or 30 }}"> models</label>
            </div>
        </div>

        <div class="scope-actions">
            <button type="button" class="btn btn-primary" id="scope-save">Save</button>
            <button type="button" class="btn btn-secondary" id="scope-preview-btn">Preview impact</button>
            <span class="muted" id="scope-preview-out"></span>
            <button type="button" class="scope-toggle" id="scope-details-toggle" aria-expanded="false" aria-controls="scope-details" hidden>
                <span class="scope-toggle__label">Show details</span>
                <span class="scope-toggle__caret" aria-hidden="true">▸</span>
            </button>
        </div>

        <div class="scope-details" id="scope-details" hidden>
            <div class="scope-details__block">
                <div class="scope-details__title">Impact by category</div>
                <div class="table-wrap scope-details__scroll">
                    <table>
                        <thead>
                            <tr><th>Category</th><th class="num">Models</th><th class="num">Units</th><th class="num">Groups</th></tr>
                        </thead>
                        <tbody id="scope-detail-rows"></tbody>
                    </table>
                </div>
            </div>
            <div class="scope-details__block">
                <div class="scope-details__title">Top models</div>
                <div class="table-wrap scope-details__scroll">
                    <table>
                        <thead>
                            <tr><th>Model</th><th>Category</th><th class="num">Units</th></tr>
                        </thead>
                        <tbody id="scope-topmodels-rows"></tbody>
                    </table>
                </div>
                <p class="muted scope-details__note" id="scope-topmodels-note" hidden></p>
            </div>
        </div>
    </div>

    {% if batches %}
    <div class="table-wrap">
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
    </div>
    {% else %}
    <p class="empty">No pipeline runs yet. The first batch will appear after the weekly cron job runs.</p>
    {% endif %}
</div>

<div class="toast" id="toast"></div>

<script>
function scopeToast(msg, type) {
    var t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast toast-' + (type || 'success');
    t.style.display = 'block';
    setTimeout(function () { t.style.display = 'none'; }, 3500);
}
function scopeCats() {
    var out = [], boxes = document.querySelectorAll('.scope-cat');
    for (var i = 0; i < boxes.length; i++) { if (boxes[i].checked) out.push(boxes[i].value); }
    return out;
}
function scopeMode() {
    var r = document.querySelector('input[name=\"scope_mode\"]:checked');
    return r ? r.value : 'all';
}
function scopeTopN() { return parseInt(document.getElementById('scope-topn').value, 10) || 30; }
function scopeSyncEnabled() { document.getElementById('scope-topn').disabled = (scopeMode() !== 'top'); }

function scopeCatLabel(key) {
    var labels = { phone: 'Phones', wearable: 'Wearables', tablet: 'Tablets', accessory: 'Accessories' };
    return labels[key] || key;
}
function scopeCell(value, isNum) {
    var td = document.createElement('td');
    if (isNum) { td.className = 'num'; }
    td.textContent = (value === null || value === undefined) ? '' : value;
    return td;
}
function scopeRenderDetails(d) {
    var body = document.getElementById('scope-detail-rows');
    body.innerHTML = '';
    var detail = d.detail || [];
    for (var i = 0; i < detail.length; i++) {
        var row = detail[i], tr = document.createElement('tr');
        tr.appendChild(scopeCell(row.label, false));
        tr.appendChild(scopeCell(row.models, true));
        tr.appendChild(scopeCell(row.units, true));
        tr.appendChild(scopeCell(row.groups, true));
        body.appendChild(tr);
    }
    var tot = document.createElement('tr');
    tot.className = 'scope-total-row';
    tot.appendChild(scopeCell('Total', false));
    tot.appendChild(scopeCell(d.total, true));
    tot.appendChild(scopeCell(d.units, true));
    tot.appendChild(scopeCell(d.groups, true));
    body.appendChild(tot);

    var tbody = document.getElementById('scope-topmodels-rows');
    tbody.innerHTML = '';
    var tm = d.top_models || [];
    for (var j = 0; j < tm.length; j++) {
        var m = tm[j], mtr = document.createElement('tr');
        var name = (m.manufacturer ? m.manufacturer + ' ' : '') + (m.model || '');
        mtr.appendChild(scopeCell(name, false));
        mtr.appendChild(scopeCell(scopeCatLabel(m.category), false));
        mtr.appendChild(scopeCell(m.units, true));
        tbody.appendChild(mtr);
    }
    var note = document.getElementById('scope-topmodels-note');
    if (d.top_models_truncated) {
        note.textContent = 'showing top ' + tm.length + ' by volume';
        note.hidden = false;
    } else {
        note.textContent = '';
        note.hidden = true;
    }
}
function scopeSetToggle(expanded) {
    var toggle = document.getElementById('scope-details-toggle');
    var panel = document.getElementById('scope-details');
    toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    toggle.querySelector('.scope-toggle__label').textContent = expanded ? 'Hide details' : 'Show details';
    toggle.querySelector('.scope-toggle__caret').textContent = expanded ? '▾' : '▸';
    panel.hidden = !expanded;
}
function scopeHideDetails() {
    scopeSetToggle(false);
    document.getElementById('scope-details-toggle').hidden = true;
}

(function () {
    var radios = document.querySelectorAll('input[name=\"scope_mode\"]');
    for (var i = 0; i < radios.length; i++) { radios[i].addEventListener('change', scopeSyncEnabled); }

    document.getElementById('scope-details-toggle').addEventListener('click', function () {
        scopeSetToggle(this.getAttribute('aria-expanded') !== 'true');
    });

    document.getElementById('scope-save').addEventListener('click', function () {
        var btn = this, cats = scopeCats();
        if (!cats.length) { scopeToast('Select at least one category', 'error'); return; }
        var old = btn.textContent;
        btn.disabled = true; btn.textContent = 'Saving...';
        fetch('/ecommerce/scrape-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ categories: cats, scope_mode: scopeMode(), top_n: scopeTopN() })
        }).then(function (r) { return r.json(); }).then(function (d) {
            btn.disabled = false; btn.textContent = old;
            if (d.ok) { scopeToast('Scrape scope saved — applies on the next weekly run', 'success'); }
            else { scopeToast(d.error || 'Save failed', 'error'); }
        }).catch(function () { btn.disabled = false; btn.textContent = old; scopeToast('Network error', 'error'); });
    });

    document.getElementById('scope-preview-btn').addEventListener('click', function () {
        var btn = this, out = document.getElementById('scope-preview-out'), cats = scopeCats();
        if (!cats.length) { out.textContent = '0 models selected'; scopeHideDetails(); return; }
        btn.disabled = true; out.textContent = 'Calculating...'; scopeHideDetails();
        var qs = 'categories=' + encodeURIComponent(cats.join(',')) +
                 '&scope_mode=' + encodeURIComponent(scopeMode()) +
                 '&top_n=' + encodeURIComponent(scopeTopN());
        fetch('/ecommerce/scrape-preview?' + qs).then(function (r) { return r.json(); }).then(function (d) {
            btn.disabled = false;
            if (!d.ok) { out.textContent = d.error || 'Preview failed'; scopeHideDetails(); return; }
            var labels = { phone: 'Phones', wearable: 'Wearables', tablet: 'Tablets', accessory: 'Accessories' }, parts = [];
            for (var k in labels) { if (d.by_category[k]) { parts.push(labels[k] + ' ' + d.by_category[k]); } }
            out.textContent = '≈ ' + d.total + ' models will be scraped' + (parts.length ? ' (' + parts.join(' · ') + ')' : '');
            scopeRenderDetails(d);
            scopeSetToggle(false);
            document.getElementById('scope-details-toggle').hidden = false;
        }).catch(function () { btn.disabled = false; out.textContent = 'Network error'; scopeHideDetails(); });
    });

    scopeSyncEnabled();
})();
</script>
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


def render_batch_list(batches, settings=None):
    """Render the batch list page (with the scrape-scope control)."""
    if settings is None:
        settings = {"categories": ["phone", "wearable", "tablet"], "scope_mode": "all", "top_n": 30}
    return page_shell(
        BATCH_LIST_TEMPLATE.render(batches=batches, settings=settings),
        title="Ecommerce Pricing Dashboard", active="ecommerce")


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
