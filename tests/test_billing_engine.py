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
    # ... plus the repair-fee sum and count aliases
    assert "AS repair_fee_sum" in sql
    assert "AS repair_count" in sql
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


def test_assemble_report_computes_charges_and_totals():
    # Fake aggregate row: every count item = 2 units, repair sum = 100.0
    n = len(_count_items())
    raw = {f"item_{i}": 2 for i in range(n)}
    raw["repair_fee_sum"] = 100.0
    raw["repair_count"] = 4

    report = tms._assemble_report(raw, datetime.date(2026, 3, 1))

    assert report["period_label"] == "March 2026"
    # find a known count line and check charge = units * fee
    inwarranty = _section(report, "In Warranty Rx")
    receive = [li for li in inwarranty["line_items"] if li["label"] == "Receive"][0]
    assert receive["units"] == 2
    assert receive["fee"] == 2.75
    assert round(receive["charge"], 2) == 5.50

    # repair line: charge = sum of Repair_Fee, units = device count
    oow = _section(report, "Out of Warranty")
    repair = oow["line_items"][0]
    assert round(repair["charge"], 2) == 100.0
    assert repair["units"] == 4

    # manual items come back with units None and charge 0
    acc = _section(report, "Accessories")["line_items"][0]
    assert acc["units"] is None
    assert acc["charge"] == 0
    assert acc["mode"] == "manual"

    # grand_total_auto = sum of all non-manual charges
    expected_auto = 0.0
    for section in report["sections"]:
        for li in section["line_items"]:
            if li["mode"] != "manual":
                expected_auto += li["charge"]
    assert round(report["grand_total_auto"], 2) == round(expected_auto, 2)


def _section(report, name):
    for s in report["sections"]:
        if s["name"] == name:
            return s
    raise AssertionError(f"section not found: {name}")


class _FakeCursor:
    def __init__(self, row, description):
        self._row = row
        self.description = description
    def execute(self, sql, params=None):
        return self
    def fetchone(self):
        return self._row
    def close(self):
        pass


class _FakeConn:
    def __init__(self, row, description):
        self._row = row
        self._description = description
    def cursor(self):
        return _FakeCursor(self._row, self._description)
    def close(self):
        pass


def test_generate_report_maps_row_by_alias():
    n = len(_count_items())
    aliases = [f"item_{i}" for i in range(n)] + ["repair_fee_sum", "repair_count"]
    row = tuple([3] * n + [50.0, 2])
    description = [(a,) for a in aliases]
    conn = _FakeConn(row, description)

    report = tms.generate_report(2026, 3, conn_factory=lambda: conn)

    assert report["period_label"] == "March 2026"
    inwarranty = _section(report, "In Warranty Rx")
    receive = [li for li in inwarranty["line_items"] if li["label"] == "Receive"][0]
    assert receive["units"] == 3
    assert round(receive["charge"], 2) == round(3 * 2.75, 2)
    oow = _section(report, "Out of Warranty")
    assert round(oow["line_items"][0]["charge"], 2) == 50.0
