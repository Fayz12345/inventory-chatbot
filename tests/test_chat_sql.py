import pytest
from chat_sql import validate_sql, SqlValidationError


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
