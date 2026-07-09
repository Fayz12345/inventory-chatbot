import re
import app
from chat_sql import validate_sql


def test_prompt_declares_tsql_and_top():
    p = app.SYSTEM_PROMPT.upper()
    assert "T-SQL" in p or "SQL SERVER" in p
    assert "TOP" in p and "LIMIT" in p          # instructs TOP, forbids LIMIT


def test_prompt_flags_nvarchar_date_columns():
    assert "Function_Test_Created" in app.SYSTEM_PROMPT
    assert "nvarchar" in app.SYSTEM_PROMPT.lower()


def test_fewshot_examples_are_valid_allowed_sql():
    # Extract SQL after each "SQL:" label in the examples block and validate it.
    examples = re.findall(r"SQL:\s*(SELECT[^\n]+)", app.SYSTEM_PROMPT)
    assert len(examples) >= 4
    for sql in examples:
        validate_sql(sql)   # raises if any example is unsafe/malformed
