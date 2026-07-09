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
