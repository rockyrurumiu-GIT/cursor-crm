"""Delivery Roster business logic — migrated from main.py (Phase 5A)."""
from __future__ import annotations

import csv
import io
import os
import re
import unicodedata
from calendar import monthrange
from collections import Counter
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

from fastapi import HTTPException
from sqlalchemy import and_, not_, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import data_scope as ds
from auth.data_scope_catalog import RESOURCE_DELIVERY_ROSTER
from auth.service import AuthContext
from services.csv_utils import strip_csv_header_noise as _strip_csv_header_noise
from schemas.delivery_roster import (
    CHINESE_ROSTER_HEADER_MAP,
    ROSTER_CUSTOMER_ALIAS_RULES,
    ROSTER_EXPORT_HEADERS,
    ROSTER_FIELD_KEYS,
    ZNTX_ROSTER_EXPORT_HEADERS,
)
from services.date_utils import parse_loose_date
from services.quote_finance import (
    apply_roster_quote_fields,
    apply_roster_salary_quote_ratio,
    ensure_quote_defaults,
    format_roster_salary_quote_ratio,
    strip_quote_amount as roster_strip_amount_for_ratio,
)


# ---------------------------------------------------------------------------
# SQL filter expressions
# ---------------------------------------------------------------------------

def sql_roster_employment_left(RosterEntry: Type) -> Any:
    """在职情况含「离职」即归入离职档案池。"""
    return RosterEntry.employment_status.like("%离职%")


def sql_roster_employment_active_pool(RosterEntry: Type) -> Any:
    """花名册在职池：空/未填视为在岗；含「离职」则不在花名册中展示。"""
    col = RosterEntry.employment_status
    return or_(col.is_(None), col == "", not_(col.like("%离职%")))


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def roster_entries_union_of_all_clients(
    db: Session, ctx: Optional[AuthContext], RosterEntry: Type, Client: Type
) -> list:
    """整体花名册（在职池）：各客户已关联行，且不含离职档案。"""
    q = (
        db.query(RosterEntry)
        .join(Client, RosterEntry.client_id == Client.id)
        .filter(sql_roster_employment_active_pool(RosterEntry))
    )
    if ctx is not None:
        q = ds.filter_query_by_client_scope(
            q, db, ctx, RESOURCE_DELIVERY_ROSTER, "read", RosterEntry.client_id, Client
        )
    return q.order_by(RosterEntry.id).all()


def roster_entries_turnover_pool(
    db: Session, RosterEntry: Type, Client: Type, ctx: Optional[AuthContext] = None
) -> list:
    """离职率分析：全部为离职档案行。"""
    q = db.query(RosterEntry).filter(sql_roster_employment_left(RosterEntry))
    if ctx is not None:
        q = ds.filter_query_by_client_scope(
            q, db, ctx, RESOURCE_DELIVERY_ROSTER, "read", RosterEntry.client_id, Client
        )
    return q.order_by(RosterEntry.id).all()


# ---------------------------------------------------------------------------
# Throme staff number (索摩工号)
# ---------------------------------------------------------------------------

_THROME_STAFF_NO_CONFLICT_DETAIL = "索摩工号生成冲突，请重试"


def generate_throme_staff_no(db: Session) -> str:
    """Allocate next company-wide staff number: A1{0001}, A1{0002}, ..."""
    row = db.execute(
        text("SELECT next_value FROM roster_throme_staff_no_sequence WHERE id = 1")
    ).fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="索摩工号序列表未初始化")
    next_value = int(row[0])
    staff_no = f"A1{next_value:04d}"
    db.execute(
        text("UPDATE roster_throme_staff_no_sequence SET next_value = :nv WHERE id = 1"),
        {"nv": next_value + 1},
    )
    return staff_no


def force_generate_throme_staff_no(db: Session, data: Dict[str, str]) -> None:
    data.pop("throme_staff_no", None)
    data["throme_staff_no"] = generate_throme_staff_no(db)


def ensure_throme_staff_no(db: Session, data: Dict[str, str]) -> None:
    if not str(data.get("throme_staff_no", "")).strip():
        data["throme_staff_no"] = generate_throme_staff_no(db)


def strip_immutable_roster_fields_on_update(data: Dict[str, str]) -> None:
    data.pop("throme_staff_no", None)


def add_roster_entry(
    db: Session,
    client_id: int,
    data: Dict[str, str],
    RosterEntry: Type[Any],
    *,
    preserve_throme_staff_no: bool = False,
) -> Any:
    """Insert roster row with throme_staff_no; retry once on unique-index conflict."""
    merged = dict(data)
    if preserve_throme_staff_no:
        ensure_throme_staff_no(db, merged)
    else:
        force_generate_throme_staff_no(db, merged)
    last_err: Optional[Exception] = None
    for _ in range(2):
        sp = db.begin_nested()
        try:
            entry = RosterEntry(client_id=client_id, **merged)
            db.add(entry)
            db.flush()
            sp.commit()
            return entry
        except IntegrityError as exc:
            sp.rollback()
            last_err = exc
            if preserve_throme_staff_no:
                raise HTTPException(
                    status_code=409, detail=_THROME_STAFF_NO_CONFLICT_DETAIL
                ) from exc
            force_generate_throme_staff_no(db, merged)
    raise HTTPException(
        status_code=409, detail=_THROME_STAFF_NO_CONFLICT_DETAIL
    ) from last_err


# ---------------------------------------------------------------------------
# Serialization / normalization
# ---------------------------------------------------------------------------

def roster_entry_to_dict(e: Any) -> dict:
    row = {
        "id": e.id,
        "client_id": e.client_id,
        "serial_no": e.serial_no or "",
        "employment_status": e.employment_status or "",
        "full_name": e.full_name or "",
        "contact_info": e.contact_info or "",
        "customer_name": e.customer_name or "",
        "work_location": e.work_location or "",
        "position_title": e.position_title or "",
        "business_line": e.business_line or "",
        "entry_date": e.entry_date or "",
        "regularization_status": e.regularization_status or "",
        "throme_staff_no": e.throme_staff_no or "",
        "regularization_date": e.regularization_date or "",
        "quote_unit": getattr(e, "quote_unit", None) or "monthly",
        "quote_amount_tax": getattr(e, "quote_amount_tax", None) or "",
        "monthly_billable_days": getattr(e, "monthly_billable_days", None) or "20.67",
        "daily_billable_hours": getattr(e, "daily_billable_hours", None) or "8",
        "monthly_quote_tax": e.monthly_quote_tax or "",
        "pre_tax_salary": e.pre_tax_salary or "",
        "gms": e.gms or "",
        "gm_pct": e.gm_pct or "",
        "employee_plus1": e.employee_plus1 or "",
        "zntx_onboarding_channel": e.zntx_onboarding_channel or "",
        "zntx_attendance_checkin": e.zntx_attendance_checkin or "",
        "zntx_attendance_makeup": e.zntx_attendance_makeup or "",
        "employee_plus2": e.employee_plus2 or "",
        "interface_contact": e.interface_contact or "",
        "project_release_date": e.project_release_date or "",
        "company_resign_date": e.company_resign_date or "",
        "zntx_staff_no": e.zntx_staff_no or "",
        "zntx_separation_type": e.zntx_separation_type or "",
        "zntx_compensation_amount": e.zntx_compensation_amount or "",
        "delivery_communication": e.delivery_communication or "",
        "business_action": e.business_action or "",
        "bp_involved": e.bp_involved or "",
        "leave_reason": e.leave_reason or "",
        "remarks": e.remarks or "",
    }
    ensure_quote_defaults(row)
    apply_roster_quote_fields(row)
    coef = row.get("salary_quote_ratio", "")
    row["quote_coefficient"] = coef
    return row


def normalize_roster_payload(d: Dict[str, Any]) -> Dict[str, str]:
    keys = [
        "serial_no",
        "employment_status",
        "full_name",
        "contact_info",
        "customer_name",
        "work_location",
        "position_title",
        "business_line",
        "entry_date",
        "regularization_status",
        "throme_staff_no",
        "regularization_date",
        "quote_unit",
        "quote_amount_tax",
        "monthly_billable_days",
        "daily_billable_hours",
        "monthly_quote_tax",
        "pre_tax_salary",
        "salary_quote_ratio",
        "gms",
        "gm_pct",
        "employee_plus1",
        "zntx_onboarding_channel",
        "zntx_attendance_checkin",
        "zntx_attendance_makeup",
        "employee_plus2",
        "interface_contact",
        "project_release_date",
        "company_resign_date",
        "zntx_staff_no",
        "zntx_separation_type",
        "zntx_compensation_amount",
        "delivery_communication",
        "business_action",
        "bp_involved",
        "leave_reason",
        "remarks",
    ]
    out: Dict[str, str] = {}
    for k in keys:
        v = d.get(k, "")
        if v is None:
            v = ""
        out[k] = str(v).strip()
    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_roster_business_fields(data: Dict[str, str]) -> None:
    def _normalize_amount_text(v: str) -> str:
        return re.sub(r"[¥￥,\s\u00a0]", "", str(v or "").strip())

    ensure_quote_defaults(data)

    contact = str(data.get("contact_info", "")).strip()
    if contact and not re.fullmatch(r"\d{11}", contact):
        raise HTTPException(status_code=400, detail="联系方式必须为11位数字")

    for k, label in (("quote_amount_tax", "报价(含税)"), ("pre_tax_salary", "税前工资")):
        v = _normalize_amount_text(data.get(k, ""))
        if v and not re.fullmatch(r"\d{1,8}(?:\.\d{1,2})?", v):
            raise HTTPException(status_code=400, detail=f"{label}格式无效")

    gm_pct = str(data.get("gm_pct", "")).strip()
    gm_pct_norm = gm_pct.replace("\uff05", "%")
    gm_pct_with_symbol_ok = re.fullmatch(r"(100(?:\.0{1,2})?|[1-9]?\d(?:\.\d{1,2})?)%", gm_pct_norm)
    gm_pct_plain_ok = re.fullmatch(r"(100(?:\.0{1,2})?|[1-9]?\d(?:\.\d{1,2})?)", gm_pct_norm)
    if gm_pct and not (gm_pct_with_symbol_ok or gm_pct_plain_ok):
        raise HTTPException(status_code=400, detail="GM%需为0-100（如 12、12.5、12% 或 12.5%）")

    reg_status = str(data.get("regularization_status", "")).strip()
    if reg_status and reg_status not in ("未转正", "已转正"):
        raise HTTPException(status_code=400, detail="转正必须为「未转正」或「已转正」")


# ---------------------------------------------------------------------------
# Client resolution and dedup
# ---------------------------------------------------------------------------

def resolve_roster_customer_client(db: Session, raw: str, Client: Type) -> Tuple[Any, str]:
    """将简称/全称与 clients 表匹配；返回 (Client 或 None, 建议写入花名册的简称/展示名)。"""
    s = str(raw or "").strip()
    if not s:
        return None, ""
    for kw, canonical in ROSTER_CUSTOMER_ALIAS_RULES:
        if kw in s:
            c = db.query(Client).filter(Client.name == canonical).first()
            if c:
                return c, kw
    exact = db.query(Client).filter(Client.name == s).first()
    if exact:
        return exact, s
    return None, s


def contact_dedup_key(raw: Optional[str]) -> str:
    """联系方式去重键：仅保留数字。"""
    if not raw:
        return ""
    digits = "".join(ch for ch in str(raw).strip() if ch.isdigit())
    return digits


def assert_roster_contact_unique(
    db: Session,
    client_id: int,
    contact_info: str,
    RosterEntry: Type,
    exclude_row_id: Optional[int] = None,
) -> None:
    """手动新增/修改时：若联系方式非空，则同一客户下不得与其它行重复。"""
    ck = contact_dedup_key(contact_info)
    if not ck:
        return
    q = db.query(RosterEntry).filter(RosterEntry.client_id == client_id)
    if exclude_row_id is not None:
        q = q.filter(RosterEntry.id != exclude_row_id)
    for e in q.all():
        if contact_dedup_key(e.contact_info) == ck:
            raise HTTPException(
                status_code=409,
                detail="该联系方式在本客户花名册中已存在，请勿重复",
            )


def assert_roster_contact_unique_global(
    db: Session,
    contact_info: str,
    RosterEntry: Type,
    exclude_row_id: Optional[int] = None,
) -> None:
    ck = contact_dedup_key(contact_info)
    if not ck:
        return
    q = db.query(RosterEntry)
    if exclude_row_id is not None:
        q = q.filter(RosterEntry.id != exclude_row_id)
    for e in q.all():
        if contact_dedup_key(e.contact_info) == ck:
            raise HTTPException(status_code=409, detail="该联系方式在整体花名册中已存在，请勿重复")


# ---------------------------------------------------------------------------
# Resequence serial_no
# ---------------------------------------------------------------------------

def resequence_roster_serial_no(db: Session, client_id: int, RosterEntry: Type) -> bool:
    """按当前行顺序重排序号为 1..N。"""
    rows = db.query(RosterEntry).filter(RosterEntry.client_id == client_id).order_by(RosterEntry.id).all()
    changed = False
    for idx, row in enumerate(rows, start=1):
        expected = str(idx)
        if (row.serial_no or "").strip() != expected:
            row.serial_no = expected
            changed = True
    return changed


def resequence_roster_serial_no_all_clients(db: Session, RosterEntry: Type) -> bool:
    """对每个 client_id 分别将序号重排为 1..N。"""
    ids = [cid for (cid,) in db.query(RosterEntry.client_id).distinct().all() if cid is not None]
    changed_any = False
    for cid in ids:
        if resequence_roster_serial_no(db, int(cid), RosterEntry):
            changed_any = True
    return changed_any


# ---------------------------------------------------------------------------
# Backup / CSV write
# ---------------------------------------------------------------------------

def write_roster_backup_csv(client: Any, rows: list, backup_dir: str, RosterEntry: Type) -> str:
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(ch for ch in client.name if ch.isalnum() or ch in (" ", "-", "_")).strip() or f"client_{client.id}"
    name = f"roster_backup_{safe_name}__cid{client.id}__{ts}.csv"
    path = os.path.join(backup_dir, name)
    export_headers = ZNTX_ROSTER_EXPORT_HEADERS if client.name == "中诺通讯" else ROSTER_EXPORT_HEADERS
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(export_headers)
        for e in rows:
            d = roster_entry_to_dict(e)
            writer.writerow([d.get(CHINESE_ROSTER_HEADER_MAP[h], "") for h in export_headers])
    return name


def write_roster_backup_csv_all(rows: list, backup_dir: str) -> str:
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    name = f"roster_backup_all__{ts}.csv"
    path = os.path.join(backup_dir, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(ROSTER_EXPORT_HEADERS)
        for e in rows:
            d = roster_entry_to_dict(e)
            writer.writerow([d.get(CHINESE_ROSTER_HEADER_MAP[h], "") for h in ROSTER_EXPORT_HEADERS])
    return name


def write_roster_backup_turnover_csv_all(rows: list, backup_dir: str) -> str:
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    name = f"roster_backup_turnover_all__{ts}.csv"
    path = os.path.join(backup_dir, name)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(ROSTER_EXPORT_HEADERS)
        for e in rows:
            d = roster_entry_to_dict(e)
            w.writerow([d.get(CHINESE_ROSTER_HEADER_MAP[h], "") for h in ROSTER_EXPORT_HEADERS])
    return name


def ensure_merged_turnover_employment(merged: Dict[str, str]) -> None:
    st = str(merged.get("employment_status", "")).strip()
    if not st or "离职" not in st:
        merged["employment_status"] = "离职"


# ---------------------------------------------------------------------------
# CSV upload parsing
# ---------------------------------------------------------------------------

def decode_roster_upload_bytes(raw: bytes) -> str:
    """依次尝试 UTF-8（含 BOM）、UTF-16（Excel 另存常见）、GB18030。"""
    if len(raw) >= 2 and raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16-sig")
    if len(raw) >= 3 and raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("gb18030", errors="replace")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")



def _is_gms_column_header(h: str) -> bool:
    t = _strip_csv_header_noise(h)
    if not t:
        return False
    if t.replace(" ", "") in ("GM%", "GM\uff05"):
        return False
    compact = re.sub(r"\s+", "", t)
    for u in ("\uff04", "\ufe69"):
        compact = compact.replace(u, "$")
    if compact.upper() in ("GM$", "GMS"):
        return True
    if re.fullmatch(r"GM[$]", compact, flags=re.IGNORECASE):
        return True
    if re.fullmatch(r"GMS", compact, flags=re.IGNORECASE):
        return True
    if len(compact) == 3 and compact[:2].upper() == "GM":
        tail = compact[2]
        if tail in ("%", "\uff05"):
            return False
        if tail == "$" or tail in "\uff04\ufe69":
            return True
        try:
            if "DOLLAR" in unicodedata.name(tail).upper():
                return True
        except ValueError:
            pass
    return False


def map_roster_csv_header(cell: str) -> Optional[str]:
    if cell is None:
        return None
    h = _strip_csv_header_noise(cell)
    if h in CHINESE_ROSTER_HEADER_MAP:
        return CHINESE_ROSTER_HEADER_MAP[h]
    if h in ROSTER_FIELD_KEYS:
        return h
    if _is_gms_column_header(h):
        return "gms"
    return None


def _detect_csv_delimiter(first_line: str) -> str:
    if not first_line:
        return ","
    c, s, tab = first_line.count(","), first_line.count(";"), first_line.count("\t")
    m = max(c, s, tab)
    if m == 0:
        return ","
    if c == m:
        return ","
    if s == m:
        return ";"
    return "\t"


def _csv_field_count(line: str, delim: str) -> int:
    try:
        row = next(csv.reader([line], delimiter=delim))
        return len(row)
    except Exception:
        return 0


def _best_csv_delimiter(first_line: str) -> str:
    if not first_line.strip():
        return ","
    best_d, best_n = ",", 0
    for d in (",", ";", "\t"):
        n = _csv_field_count(first_line, d)
        if n > best_n:
            best_n, best_d = n, d
    if best_n >= 2:
        return best_d
    return _detect_csv_delimiter(first_line)


def iter_roster_csv_data_rows(text: str):
    """用 csv.reader 按列下标与表头对齐解析。每行 yield dict。"""
    raw_lines = text.splitlines()
    while raw_lines and not raw_lines[0].strip():
        raw_lines.pop(0)
    while raw_lines and not raw_lines[-1].strip():
        raw_lines.pop()
    if not raw_lines:
        return
    text_norm = "\n".join(raw_lines)
    delim = _best_csv_delimiter(raw_lines[0])
    reader = csv.reader(io.StringIO(text_norm), delimiter=delim)
    rows = list(reader)
    if not rows:
        return
    headers = rows[0]
    for parts in rows[1:]:
        row_dict: Dict[str, str] = {}
        for i, hcell in enumerate(headers):
            val = parts[i] if i < len(parts) else ""
            fk = map_roster_csv_header(hcell or "")
            if fk:
                row_dict[fk] = (val or "").strip()
        yield row_dict


def analyze_roster_csv_headers(text: str) -> Dict[str, Any]:
    """返回 CSV 首行表头的识别情况。"""
    raw_lines = text.splitlines()
    while raw_lines and not raw_lines[0].strip():
        raw_lines.pop(0)
    while raw_lines and not raw_lines[-1].strip():
        raw_lines.pop()
    if not raw_lines:
        return {"headers": [], "matched_headers": [], "unmatched_headers": []}
    delim = _best_csv_delimiter(raw_lines[0])
    reader = csv.reader(io.StringIO(raw_lines[0]), delimiter=delim)
    try:
        headers = next(reader)
    except StopIteration:
        headers = []
    matched_headers: List[str] = []
    unmatched_headers: List[str] = []
    for h in headers:
        name = _strip_csv_header_noise(h or "")
        if not name:
            continue
        if map_roster_csv_header(name):
            matched_headers.append(name)
        else:
            unmatched_headers.append(name)
    return {
        "headers": headers,
        "matched_headers": matched_headers,
        "unmatched_headers": unmatched_headers,
    }


# ---------------------------------------------------------------------------
# Turnover dashboard helpers (COMPLETE — not split across files)
# ---------------------------------------------------------------------------

def roster_distinct_client_ids(db: Session, RosterEntry: Type) -> List[int]:
    """花名册中出现过的客户 (client_id 去重)。"""
    rows = (
        db.query(RosterEntry.client_id)
        .filter(RosterEntry.client_id.isnot(None), RosterEntry.client_id > 0)
        .distinct()
        .all()
    )
    return sorted({int(r[0]) for r in rows if r[0] is not None})


def dashboard_business_options(db: Session, RosterEntry: Type, Client: Type) -> List[Dict[str, Any]]:
    opts: List[Dict[str, Any]] = []
    for cid in roster_distinct_client_ids(db, RosterEntry):
        c = db.query(Client).filter(Client.id == cid).first()
        if not c:
            continue
        short = (c.name or "").strip()
        for kw, full in ROSTER_CUSTOMER_ALIAS_RULES:
            if full == c.name:
                short = kw
                break
        opts.append({"client_id": cid, "label": (c.name or "").strip(), "short_key": short})
    opts.sort(key=lambda x: x["label"])
    return opts


def dashboard_scope_client_ids(
    db: Session, scope: str, business_key: str, RosterEntry: Type, Client: Type
) -> Tuple[List[int], str]:
    roster_cids = roster_distinct_client_ids(db, RosterEntry)
    sk = str(business_key or "").strip()
    if str(scope or "").strip().lower() == "business" and sk:
        c, _ = resolve_roster_customer_client(db, sk, Client)
        if not c:
            raise HTTPException(
                status_code=400,
                detail="未识别客户，请使用与花名册「客户」列一致的简称或「客户管理」中的全称",
            )
        if c.id not in set(roster_cids):
            raise HTTPException(status_code=400, detail="花名册中尚无该客户的数据")
        return [c.id], (c.name or "").strip() or sk
    return roster_cids, "整体客户"


def roster_entries_for_client_ids(db: Session, client_ids: List[int], RosterEntry: Type) -> list:
    if not client_ids:
        return []
    return (
        db.query(RosterEntry)
        .filter(RosterEntry.client_id.in_(client_ids))
        .order_by(RosterEntry.id)
        .all()
    )


def roster_entries_for_business_scope(db: Session, client_ids: List[int], RosterEntry: Type, Client: Type) -> list:
    """单一业务看板：该客户下全部行 + client 未绑但可解析为同一客户的离职档案行。"""
    if not client_ids:
        return []
    target_id = int(client_ids[0])
    by_id: Dict[int, Any] = {e.id: e for e in roster_entries_for_client_ids(db, client_ids, RosterEntry)}
    orphan_turnover = and_(
        or_(RosterEntry.client_id.is_(None), RosterEntry.client_id == 0),
        sql_roster_employment_left(RosterEntry),
    )
    for r in db.query(RosterEntry).filter(orphan_turnover).order_by(RosterEntry.id).all():
        if r.id in by_id:
            continue
        c, _ = resolve_roster_customer_client(db, r.customer_name or "", Client)
        if c and c.id == target_id:
            by_id[r.id] = r
    return sorted(by_id.values(), key=lambda e: e.id)


def roster_entries_department_dashboard(db: Session, RosterEntry: Type) -> list:
    """花名册整体看板：已关联客户的全部行 + client_id 未绑定的离职档案行。"""
    roster_cids = roster_distinct_client_ids(db, RosterEntry)
    orphan_turnover = and_(
        or_(RosterEntry.client_id.is_(None), RosterEntry.client_id == 0),
        sql_roster_employment_left(RosterEntry),
    )
    filt = or_(RosterEntry.client_id.in_(roster_cids), orphan_turnover) if roster_cids else orphan_turnover
    return db.query(RosterEntry).filter(filt).order_by(RosterEntry.id).all()


def row_is_turnover_pool(r: Any) -> bool:
    st = str(r.employment_status or "")
    return "离职" in st


def _employed_on_date_row(r: Any, d: date) -> bool:
    """某日是否计为在职（计头计尾：离职日当天仍计为在职）。"""
    entry_d = parse_loose_date(str(r.entry_date or ""))
    if not entry_d:
        return False
    if d < entry_d:
        return False
    resign_d = parse_loose_date(str(r.company_resign_date or ""))
    if resign_d and d > resign_d:
        return False
    return True


def _headcount_on_date(rows: list, d: date) -> int:
    return sum(1 for r in rows if _employed_on_date_row(r, d))


def _avg_headcount_period(rows: list, d0: date, d1: date) -> Tuple[float, int, int]:
    h0 = _headcount_on_date(rows, d0)
    h1 = _headcount_on_date(rows, d1)
    return (h0 + h1) / 2.0, h0, h1


def _departure_events_in_range(rows: list, d0: date, d1: date) -> list:
    out: list = []
    for r in rows:
        if not row_is_turnover_pool(r):
            continue
        rd = parse_loose_date(str(r.company_resign_date or ""))
        if not rd:
            continue
        if d0 <= rd <= d1:
            out.append(r)
    return out


def _onboarding_events_in_range(rows: list, d0: date, d1: date) -> list:
    out: list = []
    for r in rows:
        ed = parse_loose_date(str(r.entry_date or ""))
        if not ed:
            continue
        if d0 <= ed <= d1:
            out.append(r)
    return out


def _classify_separation_kind(raw: str) -> str:
    s = str(raw or "")
    if "转出" in s:
        return "transfer"
    if "被动" in s:
        return "passive"
    if "主动" in s:
        return "active"
    return "unknown"


def _zntx_is_business_termination_type(raw: Optional[str]) -> bool:
    return "业务离职" in str(raw or "")


def _departure_business_termination_subset(rows: list) -> list:
    return [r for r in rows if _zntx_is_business_termination_type(r.zntx_separation_type)]


def _tenure_days_at_resign(r: Any) -> Optional[int]:
    entry_d = parse_loose_date(str(r.entry_date or ""))
    resign_d = parse_loose_date(str(r.company_resign_date or ""))
    if not entry_d or not resign_d:
        return None
    return (resign_d - entry_d).days


def _tenure_exclusive_bucket(days: Optional[int]) -> str:
    if days is None:
        return "入职/离职日期缺失"
    if days < 0:
        return "日期异常"
    if days <= 7:
        return "入职1周内"
    if days <= 14:
        return "入职2周内"
    if days <= 30:
        return "入职1月内"
    if days <= 90:
        return "入职3月内"
    if days <= 180:
        return "入职半年内"
    if days <= 365:
        return "入职1年内"
    return "入职1年及以上"


def _last_day_of_month(y: int, m: int) -> date:
    return date(y, m, monthrange(y, m)[1])


def _trend_month_row_is_idle(row: Dict[str, Any]) -> bool:
    d = int(row.get("departures") or 0)
    o = int(row.get("onboardings") or 0)
    av = float(row.get("avg_headcount") or 0)
    return d == 0 and o == 0 and av < 0.0001


def _trim_trend_idle_edges(monthly: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not monthly:
        return monthly
    n = len(monthly)
    i, j = 0, n - 1
    while i < n and _trend_month_row_is_idle(monthly[i]):
        i += 1
    while j >= i and _trend_month_row_is_idle(monthly[j]):
        j -= 1
    if i > j:
        return [monthly[-1]]
    return monthly[i : j + 1]


def _first_day_n_months_before(today: date, months_back: int) -> date:
    y, m = today.year, today.month
    for _ in range(months_back):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return date(y, m, 1)


def _parse_dashboard_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    s = str(raw).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None
    pd = parse_loose_date(s)
    return pd if isinstance(pd, date) else None


def _norm_pos_loc(val: str, fallback: str = "(未填)") -> str:
    s = str(val or "").strip()
    return s if s else fallback


def departures_by_business_department(
    db: Session, deps_p: list, Client: Type
) -> List[Dict[str, Any]]:
    """整体看板：按客户/业务名汇总同期离职人数。"""
    if not deps_p:
        return []
    cids = {int(r.client_id) for r in deps_p if r.client_id and int(r.client_id) > 0}
    id_to_name: Dict[int, str] = {}
    if cids:
        for c in db.query(Client).filter(Client.id.in_(cids)).all():
            id_to_name[c.id] = (c.name or "").strip() or f"客户#{c.id}"
    cnt: Counter = Counter()
    for r in deps_p:
        cid = r.client_id
        if cid and int(cid) > 0 and int(cid) in id_to_name:
            label = id_to_name[int(cid)]
        else:
            cn = str(r.customer_name or "").strip()
            label = cn if cn else "(未绑客户)"
        cnt[label] += 1
    return [
        {"dimension": lab, "departures": n}
        for lab, n in sorted(cnt.items(), key=lambda x: (-x[1], x[0]))
    ]


def _separation_detail_label(raw: Optional[str]) -> str:
    s = str(raw or "")
    if "转出" in s:
        return "转出"
    if "被动" in s:
        return "被动"
    if "主动" in s:
        return "主动"
    return "未标注"


def _departure_detail_entries(rows: list) -> List[Dict[str, str]]:
    def _sort_key(r: Any) -> Tuple[date, str]:
        rd = parse_loose_date(str(r.company_resign_date or ""))
        return (rd if isinstance(rd, date) else date.min, str(r.full_name or ""))

    out: List[Dict[str, str]] = []
    for r in sorted(rows, key=_sort_key):
        nm = str(r.full_name or "").strip() or "（无姓名）"
        rd = parse_loose_date(str(r.company_resign_date or ""))
        ds_str = rd.isoformat() if isinstance(rd, date) else str(r.company_resign_date or "").strip() or "—"
        cust = str(r.customer_name or r.business_line or "").strip()
        suf = f" · {cust}" if cust else ""
        out.append(
            {
                "detail": f"{nm} · 离职日 {ds_str}{suf}",
                "separation": _separation_detail_label(r.zntx_separation_type),
            }
        )
    return out


def _onboarding_detail_entries(rows: list) -> List[Dict[str, str]]:
    def _sort_key(r: Any) -> Tuple[date, str]:
        ed = parse_loose_date(str(r.entry_date or ""))
        return (ed if isinstance(ed, date) else date.min, str(r.full_name or ""))

    out: List[Dict[str, str]] = []
    for r in sorted(rows, key=_sort_key):
        nm = str(r.full_name or "").strip() or "（无姓名）"
        ed = parse_loose_date(str(r.entry_date or ""))
        ds_str = ed.isoformat() if isinstance(ed, date) else str(r.entry_date or "").strip() or "—"
        cust = str(r.customer_name or r.business_line or "").strip()
        suf = f" · {cust}" if cust else ""
        out.append({"detail": f"{nm} · 入职日 {ds_str}{suf}", "separation": ""})
    return out


# ---------------------------------------------------------------------------
# Turnover dashboard main computation
# ---------------------------------------------------------------------------

def compute_turnover_dashboard(
    db: Session,
    scope: str,
    business_key: str,
    trend_months: int,
    period_start: str,
    period_end: str,
    RosterEntry: Type,
    Client: Type,
) -> Dict[str, Any]:
    """Complete turnover dashboard computation — moved from main.py route handler."""
    tm = max(1, min(int(trend_months or 12), 36))
    client_ids, scope_title = dashboard_scope_client_ids(db, scope, business_key, RosterEntry, Client)
    if str(scope or "").strip().lower() == "business":
        rows_all = roster_entries_for_business_scope(db, client_ids, RosterEntry, Client)
    else:
        rows_all = roster_entries_department_dashboard(db, RosterEntry)
    today = date.today()

    ps = _parse_dashboard_date(period_start)
    pe = _parse_dashboard_date(period_end)
    if not ps or not pe:
        first_this = today.replace(day=1)
        pe = first_this - timedelta(days=1)
        ps = pe.replace(day=1)
    if pe < ps:
        raise HTTPException(status_code=400, detail="统计结束日期不能早于开始日期")

    avg_p, h0_p, h1_p = _avg_headcount_period(rows_all, ps, pe)
    deps_p = _departure_events_in_range(rows_all, ps, pe)
    dep_n = len(deps_p)
    bdeps_p = _departure_business_termination_subset(deps_p)
    bdep_n = len(bdeps_p)
    bdep_rate_p = round((bdep_n / avg_p) * 100, 2) if avg_p > 0 else None
    onb_p = _onboarding_events_in_range(rows_all, ps, pe)
    onb_n = len(onb_p)
    rate_p = round((dep_n / avg_p) * 100, 2) if avg_p > 0 else None

    sep_counts = {"active": 0, "passive": 0, "transfer": 0, "unknown": 0}
    tenure_bucket_counts: Dict[str, int] = {}
    for r in deps_p:
        sep_counts[_classify_separation_kind(str(r.zntx_separation_type or ""))] += 1
        b = _tenure_exclusive_bucket(_tenure_days_at_resign(r))
        tenure_bucket_counts[b] = tenure_bucket_counts.get(b, 0) + 1

    sep_rates = {
        k: (round((v / dep_n) * 100, 2) if dep_n > 0 else None) for k, v in sep_counts.items()
    }

    tenure_order = [
        "入职1周内",
        "入职2周内",
        "入职1月内",
        "入职3月内",
        "入职半年内",
        "入职1年内",
        "入职1年及以上",
        "入职/离职日期缺失",
        "日期异常",
    ]
    tenure_buckets = [{"label": lab, "count": tenure_bucket_counts.get(lab, 0)} for lab in tenure_order]

    trend_start = _first_day_n_months_before(today, tm - 1)
    monthly: List[Dict[str, Any]] = []
    y, m = trend_start.year, trend_start.month
    while date(y, m, 1) <= date(today.year, today.month, 1):
        ms = date(y, m, 1)
        me = _last_day_of_month(y, m)
        avg_m, hs, he = _avg_headcount_period(rows_all, ms, me)
        dm = _departure_events_in_range(rows_all, ms, me)
        bdm = _departure_business_termination_subset(dm)
        bdep_rate_m = round((len(bdm) / avg_m) * 100, 2) if avg_m > 0 else None
        om = _onboarding_events_in_range(rows_all, ms, me)
        if avg_m > 0:
            rate_m = round((len(dm) / avg_m) * 100, 2)
        else:
            rate_m = 0.0 if len(dm) == 0 else None
        monthly.append(
            {
                "year": y,
                "month": m,
                "month_key": f"{y:04d}-{m:02d}",
                "month_label": f"{y}年{m}月",
                "period_start": ms.isoformat(),
                "period_end": me.isoformat(),
                "departures": len(dm),
                "departure_details": _departure_detail_entries(dm),
                "business_departures": len(bdm),
                "business_departure_details": _departure_detail_entries(bdm),
                "business_departure_rate_pct": bdep_rate_m,
                "onboardings": len(om),
                "onboarding_details": _onboarding_detail_entries(om),
                "headcount_start": hs,
                "headcount_end": he,
                "avg_headcount": round(avg_m, 2),
                "rate_pct": rate_m,
            }
        )
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1

    monthly = _trim_trend_idle_edges(monthly)

    by_business: List[Dict[str, Any]] = []
    if str(scope or "").strip().lower() == "department":
        by_business = departures_by_business_department(db, deps_p, Client)

    by_position: List[Dict[str, Any]] = []
    by_city: List[Dict[str, Any]] = []
    if str(scope or "").strip().lower() == "business" and client_ids:

        def _norm_city(val: str) -> str:
            return _norm_pos_loc(val, "(未填工作地)")

        pos_keys: set = set()
        for r in deps_p:
            pos_keys.add(_norm_pos_loc(r.position_title))
        for r in rows_all:
            if _employed_on_date_row(r, ps) or _employed_on_date_row(r, pe):
                pos_keys.add(_norm_pos_loc(r.position_title))
        for pk in sorted(pos_keys, key=lambda x: (x == "(未填)", x)):
            rows_p = [r for r in rows_all if _norm_pos_loc(r.position_title) == pk]
            avg_x, _, _ = _avg_headcount_period(rows_p, ps, pe)
            dep_x = [r for r in deps_p if _norm_pos_loc(r.position_title) == pk]
            rate_x = round((len(dep_x) / avg_x) * 100, 2) if avg_x > 0 else None
            by_position.append(
                {
                    "dimension": pk,
                    "departures": len(dep_x),
                    "avg_headcount": round(avg_x, 2),
                    "rate_pct": rate_x,
                }
            )
        city_keys: set = set()
        for r in deps_p:
            city_keys.add(_norm_city(r.work_location))
        for r in rows_all:
            if _employed_on_date_row(r, ps) or _employed_on_date_row(r, pe):
                city_keys.add(_norm_city(r.work_location))
        for ck in sorted(city_keys, key=lambda x: (x == "(未填工作地)", x)):
            rows_c = [r for r in rows_all if _norm_city(r.work_location) == ck]
            avg_c, _, _ = _avg_headcount_period(rows_c, ps, pe)
            dep_c = [r for r in deps_p if _norm_city(r.work_location) == ck]
            rate_c = round((len(dep_c) / avg_c) * 100, 2) if avg_c > 0 else None
            by_city.append(
                {
                    "dimension": ck,
                    "departures": len(dep_c),
                    "avg_headcount": round(avg_c, 2),
                    "rate_pct": rate_c,
                }
            )

    rows_denominator_base = len([r for r in rows_all if parse_loose_date(str(r.entry_date or ""))])
    footnote = (
        "离职率 = 期内离职人数（离职档案且离职日期落在区间内）÷ 期内平均在职人数；"
        "平均在职 =（期初日在职 + 期末日在职）/2；在职按入职日、离职日推断，离职日当日仍计为在职；"
        "各月「入职」= 当月内入职日期落在该自然月的花名册行数（与上方面向范围一致）；"
        f"当前范围内花名册共 {len(rows_all)} 行，其中 {rows_denominator_base} 行有入职日期可参与分母。"
    )
    if str(scope or "").strip().lower() == "department":
        footnote += (
            " 整体客户看板中「业务离职」= 上述同期离职记录里，「离职类型」含「业务离职」者；"
            "与主动/被动/转出分类独立展示，可重叠。"
        )

    return {
        "scope": str(scope or "department"),
        "scope_title": scope_title,
        "business_options": dashboard_business_options(db, RosterEntry, Client),
        "footnote": footnote,
        "analysis_period": {
            "start": ps.isoformat(),
            "end": pe.isoformat(),
            "departures": dep_n,
            "departure_details": _departure_detail_entries(deps_p),
            "business_departures": bdep_n,
            "business_departure_details": _departure_detail_entries(bdeps_p),
            "business_departure_rate_pct": bdep_rate_p,
            "onboardings": onb_n,
            "onboarding_details": _onboarding_detail_entries(onb_p),
            "headcount_start": h0_p,
            "headcount_end": h1_p,
            "avg_headcount": round(avg_p, 2),
            "rate_pct": rate_p,
        },
        "separation": {
            "active": {"count": sep_counts["active"], "rate_pct": sep_rates["active"]},
            "passive": {"count": sep_counts["passive"], "rate_pct": sep_rates["passive"]},
            "transfer": {"count": sep_counts["transfer"], "rate_pct": sep_rates["transfer"]},
            "unknown": {"count": sep_counts["unknown"], "rate_pct": sep_rates["unknown"]},
        },
        "tenure_buckets": tenure_buckets,
        "monthly_trend": monthly,
        "trend_months": tm,
        "by_business": by_business,
        "by_position": by_position,
        "by_city": by_city,
    }
