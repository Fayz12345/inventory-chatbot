import pytest
from chat_sql import validate_sql, SqlValidationError, build_count_query


def test_plain_select_passes():
    out = validate_sql("SELECT COUNT(*) FROM ReportingInventoryFlat")
    assert "ReportingInventoryFlat" in out


def test_cte_select_passes():
    sql = ("WITH x AS (SELECT Manufacturer FROM ReportingInventoryFlat) "
           "SELECT * FROM x")
    assert validate_sql(sql)  # CTE alias 'x' must not trip the table allowlist


def test_strips_markdown_fences():
    assert validate_sql("```sql\nSELECT 1 FROM ReportingInventoryFlat\n```")


@pytest.mark.parametrize("bad", [
    "INSERT INTO ReportingInventoryFlat (ESN) VALUES ('x')",
    "UPDATE ReportingInventoryFlat SET Grade='A'",
    "DELETE FROM ReportingInventoryFlat",
    "DROP TABLE ReportingInventoryFlat",
    "SELECT 1 FROM ReportingInventoryFlat; DROP TABLE ReportingInventoryFlat",  # batched
    "SELECT * FROM users",                       # other table
    "SELECT name FROM sys.tables",               # catalog
    "SELECT * FROM ReportingInventoryFlat WAITFOR DELAY '00:00:10'",  # command
    "SELECT * INTO copy FROM ReportingInventoryFlat",  # SELECT INTO writes
])
def test_dangerous_sql_rejected(bad):
    with pytest.raises(SqlValidationError):
        validate_sql(bad)


def test_false_positive_value_containing_keyword_is_allowed():
    # old substring blocklist wrongly rejected this; allowlist must accept it
    assert validate_sql(
        "SELECT * FROM ReportingInventoryFlat WHERE Model LIKE '%Update%'")


# --- qualifier bypass tests ---

@pytest.mark.parametrize("bad", [
    "SELECT * FROM OtherDB.dbo.ReportingInventoryFlat",   # cross-database catalog qualifier
    "SELECT * FROM secretschema.ReportingInventoryFlat",  # non-dbo schema qualifier
    "WITH tables AS (SELECT 1 x) SELECT name FROM sys.tables",  # sys catalog view
])
def test_qualifier_bypass_rejected(bad):
    with pytest.raises(SqlValidationError):
        validate_sql(bad)


def test_dbo_qualified_ref_accepted():
    # dbo.Table is a legitimate and common pattern; must not be over-rejected
    out = validate_sql("SELECT ESN FROM dbo.ReportingInventoryFlat")
    assert "ReportingInventoryFlat" in out


# --- ecommerce tables now allowed (Tier 1) ---

@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM EcommerceListingsLog WHERE Manufacturer LIKE '%Samsung%'",
    "SELECT Platform, COUNT(*) AS c FROM EcommerceListingsLog GROUP BY Platform",
    "SELECT COUNT(*) FROM EcommercePricingRecommendation WHERE Decision IS NULL",
    "SELECT TOP 10 Model, RecommendedPrice FROM EcommercePricingRecommendation",
    # recommendation joined to its batch — the one allowed cross-table join
    "SELECT r.Model, b.CreatedAt FROM EcommercePricingRecommendation r "
    "JOIN EcommercePricingBatch b ON r.BatchID = b.ID",
])
def test_ecommerce_tables_allowed(sql):
    assert validate_sql(sql)


@pytest.mark.parametrize("bad", [
    "SELECT * FROM OrderHeader",                     # sales/orders — not exposed (Tier 2)
    "SELECT * FROM OrderDetail",
    "SELECT COUNT(*) FROM EcommerceProductCatalog",  # exists but intentionally not exposed
])
def test_non_exposed_tables_rejected(bad):
    with pytest.raises(SqlValidationError):
        validate_sql(bad)


def test_build_count_query_wraps_and_strips_order_by():
    out = build_count_query(
        "SELECT ESN FROM ReportingInventoryFlat ORDER BY ReceiveDate")
    assert out.upper().startswith("SELECT COUNT(")
    assert "ORDER BY" not in out.upper()      # illegal inside the COUNT subquery
    assert "ReportingInventoryFlat" in out
