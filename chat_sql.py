"""SQL guardrails for the text-to-SQL chat feature.

validate_sql replaces the old substring blocklist in app.run_query with an
AST allowlist: exactly one read-only SELECT (CTEs allowed) that references only
approved tables. build_count_query supports honest result truncation (#5).
"""
import re
import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"reportinginventoryflat"}  # lowercase names

# Statement/expression types that must never appear. exp.Command catches
# constructs sqlglot doesn't model as structured DML (e.g. WAITFOR, EXEC).
_FORBIDDEN = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter,
              exp.Create, exp.Merge, exp.Command, exp.Into)

_FENCE_RE = re.compile(r"^```(?:sql)?|```$", re.IGNORECASE)


class SqlValidationError(Exception):
    """Generated SQL is not a safe single read-only SELECT."""


def _clean(sql):
    s = (sql or "").strip()
    if s.startswith("```"):
        s = _FENCE_RE.sub("", s).strip()
    return s.rstrip(";").strip()


def validate_sql(sql, allowed_tables=ALLOWED_TABLES):
    cleaned = _clean(sql)
    if not cleaned:
        raise SqlValidationError("Empty query.")
    try:
        statements = [s for s in sqlglot.parse(cleaned, dialect="tsql") if s]
    except Exception as e:  # sqlglot ParseError
        raise SqlValidationError(f"Could not parse SQL: {e}")
    if len(statements) != 1:
        raise SqlValidationError("Only a single statement is allowed.")
    stmt = statements[0]
    if not isinstance(stmt, exp.Select):
        raise SqlValidationError("Only SELECT queries are allowed.")
    if any(True for _ in stmt.find_all(*_FORBIDDEN)):
        raise SqlValidationError("Only read-only SELECT queries are allowed.")
    cte_names = {c.alias_or_name.lower() for c in stmt.find_all(exp.CTE)}
    allowed = {t.lower() for t in allowed_tables} | cte_names
    for table in stmt.find_all(exp.Table):
        if (table.name or "").lower() not in allowed:
            raise SqlValidationError(f"Querying '{table.name}' is not allowed.")
    return stmt.sql(dialect="tsql")
