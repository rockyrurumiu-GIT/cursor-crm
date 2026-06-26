"""Quote coefficient and monthly quote conversion tests."""
from services.quote_finance import (
    apply_offer_quote_fields,
    apply_roster_quote_fields,
    compute_monthly_quote_tax,
    compute_quote_coefficient,
    ensure_quote_defaults,
)


def test_month_quote_coefficient():
    assert compute_quote_coefficient("26000", "18000") == "1.44"


def test_day_quote_coefficient():
    monthly = compute_monthly_quote_tax("1000", "daily")
    assert monthly == "20670"
    assert compute_quote_coefficient(monthly, "16000") == "1.29"


def test_hour_quote_coefficient():
    monthly = compute_monthly_quote_tax("120", "hourly")
    assert monthly == "19843.2"
    assert compute_quote_coefficient(monthly, "16000") == "1.24"


def test_empty_salary_returns_empty():
    assert compute_quote_coefficient("26000", "") == ""
    assert compute_quote_coefficient("26000", "0") == ""


def test_roster_apply_preserves_raw_quote():
    data = {
        "quote_unit": "daily",
        "quote_amount_tax": "1000",
        "monthly_billable_days": "20.67",
        "daily_billable_hours": "8",
        "pre_tax_salary": "16000",
    }
    apply_roster_quote_fields(data)
    assert data["quote_amount_tax"] == "1000"
    assert data["quote_unit"] == "daily"
    assert data["monthly_quote_tax"] == "20670"
    assert data["salary_quote_ratio"] == "1.29"


def test_legacy_backfill_monthly_only():
    data = {"monthly_quote_tax": "26000", "pre_tax_salary": "18000"}
    ensure_quote_defaults(data)
    apply_roster_quote_fields(data)
    assert data["quote_unit"] == "monthly"
    assert data["quote_amount_tax"] == "26000"
    assert data["salary_quote_ratio"] == "1.44"


def test_offer_apply_converts_day_quote():
    data = {
        "quote_tax_unit": "人天",
        "monthly_quote_tax": "1000",
        "pre_tax_salary": "16000",
    }
    apply_offer_quote_fields(data)
    assert data["quote_amount_tax"] == "1000"
    assert data["monthly_quote_tax"] == "20670"
