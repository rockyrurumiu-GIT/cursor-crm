"""GM calculator formula tests."""
from services.gm_insurance import parse_insurance_rows_from_xlsx
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAX_DIVISOR = 1.0672


def annual_leave(salary):
    if salary <= 0:
        return 0.0
    return salary / 21.75 * 5 / 12


def compute_gm(L, salary, bonus, social, housing, welfare=0, laptop=0, rec=0, cap=0, other=0):
    M = L / TAX_DIVISOR
    leave = annual_leave(salary)
    Y = salary + bonus + social + housing + leave + welfare + laptop + rec + cap + other
    Z = M - Y
    return M, Y, Z, Z / M if M else None, leave


def test_annual_leave_formula():
    assert abs(annual_leave(20000) - 20000 / 21.75 * 5 / 12) < 0.02
    assert abs(annual_leave(15000) - 287.35632183908) < 0.02


def test_tax_divisor_sample():
    L = 26500
    M, Y, Z, margin, leave = compute_gm(L, 15000, 0, 1207, 120, 200, 0, 750, 530, 0)
    assert abs(M - L / TAX_DIVISOR) < 0.02
    assert abs(leave - annual_leave(15000)) < 0.02
    assert abs(Y - (17807 + leave)) < 1
    assert margin is not None
    assert 0.25 < margin < 0.30


def test_xlsx_parse_has_wuhan():
    path = os.path.join(BASE, "毛利测算表2026.xlsx")
    if not os.path.isfile(path):
        return
    rows = parse_insurance_rows_from_xlsx(path)
    locs = {r["location"]: r for r in rows}
    assert "武汉" in locs
    assert locs["武汉"]["social_insurance"] == 1207
