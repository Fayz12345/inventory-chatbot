import os

import app as app_module
from ui.shell import page_shell

ROOT = os.path.dirname(os.path.abspath(app_module.__file__))


def test_page_shell_wires_loader_and_bumped_css():
    html = page_shell('<div>body</div>', title='T', active='analytics')
    assert '/static/js/nav-loading.js' in html
    assert 'app.css?v=11' in html


def test_base_template_wires_loader_and_bumped_css():
    with open(os.path.join(ROOT, 'templates', '_base.html')) as f:
        src = f.read()
    assert 'nav-loading.js' in src
    assert 'app.css?v=11' in src
    assert 'app.css?v=10' not in src


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
