"""Shared page chrome for the Python-embedded templates (analytics, ecommerce,
billing) that can't extend the Jinja `_base.html`.

Built as PLAIN string concatenation — never `.format()`/`%`/Jinja — so the
embedded CSS link and any literal `{ }` in the wrapped body never need escaping.
`page_shell()` supplies the same <head> (app.css) + top nav as the Jinja base,
so every surface shares one look. The wrapped body fragment keeps its own
markup, `{{ }}`/`{name}` expressions, ids, classes, and inline <script> intact.
"""

from flask import has_request_context, session
from markupsafe import escape

import roles

_CSS_VERSION = "14"


def _nav_link(href, label, active, key):
    cls = ' class="active"' if active == key else ""
    return '<a href="%s"%s>%s</a>' % (escape(href), cls, escape(label))


def _topnav(active=None):
    # Gate exactly like templates/_topnav.html so the tab set is identical on
    # every surface (this shell renders the ecommerce/analytics/billing pages;
    # the Jinja base renders home/chat/admin). Module tabs by role perms; the
    # admin area (Users/Audit) by is_admin. Previously this showed ALL module
    # tabs ungated and omitted Audit, so the nav changed per page (security bug).
    username = session.get("username") if has_request_context() else None
    is_admin = session.get("is_admin") if has_request_context() else False
    role = roles.effective_role(
        session.get("role") if has_request_context() else None, is_admin)
    links = []
    if roles.role_allows(role, "chat"):
        links.append(_nav_link("/chat", "Chatbot", active, "chat"))
    if roles.role_allows(role, "ecommerce"):
        links.append(_nav_link("/ecommerce/dashboard", "Ecommerce", active, "ecommerce"))
    if roles.role_allows(role, "analytics"):
        links.append(_nav_link("/analytics/", "Analytics", active, "analytics"))
    if roles.role_allows(role, "billing"):
        links.append(_nav_link("/billing/", "Billing", active, "billing"))
    if is_admin:
        links.append(_nav_link("/admin/users", "Users", active, "admin"))
        links.append(_nav_link("/admin/audit", "Audit", active, "audit"))
    who = ('<span class="who">%s</span>' % escape(username)) if username else ""
    return (
        '<header class="app-header">'
        '<a class="app-header__brand" href="/chat"><span class="dot"></span> Bridge Platform</a>'
        '<nav class="app-nav">' + "".join(links) + "</nav>"
        '<div class="app-header__right">' + who + '<a href="/logout">Sign out</a></div>'
        "</header>"
    )


def page_shell(body_html, title="Bridge Platform", active=None, back=None):
    """Wrap an already-rendered body fragment in the shared head + top nav.

    body_html : str  — the page body (the old template minus its <html>/<head>/header).
    title     : str  — <title>.
    active    : str  — nav key to highlight ('ecommerce' | 'analytics' | ...).
    back      : (href, label) | None — optional back link rendered above the body.
    """
    back_html = ""
    if back:
        back_html = (
            '<div style="max-width:1240px;margin:0 auto;padding:18px 24px 0">'
            '<a class="back" href="%s">&larr; %s</a></div>' % (escape(back[0]), escape(back[1]))
        )
    return (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>" + str(escape(title)) + "</title>"
        '<link rel="stylesheet" href="/static/css/app.css?v=' + _CSS_VERSION + '">'
        "</head><body>"
        + _topnav(active)
        + back_html
        + body_html
        + '<script src="/static/js/nav-loading.js?v=1"></script>'
        + "</body></html>"
    )
