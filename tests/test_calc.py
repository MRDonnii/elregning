"""Beregningerne alene (Claude AI, 2026-11-01)."""

from custom_components.elregning.calc import Measured, bill_ratio, compare_bill, forecast


def _bill(start="2026-10-01", end="2026-10-31", amount=1600.0, kwh=744.0, id_="a"):
    return {"id": id_, "start": start, "end": end, "amount": amount, "kwh": kwh}


def test_compare_bill_full_month():
    c = compare_bill(_bill(), Measured(kwh=740.0, cost=1500.0, days_with_data=31, days=31))
    assert c["days"] == 31 and c["complete"]
    assert c["difference"] == 100.0 and c["difference_pct"] == 6.7
    assert c["kwh_difference"] == 4.0 and c["kwh_difference_pct"] == 0.5
    assert c["bill_price"] == round(1600 / 744, 3) and c["measured_price"] == round(1500 / 740, 3)


def test_compare_bill_partial_coverage_is_not_complete():
    c = compare_bill(_bill(), Measured(kwh=300.0, cost=600.0, days_with_data=12, days=31))
    assert not c["complete"] and c["coverage"] == round(12 / 31, 3)


def test_compare_bill_without_measurement_or_kwh():
    c = compare_bill(_bill(kwh=None), Measured(kwh=None, cost=None, days_with_data=0, days=31))
    assert c["difference"] is None and c["kwh_difference"] is None and c["bill_price"] is None
    assert not c["complete"]


def test_ratio_uses_last_three_complete_bills():
    m = Measured(kwh=100.0, cost=1000.0, days_with_data=30, days=30)
    bills = [
        compare_bill(_bill("2026-06-01", "2026-06-30", 5000.0, id_="old"), m),  # for gammel, kommer ikke med
        compare_bill(_bill("2026-07-01", "2026-07-31", 1100.0, id_="b"), m),
        compare_bill(_bill("2026-08-01", "2026-08-31", 1000.0, id_="c"), m),
        compare_bill(_bill("2026-09-01", "2026-09-30", 900.0, id_="d"), m),
        compare_bill(
            _bill("2026-10-01", "2026-10-31", 9999.0, id_="partial"),
            Measured(kwh=10.0, cost=100.0, days_with_data=3, days=31),
        ),
    ]
    ratio, n = bill_ratio(bills)
    assert n == 3 and abs(ratio - 1.0) < 1e-9


def test_ratio_rejects_unreasonable_values():
    m = Measured(kwh=100.0, cost=100.0, days_with_data=31, days=31)
    assert bill_ratio([compare_bill(_bill(amount=1000.0), m)]) == (None, 0)


def test_forecast_with_and_without_ratio():
    f = forecast(500.0, 250.0, 50.0, 25.0, 10.0, 1.1)
    assert f == {"own_cost": 1000.0, "kwh": 500.0, "bill": 1100.0, "ratio": 1.1}
    assert forecast(500.0, 250.0, None, None, 10.0, None)["bill"] == 500.0


def test_yearly_totals_split_bill_over_new_year():
    from custom_components.elregning.calc import yearly_totals

    bills = [
        {"id": "a", "start": "2024-12-01", "end": "2025-01-31", "amount": 620.0, "kwh": 62.0},
        {"id": "b", "start": "2025-02-01", "end": "2025-02-28", "amount": 280.0, "kwh": 28.0},
        {"id": "g", "start": "2025-01-01", "end": "2025-03-31", "amount": 900.0, "m3": 90.0, "utility": "gas"},
    ]
    years = {(y["year"], y["utility"]): y for y in yearly_totals(bills)}
    assert years[(2024, "el")]["amount"] == 310.0 and years[(2024, "el")]["kwh"] == 31.0
    assert years[(2025, "el")]["amount"] == 590.0 and years[(2025, "el")]["price_kwh"] == 10.0
    assert years[(2025, "gas")]["m3"] == 90.0 and years[(2025, "gas")]["kwh"] is None
    assert years[(2025, "gas")]["price_m3"] == 10.0
    assert yearly_totals(bills)[0]["year"] == 2025
