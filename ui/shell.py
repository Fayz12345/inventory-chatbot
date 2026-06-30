"""Shared page chrome for the Python-embedded templates (analytics, ecommerce,
billing) that can't extend the Jinja `_base.html`.

Built as PLAIN string concatenation — never `.format()`/`%`/Jinja — so the
embedded CSS link and any literal `{ }` in the wrapped body never need escaping.
`page_shell()` supplies the same <head> (app.css) + top nav as the Jinja base,
so every surface shares one look. The wrapped body fragment keeps its own
markup, `{{ }}`/`{name}` expressions, ids, classes, and inline <script> intact.
"""

from flask import has_request_context, session

_CSS_VERSION = "1"


def _nav_link(href, label, active, key):
    cls = ' class="active"' if active == key else ""
    return '<a href="%s"%s>%s</a>' % (href, cls, label)


def _topnav(active=None):
    username = session.get("username") if has_request_context() else None
    is_admin = session.get("is_admin") if has_request_context() else False
    links = [
        _nav_link("/home", "Home", active, "home"),
        _nav_link("/chat", "Chatbot", active, "chat"),
        _nav_link("/ecommerce/dashboard", "Ecommerce", active, "ecommerce"),
        _nav_link("/analytics/", "Analytics", active, "analytics"),
    ]
    if is_admin:
        links.append(_nav_link("/admin/users", "Users", active, "admin"))
    who = ('<span class="who">%s</span>' % username) if username else ""
    return (
        '<header class="app-header">'
        '<a class="app-header__brand" href="/home"><span class="dot"></span> Bridge Platform</a>'
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
            '<a class="back" href="%s">&larr; %s</a></div>' % (back[0], back[1])
        )
    return (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>" + title + "</title>"
        '<link rel="stylesheet" href="/static/css/app.css?v=' + _CSS_VERSION + '">'
        "</head><body>"
        + _topnav(active)
        + back_html
        + body_html
        + "</body></html>"
    )
