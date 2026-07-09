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
