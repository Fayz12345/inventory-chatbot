import roles


def test_matrix():
    assert roles.role_allows("admin", "billing") is True
    assert roles.role_allows("manager", "ecommerce") is True
    assert roles.role_allows("manager", "user_admin") is False
    assert roles.role_allows("viewer", "ecommerce") is False
    assert roles.role_allows("viewer", "chat") is True
    assert roles.role_allows("user", "ecommerce") is False   # legacy = viewer-like


def test_unknown_role_denied():
    assert roles.role_allows("nobody", "chat") is False


# ---------------------------------------------------------------------------
# RBAC gate regression tests — guards against fail-open on ecommerce blueprint
# ---------------------------------------------------------------------------

def _make_client():
    from app import chatbot_app
    chatbot_app.config['TESTING'] = True
    chatbot_app.config['WTF_CSRF_ENABLED'] = False
    return chatbot_app.test_client()


def test_viewer_cannot_access_ecommerce_dashboard():
    """viewer role is NOT in the ecommerce allow-list → must redirect to /home."""
    client = _make_client()
    with client.session_transaction() as s:
        s['logged_in'] = True
        s['role'] = 'viewer'
    resp = client.get('/ecommerce/dashboard')
    assert resp.status_code == 302
    location = resp.headers.get('Location', '')
    assert '/home' in location


def test_no_role_key_cannot_access_ecommerce_dashboard():
    """Session with no 'role' key defaults to 'user' → also blocked from ecommerce.

    This is the exact fail-open regression guard: if the gate mistakenly
    skipped missing-role sessions, this test would catch it.
    """
    client = _make_client()
    with client.session_transaction() as s:
        s['logged_in'] = True
        # Deliberately omit 'role' key — defaults to 'user' inside the gate
    resp = client.get('/ecommerce/dashboard')
    assert resp.status_code == 302
    location = resp.headers.get('Location', '')
    assert '/home' in location


def test_admin_can_access_ecommerce_dashboard():
    """admin role IS allowed ecommerce — gate must not redirect to /home."""
    client = _make_client()
    with client.session_transaction() as s:
        s['logged_in'] = True
        s['role'] = 'admin'
        s['is_admin'] = True
    resp = client.get('/ecommerce/dashboard')
    assert resp.status_code != 302 or '/home' not in resp.headers.get('Location', '')
