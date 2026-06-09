"""GM calculator formula tests."""
from services.gm_insurance import parse_insurance_rows_from_xlsx
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAX_DIVISOR = 1.0672
MONTHLY_WORK_DAYS_2026 = 20.67
MONTHLY_HOURS_2026 = 165.36


def normalize_quote_to_monthly(quote_raw, quote_unit, monthly_hours=0):
    raw = float(quote_raw or 0)
    if raw <= 0:
        return 0.0
    if quote_unit == "day":
        return raw * MONTHLY_WORK_DAYS_2026
    if quote_unit == "hour":
        return raw * MONTHLY_HOURS_2026
    if quote_unit == "custom":
        hours = float(monthly_hours or 0)
        if hours <= 0:
            return 0.0
        return raw * hours
    return raw


def compute_custom_social_cost(base, rate_pct):
    return float(base or 0) * float(rate_pct or 0) / 100


def compute_custom_housing_cost(base, rate_pct):
    return float(base or 0) * float(rate_pct or 0) / 100


def resolve_insurance_costs(custom_insurance, social_base, social_rate, housing_base, housing_rate, location_rates):
    if custom_insurance:
        return (
            compute_custom_social_cost(social_base, social_rate),
            compute_custom_housing_cost(housing_base, housing_rate),
        )
    if not location_rates:
        return 0.0, 0.0
    return float(location_rates["social_insurance"]), float(location_rates["housing_fund"])


def resolve_annual_leave_days(raw):
    n = float(raw) if raw is not None else float("nan")
    if not (n == n and n == int(n) and 5 <= n <= 15):  # noqa: PLR2004
        return 5, True
    return int(n), False


def annual_leave(salary, days=5):
    if salary <= 0:
        return 0.0
    return salary / 21.75 * days / 12


def compute_effective_salary(salary, ratio_pct, discount_months, ratio_filled, months_filled):
    s = float(salary or 0)
    if s <= 0:
        return s
    if not ratio_filled or not months_filled:
        return s
    ratio = float(ratio_pct or 0)
    months = float(discount_months or 0)
    if ratio < 80 or ratio > 100:  # noqa: PLR2004
        return s
    if months != int(months) or months < 1 or months > 3:  # noqa: PLR2004
        return s
    months = int(months)
    return (s * (ratio / 100) * months + s * (12 - months)) / 12


def compute_gm(L, salary, bonus, social, housing, welfare=0, laptop=0, rec=0, cap=0, other=0,
               annual_leave_days=5, probation_ratio=None, probation_months=None):
    M = L / TAX_DIVISOR
    days, _invalid = resolve_annual_leave_days(annual_leave_days)
    leave = annual_leave(salary, days)
    ratio_filled = probation_ratio is not None and probation_ratio != ""
    months_filled = probation_months is not None and probation_months != ""
    effective = compute_effective_salary(salary, probation_ratio, probation_months, ratio_filled, months_filled)
    Y = effective + bonus + social + housing + leave + welfare + laptop + rec + cap + other
    Z = M - Y
    return M, Y, Z, Z / M if M else None, leave, effective


def test_annual_leave_formula():
    assert abs(annual_leave(20000) - 20000 / 21.75 * 5 / 12) < 0.02
    assert abs(annual_leave(15000) - 287.35632183908) < 0.02
    assert abs(annual_leave(20000, 10) - 20000 / 21.75 * 10 / 12) < 0.02


def test_annual_leave_invalid_falls_back_to_five_days():
    days, invalid = resolve_annual_leave_days(4)
    assert days == 5
    assert invalid is True
    assert abs(annual_leave(15000, days) - annual_leave(15000, 5)) < 0.001
    days, invalid = resolve_annual_leave_days(16)
    assert days == 5
    assert invalid is True


def test_effective_salary_probation():
    assert abs(compute_effective_salary(12000, 80, 2, True, True) - 11600) < 0.01


def test_effective_salary_partial_fill_uses_original():
    assert compute_effective_salary(12000, 80, None, True, False) == 12000
    assert compute_effective_salary(12000, None, 2, False, True) == 12000


def test_effective_salary_out_of_range_uses_original():
    assert compute_effective_salary(12000, 75, 2, True, True) == 12000
    assert compute_effective_salary(12000, 80, 4, True, True) == 12000


def test_effective_salary_full_ratio_no_discount():
    assert abs(compute_effective_salary(12000, 100, 3, True, True) - 12000) < 0.01


def test_tax_divisor_sample():
    L = 26500
    M, Y, Z, margin, leave, effective = compute_gm(L, 15000, 0, 1207, 120, 200, 0, 750, 530, 0)
    assert abs(M - L / TAX_DIVISOR) < 0.02
    assert abs(leave - annual_leave(15000)) < 0.02
    assert effective == 15000
    assert abs(Y - (17807 + leave)) < 1
    assert margin is not None
    assert 0.25 < margin < 0.30


def test_quote_month_no_conversion():
    assert normalize_quote_to_monthly(26500, "month") == 26500


def test_quote_day_conversion():
    assert abs(normalize_quote_to_monthly(1000, "day") - 20670) < 0.01


def test_quote_hour_conversion():
    assert abs(normalize_quote_to_monthly(100, "hour") - 100 * 165.36) < 0.01


def test_quote_custom_conversion():
    assert abs(normalize_quote_to_monthly(100, "custom", 160) - 16000) < 0.01


def test_quote_custom_missing_hours():
    assert normalize_quote_to_monthly(100, "custom", 0) == 0


def test_custom_social_cost():
    assert abs(compute_custom_social_cost(10000, 16.25) - 1625) < 0.01


def test_custom_housing_cost():
    assert abs(compute_custom_housing_cost(8000, 12) - 960) < 0.01


def test_custom_insurance_zero_when_disabled():
    loc = {"social_insurance": 1207, "housing_fund": 120}
    social, housing = resolve_insurance_costs(False, 10000, 16.25, 8000, 12, loc)
    assert social == 1207
    assert housing == 120


def test_custom_insurance_ignores_location_when_enabled():
    loc = {"social_insurance": 1207, "housing_fund": 120}
    social, housing = resolve_insurance_costs(True, 10000, 16.25, 8000, 12, loc)
    assert abs(social - 1625) < 0.01
    assert abs(housing - 960) < 0.01


def test_xlsx_parse_has_wuhan():
    path = os.path.join(BASE, "毛利测算表2026.xlsx")
    if not os.path.isfile(path):
        return
    rows = parse_insurance_rows_from_xlsx(path)
    locs = {r["location"]: r for r in rows}
    assert "武汉" in locs
    assert locs["武汉"]["social_insurance"] == 1207
