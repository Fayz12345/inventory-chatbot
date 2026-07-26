"""Post-scrape run report.

Collects per-source scrape outcomes for EVERY scraping source (not just Apify):
Amazon + eBay run via Apify actors; Best Buy + Reebelo via first-party (browser)
search APIs. Each source records ok/failed + keyword coverage + a reason, so a
silent failure — e.g. an eBay antibot block that returns 0 items, or a first-party
API that errors — is surfaced in an email instead of vanishing into the log.
"""

import html as _html
import logging

from ecommerce import config
from ecommerce.notifications import mailer

log = logging.getLogger(__name__)


class RunReport:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.sources = []       # [{name, kind, ok, hits, total, detail}]
        self.batch_id = None
        self.recommended = 0
        self.skipped = 0
        self.scope = None
        self.keywords = 0
        self.pipeline_error = None

    # --- collection ---
    def record_source(self, name, kind, ok, hits=0, total=0, detail=""):
        self.sources.append({"name": name, "kind": kind, "ok": ok,
                             "hits": hits, "total": total, "detail": detail})

    def set_scope(self, scope, keywords):
        self.scope = scope
        self.keywords = keywords

    def set_batch(self, batch_id, recommended, skipped):
        self.batch_id = batch_id
        self.recommended = recommended
        self.skipped = skipped

    def set_error(self, exc):
        self.pipeline_error = "%s: %s" % (type(exc).__name__, exc)

    # --- analysis ---
    def _source_reason(self, s):
        if s["ok"]:
            return "OK — %d/%d keywords returned data" % (s["hits"], s["total"])
        if s["detail"]:
            return s["detail"]
        if s["total"] and s["hits"] == 0:
            return ("0/%d keywords returned data — likely an antibot/proxy block or an "
                    "actor failure (not simply 'no listings')" % s["total"])
        return "no data"

    def failures(self):
        out = [(s["name"], self._source_reason(s)) for s in self.sources if not s["ok"]]
        if self.pipeline_error:
            out.append(("pipeline", self.pipeline_error))
        return out

    def has_failures(self):
        return bool(self.failures())

    def subject(self):
        tag = "⚠ FAILURES" if self.has_failures() else "OK"
        b = ("Batch #%s" % self.batch_id) if self.batch_id else \
            ("dry-run" if self.dry_run else "no batch")
        return "[Ecommerce scrape] %s — %s — %d recs" % (tag, b, self.recommended)

    # --- render ---
    def render_html(self):
        e = _html.escape
        p = ['<div style="font-family:Arial,sans-serif;max-width:720px;margin:0 auto;color:#1f2937">']
        p.append('<h2 style="color:#2563eb;margin:0 0 4px">Ecommerce weekly scrape report</h2>')
        p.append('<p style="color:#6b7280;margin:0 0 18px;font-size:13px">%s%s</p>' % (
            ("Batch #%s" % e(str(self.batch_id))) if self.batch_id
            else ("Dry run" if self.dry_run else "No batch saved"),
            " — DRY RUN" if self.dry_run else ""))

        fails = self.failures()
        if fails:
            p.append('<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;'
                     'padding:14px 16px;margin-bottom:18px">')
            p.append('<div style="color:#b91c1c;font-weight:bold;font-size:15px;margin-bottom:8px">'
                     '⚠ %d failure(s) this run</div>' % len(fails))
            p.append('<ul style="margin:0;padding-left:20px;color:#7f1d1d;font-size:13px">')
            for name, reason in fails:
                p.append('<li><b>%s</b>: %s</li>' % (e(name), e(reason)))
            p.append('</ul></div>')
        else:
            p.append('<div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;'
                     'padding:12px 16px;margin-bottom:18px;color:#065f46;font-weight:bold">'
                     '✅ All scraping sources succeeded.</div>')

        p.append('<table style="border-collapse:collapse;width:100%;margin-bottom:18px;font-size:13px">')
        for label, val in [("Recommended", self.recommended),
                           ("Skipped (margin)", self.skipped),
                           ("Search keywords", self.keywords),
                           ("Scope", self.scope or "-")]:
            p.append('<tr><td style="padding:4px 8px;color:#6b7280">%s</td>'
                     '<td style="padding:4px 8px;font-weight:bold">%s</td></tr>' % (e(label), e(str(val))))
        p.append('</table>')

        p.append('<h3 style="margin:0 0 8px;font-size:15px">Scraping sources</h3>')
        p.append('<table style="border-collapse:collapse;width:100%;font-size:13px">')
        p.append('<tr style="background:#f3f4f6"><th style="text-align:left;padding:6px 8px">Source</th>'
                 '<th style="text-align:left;padding:6px 8px">Type</th>'
                 '<th style="text-align:left;padding:6px 8px">Result</th></tr>')
        for s in self.sources:
            colour = "#16a34a" if s["ok"] else "#dc2626"
            p.append('<tr style="border-top:1px solid #e5e7eb">'
                     '<td style="padding:6px 8px;font-weight:bold">%s</td>'
                     '<td style="padding:6px 8px;color:#6b7280">%s</td>'
                     '<td style="padding:6px 8px;color:%s">%s</td></tr>' % (
                         e(s["name"]), e(s["kind"]), colour, e(self._source_reason(s))))
        p.append('</table>')

        if self.batch_id and not self.dry_run:
            base = getattr(config, "APP_URL", "") or ""
            url = "%s/ecommerce/dashboard/%s" % (base, self.batch_id)
            p.append('<p style="margin:18px 0 0;font-size:13px">'
                     '<a href="%s">View batch on the dashboard →</a></p>' % e(url))

        p.append('</div>')
        return "".join(p)

    def send(self, to=None):
        to = to if to is not None else config.ECOMMERCE_EMAIL_TO
        return mailer.send_email(to, self.subject(), self.render_html())
