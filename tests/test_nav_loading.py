import os

import app as app_module
from ui import shell
from ui.shell import page_shell

ROOT = os.path.dirname(os.path.abspath(app_module.__file__))


def _shell_nav(role, is_admin):
    """Render just the shell top-nav (ecommerce/analytics/billing pages) for a
    given session role, inside a request context."""
    with app_module.chatbot_app.test_request_context('/'):
        from flask import session
        session['username'] = 'tester'
        session['role'] = role
        session['is_admin'] = is_admin
        return shell._topnav()


def test_shell_nav_admin_sees_every_tab_including_audit():
    # Regression: the shell nav omitted Audit and showed all module tabs ungated,
    # so an admin's tab set differed from the Jinja pages (security bug).
    html = _shell_nav('admin', True)
    for path in ('/chat', '/ecommerce/dashboard', '/analytics/',
                 '/billing/', '/admin/users', '/admin/audit'):
        assert path in html, "admin shell nav missing " + path
    # Home was retired from the nav (its workspace cards are now the tabs); the
    # brand links to /chat, so /home must not appear anywhere in the shell nav.
    assert '/home' not in html, "Home link should be removed from the nav"


def test_shell_nav_user_sees_only_chat_and_analytics():
    html = _shell_nav('user', False)
    assert '/chat' in html and '/analytics/' in html
    for path in ('/ecommerce/dashboard', '/billing/', '/admin/users', '/admin/audit'):
        assert path not in html, "user shell nav must not include " + path


def test_shell_nav_viewer_matches_user_module_gating():
    html = _shell_nav('viewer', False)
    assert '/chat' in html and '/analytics/' in html
    assert '/ecommerce/dashboard' not in html and '/billing/' not in html


def test_shell_nav_is_admin_without_role_still_full_access():
    # A legacy is_admin session with no `role` must resolve to admin (not 'user').
    html = _shell_nav(None, True)
    assert '/admin/audit' in html and '/ecommerce/dashboard' in html


def test_page_shell_wires_loader_and_bumped_css():
    html = page_shell('<div>body</div>', title='T', active='analytics')
    assert '/static/js/nav-loading.js' in html
    assert 'app.css?v=14' in html


def test_base_template_wires_loader_and_bumped_css():
    with open(os.path.join(ROOT, 'templates', '_base.html')) as f:
        src = f.read()
    assert 'nav-loading.js' in src
    assert 'app.css?v=16' in src
    assert 'app.css?v=15' not in src


def test_nav_loading_js_has_safety_guards():
    with open(os.path.join(ROOT, 'static', 'js', 'nav-loading.js')) as f:
        src = f.read()
    assert 'route-loader' in src
    assert 'defaultPrevented' in src          # AJAX / preventDefault skip
    assert "hasAttribute('download')" in src  # download links skipped
    assert 'data-no-loading' in src           # opt-out hook
    assert 'pageshow' in src                   # bfcache hide


def test_css_has_route_loader_rules():
    with open(os.path.join(ROOT, 'static', 'css', 'app.css')) as f:
        css = f.read()
    assert '.route-loader' in css
    assert '.route-loader.active' in css


def test_telus_export_form_opted_out():
    with open(os.path.join(ROOT, 'analytics', 'templates.py')) as f:
        src = f.read()
    assert '/analytics/telus-weekly/export' in src
    # the export form (download) must carry the opt-out attribute
    assert 'data-no-loading' in src
