"""Quote unit conversion and quote coefficient (报价系数) helpers."""
from __future__ import annotations

import re
from typing import Any, Dict

DEFAULT_MONTHLY_BILLABLE_DAYS = 20.67
DEFAULT_DAILY_BILLABLE_HOURS = 8.0

_QUOTE_UNIT_ALIASES = {
    "monthly": "monthly",
    "month": "monthly",
    "人月": "monthly",
    "daily": "daily",
    "day": "daily",
    "人天": "daily",
    "hourly": "hourly",
    "hour": "hourly",
    "人时": "hourly",
}


def strip_quote_amount(v: Any) -> str:
    return re.sub(r"[¥￥,\s\u00a0%]", "", str(v or "").strip())


def parse_quote_amount(v: Any) -> float:
    text = strip_quote_amount(v)
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_billing_number(v: Any, default: float) -> float:
    text = strip_quote_amount(v)
    if not text:
        return default
    try:
        n = float(text)
    except ValueError:
        return default
    return n if n > 0 else default


def normalize_quote_unit(unit: Any) -> str:
    raw = str(unit or "").strip()
    if not raw:
        return "monthly"
    key = raw.lower()
    if key in _QUOTE_UNIT_ALIASES:
        return _QUOTE_UNIT_ALIASES[key]
    return _QUOTE_UNIT_ALIASES.get(raw, "monthly")


def quote_unit_to_offer_tax_unit(unit: Any) -> str:
    normalized = normalize_quote_unit(unit)
    return {"monthly": "人月", "daily": "人天", "hourly": "人时"}.get(normalized, "人月")


def offer_tax_unit_to_quote_unit(unit: Any) -> str:
    return normalize_quote_unit(unit)


def format_quote_amount_storage(amount: float) -> str:
    if amount <= 0:
        return ""
    if abs(amount - round(amount)) < 1e-9:
        return str(int(round(amount)))
    text = f"{amount:.2f}".rstrip("0").rstrip(".")
    return text


def compute_monthly_quote_tax(
    quote_amount_tax: Any,
    quote_unit: Any = "monthly",
    monthly_billable_days: Any = DEFAULT_MONTHLY_BILLABLE_DAYS,
    daily_billable_hours: Any = DEFAULT_DAILY_BILLABLE_HOURS,
) -> str:
    raw = parse_quote_amount(quote_amount_tax)
    if raw <= 0:
        return ""
    unit = normalize_quote_unit(quote_unit)
    days = parse_billing_number(monthly_billable_days, DEFAULT_MONTHLY_BILLABLE_DAYS)
    hours = parse_billing_number(daily_billable_hours, DEFAULT_DAILY_BILLABLE_HOURS)
    if unit == "daily":
        monthly = raw * days
    elif unit == "hourly":
        monthly = raw * hours * days
    else:
        monthly = raw
    return format_quote_amount_storage(monthly)


def compute_quote_coefficient(monthly_quote_tax: Any, pre_tax_salary: Any) -> str:
    q = parse_quote_amount(monthly_quote_tax)
    p = parse_quote_amount(pre_tax_salary)
    if q <= 0 or p <= 0:
        return ""
    return f"{q / p:.2f}"


def ensure_quote_defaults(data: Dict[str, str]) -> None:
    """Backfill legacy rows: quote_unit=monthly, quote_amount_tax=monthly_quote_tax."""
    unit = str(data.get("quote_unit") or "").strip()
    if not unit:
        data["quote_unit"] = "monthly"
    else:
        data["quote_unit"] = normalize_quote_unit(unit)

    amount = str(data.get("quote_amount_tax") or "").strip()
    monthly = str(data.get("monthly_quote_tax") or "").strip()
    if not amount and monthly:
        data["quote_amount_tax"] = monthly
    if not str(data.get("monthly_billable_days") or "").strip():
        data["monthly_billable_days"] = str(DEFAULT_MONTHLY_BILLABLE_DAYS)
    if not str(data.get("daily_billable_hours") or "").strip():
        data["daily_billable_hours"] = str(int(DEFAULT_DAILY_BILLABLE_HOURS))


def apply_roster_quote_fields(data: Dict[str, str]) -> None:
    """Recompute monthly_quote_tax and quote coefficient from raw quote fields."""
    ensure_quote_defaults(data)
    data["monthly_quote_tax"] = compute_monthly_quote_tax(
        data.get("quote_amount_tax", ""),
        data.get("quote_unit", "monthly"),
        data.get("monthly_billable_days", DEFAULT_MONTHLY_BILLABLE_DAYS),
        data.get("daily_billable_hours", DEFAULT_DAILY_BILLABLE_HOURS),
    )
    coef = compute_quote_coefficient(data["monthly_quote_tax"], data.get("pre_tax_salary", ""))
    data["salary_quote_ratio"] = coef


def format_roster_salary_quote_ratio(monthly_quote_tax: str, pre_tax_salary: str) -> str:
    """Compatibility alias: returns quote coefficient."""
    return compute_quote_coefficient(monthly_quote_tax, pre_tax_salary)


def apply_offer_quote_fields(data: Dict[str, str]) -> None:
    """Offer form amount is raw quote_amount_tax; recompute monthly_quote_tax."""
    raw = str(data.get("quote_amount_tax") or data.get("monthly_quote_tax") or "").strip()
    data["quote_amount_tax"] = raw
    unit = data.get("quote_tax_unit") or data.get("quote_unit") or "人月"
    if not str(data.get("monthly_billable_days") or "").strip():
        data["monthly_billable_days"] = str(DEFAULT_MONTHLY_BILLABLE_DAYS)
    if not str(data.get("daily_billable_hours") or "").strip():
        data["daily_billable_hours"] = str(int(DEFAULT_DAILY_BILLABLE_HOURS))
    data["monthly_quote_tax"] = compute_monthly_quote_tax(
        raw,
        unit,
        data.get("monthly_billable_days"),
        data.get("daily_billable_hours"),
    )


def apply_roster_salary_quote_ratio(data: Dict[str, str]) -> None:
    apply_roster_quote_fields(data)
