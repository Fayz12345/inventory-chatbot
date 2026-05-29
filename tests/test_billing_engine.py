import datetime
from billing import tms, schedule


def _count_items():
    out = []
    for section in schedule.TMS_FEE_SCHEDULE:
        for item in section["items"]:
            if item["mode"] == "count":
                out.append(item)
    return out


def test_build_select_one_alias_per_count_item_plus_repair():
    sql, params = tms._build_count_select(
        datetime.date(2026, 3, 1), datetime.date(2026, 4, 1)
    )
    n_count = len(_count_items())
    # one alias per count item ...
    for i in range(n_count):
        assert f"AS item_{i}" in sql
    # ... plus the repair-fee sum alias
    assert "AS repair_fee_sum" in sql
    assert "ReportingInventoryFlat_TMS" in sql
    assert "READ UNCOMMITTED" in sql


def test_build_select_params_are_balanced_with_placeholders():
    sql, params = tms._build_count_select(
        datetime.date(2026, 3, 1), datetime.date(2026, 4, 1)
    )
    assert sql.count("?") == len(params)


def test_build_select_uses_real_buyers_remorse_value():
    sql, params = tms._build_count_select(
        datetime.date(2026, 3, 1), datetime.date(2026, 4, 1)
    )
    assert "Buyers Remorse" in params
    assert "Buyer's Remorse" not in params
