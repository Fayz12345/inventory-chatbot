"""Role -> module permission matrix. `is_admin` remains the source of truth for
the user-admin area; this adds coarse module gating for non-admins."""
MODULES = ["chat", "ecommerce", "analytics", "billing", "user_admin"]
ROLES = ["admin", "manager", "viewer", "user"]

_MATRIX = {
    "admin":   {"chat", "ecommerce", "analytics", "billing", "user_admin"},
    "manager": {"chat", "ecommerce", "analytics", "billing"},
    "viewer":  {"chat", "analytics"},
    "user":    {"chat", "analytics"},   # legacy default
}


def role_allows(role, module):
    return module in _MATRIX.get(role, set())


def effective_role(role, is_admin):
    """Resolve a session's effective role. Falls back to the legacy `is_admin`
    flag when no `role` is set — so sessions created before roles existed (and
    any is_admin account) keep full access instead of being demoted to 'user'.
    Still fail-safe: a non-admin session with no role resolves to 'user'."""
    return role or ('admin' if is_admin else 'user')
