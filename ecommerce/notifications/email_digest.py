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
                <label class="scope-radio"><input type="radio" name="scope_mode" value="all" {{ 'checked' if settings.scope_mode == 'all' else '' }}> All products</label>
                <label class="scope-radio"><input type="radio" name="scope_mode" value="top" {{ 'checked' if settings.scope_mode in ('top', 'top_sku') else '' }}> Top
                    <input type="number" id="scope-topn" min="1" value="{{ settings.top_n or 30 }}">
                    <select id="scope-top-unit" style="width:auto">
                        <option value="model" {{ 'selected' if settings.scope_mode != 'top_sku' else '' }}>models</option>
                        <option value="sku" {{ 'selected' if settings.scope_mode == 'top_sku' else '' }}>SKUs</option>
                    </select></label>
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
                <p class="muted scope-details__note">Each model is one search (one scrape); each colour/grade variant is its own recommendation row.</p>
                <div class="table-wrap scope-details__scroll">
                    <table>
                        <thead>
                            <tr><th>Category</th><th class="num">Models</th><th class="num">Units</th><th class="num">Variants</th></tr>
                        </thead>
                        <tbody id="scope-detail-rows"></tbody>
                    </table>
                </div>
            </div>
            <div class="scope-details__block" id="scope-block-models">
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
            <div class="scope-details__block" id="scope-block-skus">
                <div class="scope-details__title">Top SKUs (colour/grade variants)</div>
                <div class="table-wrap scope-details__scroll">
                    <table>
                        <thead>
                            <tr><th>Model</th><th>Colour</th><th>Grade</th><th class="num">Units</th></tr>
                        </thead>
                        <tbody id="scope-topskus-rows"></tbody>
                    </table>
                </div>
                <p class="muted scope-details__note" id="scope-topskus-note" hidden></p>
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
    if (!r || r.value === 'all') return 'all';
    var u = document.getElementById('scope-top-unit');
    return (u && u.value === 'sku') ? 'top_sku' : 'top';
}
function scopeTopN() { return parseInt(document.getElementById('scope-topn').value, 10) || 30; }
function scopeSyncEnabled() {
    var r = document.querySelector('input[name=\"scope_mode\"]:checked');
    var isTop = !!r && r.value === 'top';
    document.getElementById('scope-topn').disabled = !isTop;
    var u = document.getElementById('scope-top-unit'); if (u) { u.disabled = !isTop; }
}

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

    var stbody = document.getElementById('scope-topskus-rows');
    stbody.innerHTML = '';
    var sk = d.top_skus || [];
    for (var s = 0; s < sk.length; s++) {
        var v = sk[s], vtr = document.createElement('tr');
        vtr.appendChild(scopeCell((v.manufacturer ? v.manufacturer + ' ' : '') + (v.model || ''), false));
        vtr.appendChild(scopeCell(v.colour, false));
        vtr.appendChild(scopeCell(v.grade, false));
        vtr.appendChild(scopeCell(v.units, true));
        stbody.appendChild(vtr);
    }
    var snote = document.getElementById('scope-topskus-note');
    if (d.top_skus_truncated) {
        snote.textContent = 'showing top ' + sk.length + ' by units';
        snote.hidden = false;
    } else {
        snote.textContent = '';
        snote.hidden = true;
    }

    // Lead with the selected view: Top SKUs first when scope is SKUs, else Top models first.
    var container = document.getElementById('scope-details');
    var mBlock = document.getElementById('scope-block-models');
    var sBlock = document.getElementById('scope-block-skus');
    if (container && mBlock && sBlock) {
        if (scopeMode() === 'top_sku') { container.insertBefore(sBlock, mBlock); }
        else { container.insertBefore(mBlock, sBlock); }
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
            out.textContent = '≈ ' + d.total + ' models (' + d.groups + ' colour/grade variants) will be priced' + (parts.length ? '  — ' + parts.join(' · ') : '');
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
                    <div class="actions actions--inline">
                        <span class="decision-{{ rec.Decision }}">{{ rec.Decision | capitalize }}</span>
                        {% if rec.Decision == 'approved' %}
                        <button onclick="viewListing({{ rec.ID }})"
                                style="padding:5px 12px;border:1px solid #cbd5e1;background:#f1f5f9;color:#334155;border-radius:6px;font-size:13px;cursor:pointer">View</button>
                        {% endif %}
                    </div>
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
            <div id="modal-action" style="margin-top: 20px;"></div>
            <div style="margin-top: 12px;">
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
    // instead of an idle page while Claude generates the copy.
    if (action === 'approve') {
        openModalWithLoader('Generating listing copy…');
    }

    var restore = function() {
        buttons.forEach(function(btn, i) {
            btn.disabled = false;
            btn.className = btn.dataset.cls || (i === 0 ? 'btn btn-approve' : 'btn btn-reject');
            btn.textContent = originalLabels[i];
        });
    };

    fetch('/ecommerce/' + action + '?id=' + recId, { method: 'POST' })
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (!data.ok) {
                closeModal();
                restore();
                showToast(data.error || 'Action failed', 'error');
                return;
            }
            if (action === 'reject') {
                var cell = buttons[0].parentNode;
                cell.innerHTML = '';
                var span = document.createElement('span');
                span.className = 'decision-rejected';
                span.textContent = 'Rejected';
                cell.appendChild(span);
                showToast(data.message, 'success');
                closeModal();
            } else {
                // Approve = PREVIEW ONLY: no status change. Re-enable the row so
                // the user can still Reject or re-open the preview, then show the
                // modal with an Auto-post (API) or Mark-as-listed (no API) button.
                restore();
                showListingPreview(data, recId);
            }
        })
        .catch(function() {
            closeModal();
            restore();
            showToast('Network error', 'error');
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

function showListingPreview(data, recId) {
    var listing = data.listing;
    // Hide the spinner and reveal the populated body.
    document.getElementById('modal-loader').style.display = 'none';
    document.getElementById('modal-body').classList.add('ready');

    document.getElementById('modal-meta').textContent =
        data.product + ' \u2014 ' + data.marketplace + ' \u2014 $' + parseFloat(data.price).toFixed(2);

    // Preview only \u2014 nothing is posted yet, so hide the status banner (it's shown
    // by postListing() after a successful post).
    var status = document.getElementById('post-status');
    status.textContent = '';
    status.style.display = 'none';

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

    // Action area: read-only re-view shows only a banner; otherwise Auto-post
    // (API configured) or a manual Mark-as-listed resolver (with the reason).
    var action = document.getElementById('modal-action');
    action.textContent = '';
    if (data.readonly) {
        var st = document.getElementById('post-status');
        st.textContent = '';
        st.style.display = 'block';
        st.style.background = '#eef2ff';
        st.style.color = '#3730a3';
        st.style.border = '1px solid #c7d2fe';
        st.appendChild(document.createTextNode('✓ Resolved listing — read-only. Copy the content below.'));
        appendListingLink(st, data.listing_url);   // clickable live link, if we saved one at post time
    } else if (data.can_post) {
        var envLabel = data.env ? (' (' + data.env + ')') : '';
        var postBtn = document.createElement('button');
        postBtn.className = 'btn btn-approve';
        postBtn.id = 'modal-post-btn';
        postBtn.textContent = 'Auto-post to ' + data.marketplace + envLabel;
        postBtn.onclick = function() { postListing(recId, data, postBtn); };
        action.appendChild(postBtn);
    } else {
        var note = document.createElement('div');
        note.style.cssText = 'color:#f57f17; font-size:13px; margin-bottom:8px;';
        note.textContent = (data.post_reason || ('No API for ' + data.marketplace + '.')) +
                           ' Copy the content below and list it manually.';
        action.appendChild(note);
        var markBtn = document.createElement('button');
        markBtn.className = 'btn btn-approve';
        markBtn.id = 'modal-mark-btn';
        markBtn.textContent = 'Mark as listed';
        markBtn.onclick = function() { markListed(recId, data, markBtn); };
        action.appendChild(markBtn);
    }

    document.getElementById('listing-modal').classList.add('active');
}

function postListing(recId, data, btn) {
    var env = data.env || 'production';
    if (!confirm('Create a ' + env + ' listing on ' + data.marketplace +
                 ' at $' + parseFloat(data.price).toFixed(2) + '?\\nThis posts to the marketplace.')) {
        return;
    }
    var restoreLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Posting\u2026';
    fetch('/ecommerce/post?id=' + recId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ listing: data.listing }),
    })
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (res.ok) {
                showPostedBanner(res);
                markRowResolved(recId, 'Posted');
                showToast(res.message || 'Posted', 'success');
            } else {
                btn.disabled = false;
                btn.textContent = restoreLabel;
                showToast(res.error || 'Post failed', 'error');
            }
        })
        .catch(function() {
            btn.disabled = false;
            btn.textContent = restoreLabel;
            showToast('Network error', 'error');
        });
}

function markListed(recId, data, btn) {
    if (!confirm('Mark this recommendation as listed on ' + data.marketplace + ' (manual)?')) {
        return;
    }
    btn.disabled = true;
    btn.textContent = 'Saving\u2026';
    fetch('/ecommerce/mark-listed?id=' + recId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    })
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (res.ok) {
                markRowResolved(recId, 'Listed');
                document.getElementById('modal-action').textContent = '';
                showToast(res.message || 'Marked as listed', 'success');
            } else {
                btn.disabled = false;
                btn.textContent = 'Mark as listed';
                showToast(res.error || 'Failed', 'error');
            }
        })
        .catch(function() {
            btn.disabled = false;
            btn.textContent = 'Mark as listed';
            showToast('Network error', 'error');
        });
}

function markRowResolved(recId, label) {
    var row = document.getElementById('rec-' + recId);
    if (!row) return;
    var btns = row.querySelectorAll('button');
    if (btns[0]) {
        var cell = btns[0].parentNode;
        cell.innerHTML = '';
        var wrap = document.createElement('div');
        wrap.className = 'actions actions--inline';
        var span = document.createElement('span');
        span.className = 'decision-approved';
        span.textContent = label;
        wrap.appendChild(span);
        // Mirror the server-rendered View button so the listing (and its live link)
        // is re-openable immediately, without waiting for a page reload.
        var viewBtn = document.createElement('button');
        viewBtn.textContent = 'View';
        viewBtn.setAttribute('style', 'padding:5px 12px;border:1px solid #cbd5e1;background:#f1f5f9;color:#334155;border-radius:6px;font-size:13px;cursor:pointer');
        viewBtn.onclick = function() { viewListing(recId); };
        wrap.appendChild(viewBtn);
        cell.appendChild(wrap);
    }
}

function appendListingLink(el, url) {
    // Append a "View listing ->" anchor to the live marketplace post. Shared by the
    // post-success banner and the read-only re-view banner.
    if (!url) return;
    el.appendChild(document.createTextNode('  '));
    var a = document.createElement('a');
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = 'View listing \u2192';
    a.style.fontWeight = 'bold';
    a.style.color = '#1b5e20';
    el.appendChild(a);
}

function showPostedBanner(res) {
    var status = document.getElementById('post-status');
    status.textContent = '';
    status.style.display = 'block';
    status.style.background = '#e8f5e9';
    status.style.color = '#2e7d32';
    status.style.border = '1px solid #a5d6a7';
    status.appendChild(document.createTextNode('\u2705 Posted to '));
    var mp = document.createElement('b');
    mp.textContent = res.marketplace;
    status.appendChild(mp);
    status.appendChild(document.createTextNode(' ('));
    var envEl = document.createElement('b');
    envEl.textContent = res.env || 'production';
    status.appendChild(envEl);
    status.appendChild(document.createTextNode(') \u2014 listing ID: '));
    var idEl = document.createElement('code');
    idEl.textContent = res.public_listing_id || res.listing_id || '?';
    status.appendChild(idEl);
    appendListingLink(status, res.listing_url);
    // Posting is a terminal action \u2014 clear the action button.
    document.getElementById('modal-action').textContent = '';
}

function viewListing(recId) {
    // Re-open a resolved listing read-only (content + copy buttons; no actions).
    openModalWithLoader('Loading listing…');
    fetch('/ecommerce/listing/' + recId)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.ok) {
                showListingPreview(data, recId);
            } else {
                closeModal();
                showToast(data.error || 'Could not load listing', 'error');
            }
        })
        .catch(function() { closeModal(); showToast('Network error', 'error'); });
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
        settings = {"categories": ["phone", "wearable", "tablet"], "scope_mode": "top_sku", "top_n": 30}
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
