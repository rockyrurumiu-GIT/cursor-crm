import os
import re
import time
import shutil
import json
import csv
import io
import socket
import unicodedata
from urllib.parse import quote
from datetime import datetime, timedelta
from typing import List, Optional, Any, Dict, Tuple
from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File, status, Body
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Float, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# --- 1. 配置与初始化 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
TRASH_DIR = os.path.join(BASE_DIR, "deleted_files")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
DB_URL = "sqlite:///./crm_v8.db"
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
ADMIN_USER = {"username": "admin", "password": "admin123"}

for d in [STATIC_DIR, UPLOAD_DIR, TRASH_DIR, BACKUP_DIR]:
    os.makedirs(d, exist_ok=True)


def cleanup_trash():
    now = time.time()
    if os.path.exists(TRASH_DIR):
        for f in os.listdir(TRASH_DIR):
            f_path = os.path.join(TRASH_DIR, f)
            if os.stat(f_path).st_mtime < now - 30 * 86400:
                if os.path.isfile(f_path):
                    os.remove(f_path)
                else:
                    shutil.rmtree(f_path)


cleanup_trash()

# --- 2. 数据库模型 ---
Base = declarative_base()


class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    industry = Column(String)
    owner = Column(String)
    scale = Column(String)
    phase = Column(String)  # 初步接触, 方案/报价, 合同签订, 成交
    description = Column(Text)
    remarks = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


class VisitRecord(Base):
    __tablename__ = "visits"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    date = Column(String)
    location = Column(String)
    way = Column(String)
    target = Column(String)
    content = Column(Text)
    result = Column(Text)
    next_plan = Column(Text)
    attachment = Column(String, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer)
    operator = Column(String)
    action = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class RosterEntry(Base):
    """客户花名册行（表头固定，仅数据可编辑）"""
    __tablename__ = "roster_entries"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), index=True)
    serial_no = Column(String, default="")
    employment_status = Column(String, default="")
    full_name = Column(String, default="")
    contact_info = Column(String, default="")
    customer_name = Column(String, default="")
    work_location = Column(String, default="")
    position_title = Column(String, default="")
    business_line = Column(String, default="")
    entry_date = Column(String, default="")
    regularization_date = Column(String, default="")
    monthly_quote_tax = Column(String, default="")
    pre_tax_salary = Column(String, default="")
    salary_quote_ratio = Column(String, default="")
    gms = Column(String, default="")
    gm_pct = Column(String, default="")
    employee_plus1 = Column(String, default="")
    zntx_onboarding_channel = Column(String, default="")
    zntx_attendance_checkin = Column(String, default="")
    zntx_attendance_makeup = Column(String, default="")
    employee_plus2 = Column(String, default="")
    interface_contact = Column(String, default="")
    project_release_date = Column(String, default="")
    company_resign_date = Column(String, default="")
    zntx_staff_no = Column(String, default="")
    zntx_separation_type = Column(String, default="")
    zntx_compensation_amount = Column(String, default="")
    leave_reason = Column(String, default="")
    remarks = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


class DeliverySettlementEntry(Base):
    __tablename__ = "delivery_settlement_entries"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), index=True)
    serial_no = Column(String, default="")
    progress_updated_at = Column(String, default="")
    customer_name = Column(String, default="")
    fee_month = Column(String, default="")
    chase_month = Column(String, default="")
    amount = Column(String, default="")
    internal_attendance_confirm = Column(String, default="")
    client_confirm = Column(String, default="")
    invoiced = Column(String, default="")
    invoice_date = Column(String, default="")
    paid = Column(String, default="")
    expected_payment_date = Column(String, default="")
    actual_payment_date = Column(String, default="")
    payment_days = Column(String, default="")
    payment_cycle = Column(String, default="")
    payment_nature = Column(String, default="")
    po_no = Column(String, default="")
    invoice_no = Column(String, default="")
    remarks = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


class DeliveryPipelineEntry(Base):
    __tablename__ = "delivery_pipeline_entries"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), index=True)
    resume_time = Column(String, default="")
    date = Column(String, default="")
    position = Column(String, default="")
    full_name = Column(String, default="")
    domain = Column(String, default="")
    years_experience = Column(String, default="")
    region = Column(String, default="")
    phone = Column(String, default="")
    education = Column(String, default="")
    recruiter = Column(String, default="")
    resume_screening = Column(String, default="")
    interviewed = Column(String, default="")
    interview_time = Column(String, default="")
    interviewer = Column(String, default="")
    result = Column(String, default="")
    got_offer = Column(String, default="")
    onboarding_time = Column(String, default="")
    onboarded = Column(String, default="")
    status_note = Column(String, default="")
    serial_no = Column(String, default="")
    created_at = Column(DateTime, default=datetime.now)


class DeliveryPipelineInsightDemand(Base):
    __tablename__ = "delivery_pipeline_insight_demands"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), index=True)
    period = Column(String, default="")
    position = Column(String, default="")
    region = Column(String, default="")
    demand_qty = Column(String, default="")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DeliveryInterviewEntry(Base):
    """员工访谈 — 全客户统一表头/字段（不含入职时间）；旧列仍兼容备份/导入。"""
    __tablename__ = "delivery_interview_entries"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), index=True)
    serial_no = Column(String, default="")
    full_name = Column(String, default="")
    employment_status = Column(String, default="")
    contact = Column(String, default="")
    project_name = Column(String, default="")
    position = Column(String, default="")
    employee_q1 = Column(String, default="")
    satisfaction = Column(String, default="")
    onboarding_time = Column(String, default="")
    interview_date = Column(String, default="")
    days_since_onboarding = Column(String, default="")
    interview_content = Column(Text, default="")
    delivery_judgment = Column(String, default="")
    employee_requests = Column(Text, default="")
    delivery_todos = Column(Text, default="")
    work_location = Column(String, default="")
    hometown = Column(String, default="")
    followup_1d = Column(String, default="")
    followup_7d = Column(String, default="")
    followup_30d = Column(String, default="")
    followup_90d = Column(String, default="")
    created_at = Column(DateTime, default=datetime.now)


engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def _ensure_interview_schema_compat():
    """旧库仅有早期员工访谈列时，补齐当前全局统一员工访谈字段，避免查询失败。"""
    with engine.begin() as conn:
        try:
            existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(delivery_interview_entries)").fetchall()}
        except Exception:
            return
        add_cols = {
            "employment_status": "TEXT DEFAULT ''",
            "contact": "TEXT DEFAULT ''",
            "project_name": "TEXT DEFAULT ''",
            "employee_q1": "TEXT DEFAULT ''",
            "satisfaction": "TEXT DEFAULT ''",
            "onboarding_time": "TEXT DEFAULT ''",
            "days_since_onboarding": "TEXT DEFAULT ''",
            "interview_content": "TEXT DEFAULT ''",
            "delivery_judgment": "TEXT DEFAULT ''",
            "employee_requests": "TEXT DEFAULT ''",
            "delivery_todos": "TEXT DEFAULT ''",
            "work_location": "TEXT DEFAULT ''",
            "hometown": "TEXT DEFAULT ''",
            "followup_1d": "TEXT DEFAULT ''",
            "followup_7d": "TEXT DEFAULT ''",
            "followup_30d": "TEXT DEFAULT ''",
            "followup_90d": "TEXT DEFAULT ''",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE delivery_interview_entries ADD COLUMN {col} {ddl}")


def _ensure_roster_schema_compat():
    """为已存在 sqlite 表补齐后续新增列，避免旧库导入/编辑失败。"""
    with engine.begin() as conn:
        existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(roster_entries)").fetchall()}
        add_cols = {
            "zntx_staff_no": "TEXT DEFAULT ''",
            "zntx_onboarding_channel": "TEXT DEFAULT ''",
            "zntx_attendance_checkin": "TEXT DEFAULT ''",
            "zntx_attendance_makeup": "TEXT DEFAULT ''",
            "zntx_separation_type": "TEXT DEFAULT ''",
            "zntx_compensation_amount": "TEXT DEFAULT ''",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE roster_entries ADD COLUMN {col} {ddl}")


_ensure_roster_schema_compat()
_ensure_interview_schema_compat()

# --- 3. 后端核心逻辑 ---
app = FastAPI(title="ITO CRM Ultimate")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/previews", StaticFiles(directory=UPLOAD_DIR), name="previews")
security = HTTPBasic()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != ADMIN_USER["username"] or credentials.password != ADMIN_USER["password"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    return credentials.username


def _roster_entry_to_dict(e: RosterEntry) -> dict:
    return {
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
        "regularization_date": e.regularization_date or "",
        "monthly_quote_tax": e.monthly_quote_tax or "",
        "pre_tax_salary": e.pre_tax_salary or "",
        "salary_quote_ratio": e.salary_quote_ratio or "",
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
        "leave_reason": e.leave_reason or "",
        "remarks": e.remarks or "",
    }


def _normalize_roster_payload(d: Dict[str, Any]) -> Dict[str, str]:
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
        "regularization_date",
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


def _settlement_entry_to_dict(e: DeliverySettlementEntry) -> Dict[str, str]:
    return {
        "id": e.id,
        "client_id": e.client_id,
        "serial_no": e.serial_no or "",
        "progress_updated_at": e.progress_updated_at or "",
        "customer_name": e.customer_name or "",
        "fee_month": e.fee_month or "",
        "chase_month": e.chase_month or "",
        "amount": e.amount or "",
        "internal_attendance_confirm": e.internal_attendance_confirm or "",
        "client_confirm": e.client_confirm or "",
        "invoiced": e.invoiced or "",
        "invoice_date": e.invoice_date or "",
        "paid": e.paid or "",
        "expected_payment_date": e.expected_payment_date or "",
        "actual_payment_date": e.actual_payment_date or "",
        "payment_days": e.payment_days or "",
        "payment_cycle": e.payment_cycle or "",
        "payment_nature": e.payment_nature or "",
        "po_no": e.po_no or "",
        "invoice_no": e.invoice_no or "",
        "remarks": e.remarks or "",
    }


def _pipeline_entry_to_dict(e: DeliveryPipelineEntry) -> Dict[str, str]:
    return {
        "id": e.id,
        "client_id": e.client_id,
        "resume_time": e.resume_time or "",
        "date": e.date or "",
        "position": e.position or "",
        "full_name": e.full_name or "",
        "domain": e.domain or "",
        "years_experience": e.years_experience or "",
        "region": e.region or "",
        "phone": e.phone or "",
        "education": e.education or "",
        "recruiter": e.recruiter or "",
        "resume_screening": e.resume_screening or "",
        "interviewed": e.interviewed or "",
        "interview_time": e.interview_time or "",
        "interviewer": e.interviewer or "",
        "result": e.result or "",
        "got_offer": e.got_offer or "",
        "onboarding_time": e.onboarding_time or "",
        "onboarded": e.onboarded or "",
        "status_note": e.status_note or "",
        "serial_no": e.serial_no or "",
    }


def _normalize_pipeline_payload(d: Dict[str, Any]) -> Dict[str, str]:
    keys = [
        "resume_time",
        "date",
        "position",
        "full_name",
        "domain",
        "years_experience",
        "region",
        "phone",
        "education",
        "recruiter",
        "resume_screening",
        "interviewed",
        "interview_time",
        "interviewer",
        "result",
        "got_offer",
        "onboarding_time",
        "onboarded",
        "status_note",
        "serial_no",
    ]
    out: Dict[str, str] = {}
    for k in keys:
        v = d.get(k, "")
        if v is None:
            v = ""
        out[k] = str(v).strip()
    return out


def _interview_entry_to_dict(e: DeliveryInterviewEntry) -> Dict[str, str]:
    return {
        "id": e.id,
        "client_id": e.client_id,
        "serial_no": e.serial_no or "",
        "full_name": e.full_name or "",
        "employment_status": e.employment_status or "",
        "contact": e.contact or "",
        "project_name": e.project_name or "",
        "position": e.position or "",
        "employee_q1": e.employee_q1 or "",
        "onboarding_time": e.onboarding_time or "",
        "interview_date": e.interview_date or "",
        "satisfaction": e.satisfaction or "",
        "delivery_judgment": e.delivery_judgment or "",
        "employee_requests": e.employee_requests or "",
        "delivery_todos": e.delivery_todos or "",
        "work_location": e.work_location or "",
        "hometown": e.hometown or "",
        "followup_1d": e.followup_1d or "",
        "followup_7d": e.followup_7d or "",
        "followup_30d": e.followup_30d or "",
        "followup_90d": e.followup_90d or "",
    }


def _normalize_interview_payload(d: Dict[str, Any]) -> Dict[str, str]:
    keys = [
        "full_name",
        "employment_status",
        "contact",
        "project_name",
        "position",
        "employee_q1",
        "onboarding_time",
        "interview_date",
        "satisfaction",
        "delivery_judgment",
        "employee_requests",
        "delivery_todos",
        "work_location",
        "hometown",
        "followup_1d",
        "followup_7d",
        "followup_30d",
        "followup_90d",
    ]
    out: Dict[str, str] = {}
    for k in keys:
        v = d.get(k, "")
        if v is None:
            v = ""
        out[k] = str(v).strip()
    return out


def _normalize_settlement_payload(d: Dict[str, Any]) -> Dict[str, str]:
    keys = [
        "serial_no",
        "progress_updated_at",
        "customer_name",
        "fee_month",
        "chase_month",
        "amount",
        "internal_attendance_confirm",
        "client_confirm",
        "invoiced",
        "invoice_date",
        "paid",
        "expected_payment_date",
        "actual_payment_date",
        "payment_days",
        "payment_cycle",
        "payment_nature",
        "po_no",
        "invoice_no",
        "remarks",
    ]
    out: Dict[str, str] = {}
    for k in keys:
        v = d.get(k, "")
        if v is None:
            v = ""
        out[k] = str(v).strip()
    out["amount"] = _normalize_settlement_amount(out.get("amount", ""))
    return out


def _normalize_settlement_amount(raw: str) -> str:
    """金额统一为两位小数字符串，便于结算场景展示。"""
    s = str(raw or "").strip()
    if not s:
        return ""
    s = re.sub(r"[¥￥,\s\u00a0]", "", s)
    try:
        n = float(s)
    except ValueError:
        return ""
    return f"{n:.2f}"


def _resequence_settlement_serial_no(db: Session, client_id: int) -> None:
    rows = (
        db.query(DeliverySettlementEntry)
        .filter(DeliverySettlementEntry.client_id == client_id)
        .order_by(DeliverySettlementEntry.id)
        .all()
    )
    for idx, row in enumerate(rows, start=1):
        row.serial_no = str(idx)


def _resequence_pipeline_serial_no(db: Session, client_id: int) -> None:
    rows = (
        db.query(DeliveryPipelineEntry)
        .filter(DeliveryPipelineEntry.client_id == client_id)
        .order_by(DeliveryPipelineEntry.id)
        .all()
    )
    for idx, row in enumerate(rows, start=1):
        row.serial_no = str(idx)


def _resequence_interview_serial_no(db: Session, client_id: int) -> None:
    rows = (
        db.query(DeliveryInterviewEntry)
        .filter(DeliveryInterviewEntry.client_id == client_id)
        .order_by(DeliveryInterviewEntry.id)
        .all()
    )
    for idx, row in enumerate(rows, start=1):
        row.serial_no = str(idx)


def _normalize_pipeline_insight_demand_payload(d: Dict[str, Any]) -> Dict[str, str]:
    return {
        "period": str(d.get("period", "") or "").strip(),
        "position": str(d.get("position", "") or "").strip(),
        "region": str(d.get("region", "") or "").strip(),
        "demand_qty": str(d.get("demand_qty", "") or "").strip(),
    }


def _resequence_settlement_serial_no_all(db: Session) -> None:
    rows = db.query(DeliverySettlementEntry).order_by(DeliverySettlementEntry.id).all()
    for idx, row in enumerate(rows, start=1):
        row.serial_no = str(idx)


SETTLEMENT_REQUIRED_FIELDS = (
    "customer_name",
    "fee_month",
    "amount",
    "internal_attendance_confirm",
    "client_confirm",
    "invoiced",
    "paid",
    "payment_cycle",
)


SETTLEMENT_REQUIRED_LABELS = {
    "customer_name": "客户",
    "fee_month": "费用月份",
    "amount": "金额",
    "internal_attendance_confirm": "内部确认考勤",
    "client_confirm": "客户确认",
    "invoiced": "是否开票",
    "paid": "是否回款",
    "payment_cycle": "回款周期",
}


def _validate_settlement_payload(data: Dict[str, str]) -> None:
    missing = [k for k in SETTLEMENT_REQUIRED_FIELDS if not str(data.get(k, "")).strip()]
    if missing:
        labels = [SETTLEMENT_REQUIRED_LABELS.get(k, k) for k in missing]
        raise HTTPException(status_code=400, detail=f"以下必填项未填写：{'、'.join(labels)}")

    for k, label in (
        ("internal_attendance_confirm", "内部确认考勤"),
        ("client_confirm", "客户确认"),
        ("invoiced", "是否开票"),
        ("paid", "是否回款"),
    ):
        v = str(data.get(k, "")).strip()
        if v and v not in ("是", "否"):
            raise HTTPException(status_code=400, detail=f"{label}仅支持“是/否”")

    payment_cycle = str(data.get("payment_cycle", "")).strip()
    if payment_cycle and payment_cycle not in ("月度", "双月", "季度", "半年度"):
        raise HTTPException(status_code=400, detail="回款周期仅支持：月度、双月、季度、半年度")

    payment_nature = str(data.get("payment_nature", "")).strip()
    if payment_nature and payment_nature not in ("增量回款", "存量回款"):
        raise HTTPException(status_code=400, detail="回款性质仅支持：增量回款、存量回款")
    amount = str(data.get("amount", "")).strip()
    if amount:
        try:
            float(amount)
        except ValueError:
            raise HTTPException(status_code=400, detail="金额格式不正确")


def _resolve_settlement_client_id(db: Session, customer_name: str, require_existing: bool) -> Optional[int]:
    name = str(customer_name or "").strip()
    c = db.query(Client).filter(Client.name == name).first() if name else None
    if require_existing and not c:
        raise HTTPException(status_code=400, detail="手动新增/修改时，客户必须从已建客户名单中选择")
    return c.id if c else None


def _settlement_dedup_key(customer_name: str, fee_month: str, amount: str, remarks: str) -> str:
    cn = str(customer_name or "").strip()
    fm = str(fee_month or "").strip()
    am = str(amount or "").strip()
    rm = str(remarks or "").strip()
    if not cn or not fm or not am:
        return ""
    return f"{cn}||{fm}||{am}||{rm}"


def _write_settlement_backup_csv(rows: List[DeliverySettlementEntry]) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"settlement_backup_{ts}.csv"
    path = os.path.join(BACKUP_DIR, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(SETTLEMENT_EXPORT_HEADERS)
        for e in rows:
            d = _settlement_entry_to_dict(e)
            writer.writerow([d.get(SETTLEMENT_HEADER_MAP[h], "") for h in SETTLEMENT_EXPORT_HEADERS])
    return name


def _write_roster_backup_csv(client: Client, rows: List[RosterEntry]) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(ch for ch in client.name if ch.isalnum() or ch in (" ", "-", "_")).strip() or f"client_{client.id}"
    name = f"roster_backup_{safe_name}__cid{client.id}__{ts}.csv"
    path = os.path.join(BACKUP_DIR, name)
    export_headers = ZNTX_ROSTER_EXPORT_HEADERS if client.name == "中诺通讯" else ROSTER_EXPORT_HEADERS
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(export_headers)
        for e in rows:
            d = _roster_entry_to_dict(e)
            writer.writerow([d.get(_CHINESE_ROSTER_HEADER_MAP[h], "") for h in export_headers])
    return name


def _write_roster_backup_csv_all(rows: List[RosterEntry]) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"roster_backup_all__{ts}.csv"
    path = os.path.join(BACKUP_DIR, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(ROSTER_EXPORT_HEADERS)
        for e in rows:
            d = _roster_entry_to_dict(e)
            writer.writerow([d.get(_CHINESE_ROSTER_HEADER_MAP[h], "") for h in ROSTER_EXPORT_HEADERS])
    return name


PIPELINE_EXPORT_HEADERS = [
    "简历时间",
    "日期",
    "岗位",
    "姓名",
    "领域",
    "年限",
    "地域",
    "电话",
    "学历",
    "招聘",
    "简历筛选",
    "是否面试",
    "面试时间",
    "面试官",
    "面试结果",
    "是否拿offer",
    "入职时间",
    "是否入职",
    "情况",
    "序号",
]


PIPELINE_HEADER_MAP = {
    "简历时间": "resume_time",
    "日期": "date",
    "岗位": "position",
    "姓名": "full_name",
    "领域": "domain",
    "年限": "years_experience",
    "地域": "region",
    "电话": "phone",
    "学历": "education",
    "招聘": "recruiter",
    "简历筛选": "resume_screening",
    "是否面试": "interviewed",
    "面试时间": "interview_time",
    "面试官": "interviewer",
    "结果": "result",
    "面试结果": "result",
    "是否拿offer": "got_offer",
    "入职时间": "onboarding_time",
    "是否入职": "onboarded",
    "情况": "status_note",
    "序号": "serial_no",
}


def _write_pipeline_backup_csv(client: Client, rows: List[DeliveryPipelineEntry]) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(ch for ch in client.name if ch.isalnum() or ch in (" ", "-", "_")).strip() or f"client_{client.id}"
    name = f"pipeline_backup_{safe_name}__cid{client.id}__{ts}.csv"
    path = os.path.join(BACKUP_DIR, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(PIPELINE_EXPORT_HEADERS)
        for e in rows:
            d = _pipeline_entry_to_dict(e)
            writer.writerow([d.get(PIPELINE_HEADER_MAP[h], "") for h in PIPELINE_EXPORT_HEADERS])
    return name


INTERVIEW_EXPORT_HEADERS = [
    "序号",
    "员工姓名",
    "在职/离职",
    "联系方式",
    "所属项目",
    "岗位",
    "员工加1",
    "入职时间",
    "访谈日期",
    "满意度",
    "交付判断",
    "员工诉求",
    "交付待办事项",
    "工作地",
    "老家",
    "1 D",
    "7 D",
    "30 D",
    "90 D",
]


INTERVIEW_HEADER_MAP = {
    "序号": "serial_no",
    "员工姓名": "full_name",
    "在职/离职": "employment_status",
    "联系方式": "contact",
    "所属项目": "project_name",
    "岗位": "position",
    "员工加1": "employee_q1",
    "员工+1": "employee_q1",
    "员工＋1": "employee_q1",
    "员工➕1": "employee_q1",
    "员工加Q1": "employee_q1",
    "员工ID": "employee_q1",
    "入职时间": "onboarding_time",
    "访谈日期": "interview_date",
    "满意度": "satisfaction",
    "入职天数": "days_since_onboarding",
    "访谈内容及情况": "interview_content",
    "交付判断": "delivery_judgment",
    "员工诉求": "employee_requests",
    "交付待办事项": "delivery_todos",
    "工作地": "work_location",
    "老家": "hometown",
    "1 D": "followup_1d",
    "7 D": "followup_7d",
    "30 D": "followup_30d",
    "90 D": "followup_90d",
}


def _interview_display_serial_pairs(rows: List[DeliveryInterviewEntry]) -> List[Tuple[int, DeliveryInterviewEntry]]:
    """按 id 升序；同一「员工姓名」共用同一序号（首次出现递增，重名复用）。姓名为空时归为同一组。"""
    sorted_rows = sorted(rows, key=lambda e: e.id or 0)
    name_to_sn: Dict[str, int] = {}
    next_sn = 1
    out: List[Tuple[int, DeliveryInterviewEntry]] = []
    for e in sorted_rows:
        name = str(e.full_name or "").strip()
        key = name if name else "__empty__"
        if key not in name_to_sn:
            name_to_sn[key] = next_sn
            next_sn += 1
        out.append((name_to_sn[key], e))
    return out


def _write_interview_backup_csv(client: Client, rows: List[DeliveryInterviewEntry]) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(ch for ch in client.name if ch.isalnum() or ch in (" ", "-", "_")).strip() or f"client_{client.id}"
    name = f"interview_backup_{safe_name}__cid{client.id}__{ts}.csv"
    path = os.path.join(BACKUP_DIR, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(INTERVIEW_EXPORT_HEADERS)
        for sn, e in _interview_display_serial_pairs(rows):
            d = _interview_entry_to_dict(e)
            cells = [str(sn)] + [d.get(INTERVIEW_HEADER_MAP[h], "") for h in INTERVIEW_EXPORT_HEADERS[1:]]
            writer.writerow(cells)
    return name


def _ascii_filename_fallback(source: str, default_base: str = "export") -> str:
    s = "".join(ch for ch in (source or "") if ch.isascii() and (ch.isalnum() or ch in (" ", "-", "_"))).strip()
    return s or default_base


def _set_csv_download_headers(response: StreamingResponse, chinese_filename: str, ascii_base: str) -> None:
    safe_ascii = _ascii_filename_fallback(ascii_base, "export")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{safe_ascii}.csv"; '
        f"filename*=UTF-8''{quote(chinese_filename)}"
    )


def _pick_latest_backup(prefix: str, client_id: Optional[int] = None) -> Optional[str]:
    files = [f for f in os.listdir(BACKUP_DIR) if f.startswith(prefix) and f.endswith(".csv")]
    if client_id is not None:
        marker = f"__cid{client_id}__"
        legacy_marker = f"_{client_id}_"
        files = [f for f in files if (marker in f or legacy_marker in f)]
    if not files:
        return None
    files.sort(key=lambda x: os.path.getmtime(os.path.join(BACKUP_DIR, x)), reverse=True)
    return files[0]


SETTLEMENT_EXPORT_HEADERS = [
    "序号",
    "结算进度更新日期",
    "客户",
    "费用月份",
    "追款月份",
    "金额",
    "内部确认考勤",
    "客户确认",
    "是否开票",
    "开票日期",
    "是否回款",
    "预计回款时间",
    "实际回款时间",
    "回款天数",
    "回款周期",
    "回款性质",
    "PO单",
    "发票号",
    "备注",
]


SETTLEMENT_HEADER_MAP = {
    "序号": "serial_no",
    "结算进度更新日期": "progress_updated_at",
    "客户": "customer_name",
    "费用月份": "fee_month",
    "追款月份": "chase_month",
    "金额": "amount",
    "内部确认考勤": "internal_attendance_confirm",
    "客户确认": "client_confirm",
    "是否开票": "invoiced",
    "开票日期": "invoice_date",
    "是否回款": "paid",
    "预计回款时间": "expected_payment_date",
    "实际回款时间": "actual_payment_date",
    "回款天数": "payment_days",
    "回款周期": "payment_cycle",
    "回款性质": "payment_nature",
    "PO单": "po_no",
    "发票号": "invoice_no",
    "备注": "remarks",
}


ROSTER_FIELD_KEYS = frozenset(
    [
        "serial_no",
        "employment_status",
        "full_name",
        "contact_info",
        "customer_name",
        "work_location",
        "position_title",
        "business_line",
        "entry_date",
        "regularization_date",
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
        "leave_reason",
        "remarks",
    ]
)


_CHINESE_ROSTER_HEADER_MAP = {
    "序号": "serial_no",
    "在职情况": "employment_status",
    "姓名": "full_name",
    "联系方式": "contact_info",
    "客户": "customer_name",
    "工作地": "work_location",
    "岗位": "position_title",
    "业务线": "business_line",
    "入职日期": "entry_date",
    "入职时间": "entry_date",
    "转正时间": "regularization_date",
    "月报价(含税)": "monthly_quote_tax",
    "税前工资": "pre_tax_salary",
    "薪资报价比": "salary_quote_ratio",
    "GM$": "gms",
    "GMS": "gms",  # 旧表头兼容
    "GM%": "gm_pct",
    "员工+1": "employee_plus1",
    "入职渠道": "zntx_onboarding_channel",
    "打卡": "zntx_attendance_checkin",
    "补卡": "zntx_attendance_makeup",
    "员工+2": "employee_plus2",
    "接口": "interface_contact",
    "项目释放日期": "project_release_date",
    "项目释放时间": "project_release_date",
    "公司离职日期": "company_resign_date",
    "离职时间": "company_resign_date",
    "工号": "zntx_staff_no",
    "中诺工号": "zntx_staff_no",
    "中河工号": "zntx_staff_no",  # 兼容旧误写
    "离职类型": "zntx_separation_type",
    "补偿金": "zntx_compensation_amount",
    "离职或释放原因": "leave_reason",
    "释放成功离职原因": "leave_reason",
    "备注": "remarks",
}


# 花名册「客户」：单元格中含左侧关键字即视为右侧 clients.name（须与客户管理中全称完全一致；左侧越长越优先匹配）
ROSTER_CUSTOMER_ALIAS_RULES: Tuple[Tuple[str, str], ...] = (
    ("远景智能", "远景智能"),
    ("中诺", "中诺通讯"),
    ("华勤", "华勤科技"),
    ("帷幄", "帷幄科技"),
    ("日产", "日产中国"),
)


def _resolve_roster_customer_client(db: Session, raw: str) -> Tuple[Optional[Client], str]:
    """将简称/分子公司与 clients 表匹配；返回 (Client 或 None, 建议写入花名册的客户名字符串)。"""
    s = str(raw or "").strip()
    if not s:
        return None, ""
    exact = db.query(Client).filter(Client.name == s).first()
    if exact:
        return exact, s
    for kw, canonical in ROSTER_CUSTOMER_ALIAS_RULES:
        if kw in s:
            c = db.query(Client).filter(Client.name == canonical).first()
            if c:
                return c, canonical
    return None, s


def _contact_dedup_key(raw: Optional[str]) -> str:
    """联系方式去重键：仅保留数字，忽略空格、横线等格式差异；不以姓名为依据。"""
    if not raw:
        return ""
    digits = "".join(ch for ch in str(raw).strip() if ch.isdigit())
    return digits


def _assert_roster_contact_unique(
    db: Session,
    client_id: int,
    contact_info: str,
    exclude_row_id: Optional[int] = None,
) -> None:
    """手动新增/修改时：若联系方式（规范化后）非空，则同一客户下不得与其它行重复。"""
    ck = _contact_dedup_key(contact_info)
    if not ck:
        return
    q = db.query(RosterEntry).filter(RosterEntry.client_id == client_id)
    if exclude_row_id is not None:
        q = q.filter(RosterEntry.id != exclude_row_id)
    for e in q.all():
        if _contact_dedup_key(e.contact_info) == ck:
            raise HTTPException(
                status_code=409,
                detail="该联系方式在本客户花名册中已存在，请勿重复",
            )


def _resequence_roster_serial_no(db: Session, client_id: int) -> bool:
    """按当前行顺序重排序号为 1..N，避免删除后出现断号。"""
    rows = db.query(RosterEntry).filter(RosterEntry.client_id == client_id).order_by(RosterEntry.id).all()
    changed = False
    for idx, row in enumerate(rows, start=1):
        expected = str(idx)
        if (row.serial_no or "").strip() != expected:
            row.serial_no = expected
            changed = True
    return changed


def _resequence_roster_serial_no_all_clients(db: Session) -> bool:
    """对每个 client_id（含未匹配客户时的 0）分别将序号重排为 1..N；不在全库范围内混排。"""
    ids = [cid for (cid,) in db.query(RosterEntry.client_id).distinct().all() if cid is not None]
    changed_any = False
    for cid in ids:
        if _resequence_roster_serial_no(db, int(cid)):
            changed_any = True
    return changed_any


def _resequence_all_rosters_once() -> None:
    """服务启动时一次性修复历史断号，避免长期遗留。"""
    db = SessionLocal()
    try:
        client_ids = [cid for (cid,) in db.query(RosterEntry.client_id).distinct().all() if cid is not None]
        changed_any = False
        for cid in client_ids:
            if _resequence_roster_serial_no(db, cid):
                changed_any = True
        if changed_any:
            db.commit()
    finally:
        db.close()


def _validate_roster_business_fields(data: Dict[str, str]) -> None:
    def _normalize_amount_text(v: str) -> str:
        return re.sub(r"[¥￥,\s\u00a0]", "", str(v or "").strip())

    contact = str(data.get("contact_info", "")).strip()
    if contact and not re.fullmatch(r"\d{11}", contact):
        raise HTTPException(status_code=400, detail="联系方式必须为11位数字")

    for k, label in (("monthly_quote_tax", "月报价(含税)"), ("pre_tax_salary", "税前工资")):
        v = _normalize_amount_text(data.get(k, ""))
        if v and not re.fullmatch(r"\d{4,6}", v):
            raise HTTPException(status_code=400, detail=f"{label}必须为4-6位数字（可带逗号）")

    gm_pct = str(data.get("gm_pct", "")).strip()
    gm_pct_norm = gm_pct.replace("％", "%")
    gm_pct_with_symbol_ok = re.fullmatch(r"(100(?:\.0{1,2})?|[1-9]?\d(?:\.\d{1,2})?)%", gm_pct_norm)
    gm_pct_plain_ok = re.fullmatch(r"(100(?:\.0{1,2})?|[1-9]?\d(?:\.\d{1,2})?)", gm_pct_norm)
    if gm_pct and not (gm_pct_with_symbol_ok or gm_pct_plain_ok):
        raise HTTPException(status_code=400, detail="GM%需为0-100（如 12、12.5、12% 或 12.5%）")


def _assert_roster_contact_unique_global(
    db: Session,
    contact_info: str,
    exclude_row_id: Optional[int] = None,
) -> None:
    ck = _contact_dedup_key(contact_info)
    if not ck:
        return
    q = db.query(RosterEntry)
    if exclude_row_id is not None:
        q = q.filter(RosterEntry.id != exclude_row_id)
    for e in q.all():
        if _contact_dedup_key(e.contact_info) == ck:
            raise HTTPException(status_code=409, detail="该联系方式在整体花名册中已存在，请勿重复")


ROSTER_CREATE_REQUIRED_FIELDS = (
    "employment_status",
    "full_name",
    "contact_info",
    "customer_name",
    "work_location",
    "position_title",
    "business_line",
    "entry_date",
    "monthly_quote_tax",
    "pre_tax_salary",
    "gms",
    "gm_pct",
)


ROSTER_REQUIRED_LABELS = {
    "employment_status": "在职情况",
    "full_name": "姓名",
    "contact_info": "联系方式",
    "customer_name": "客户",
    "work_location": "工作地",
    "position_title": "岗位",
    "business_line": "业务线",
    "entry_date": "入职时间",
    "monthly_quote_tax": "月报价(含税)",
    "pre_tax_salary": "税前工资",
    "gms": "GM$",
    "gm_pct": "GM%",
}


_resequence_all_rosters_once()


def _strip_csv_header_noise(s: str) -> str:
    """去掉 BOM、零宽字符、不间断空格等，避免 Excel 导出列名与代码不一致。"""
    t = unicodedata.normalize("NFKC", str(s))
    t = t.strip().strip("\ufeff")
    t = t.replace("\u00a0", "").replace("\u3000", "")
    # 零宽空格、BOM、方向标记等格式类字符（不影响中文笔画）
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf")
    return t.strip()


def _is_gms_column_header(h: str) -> bool:
    """
    识别 GM$/GMS 列表头。Excel 导出可能使用全角＄、含不可见字符或与 GM% 混淆。
    亦兼容末位为各类「货币符号」(Sc) 的 GM 列（视觉为 $ 但码位非 U+0024）。
    """
    t = _strip_csv_header_noise(h)
    if not t:
        return False
    # 明确排除 GM% 列（含全角％）
    if t.replace(" ", "") in ("GM%", "GM％"):
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
    # GM + 末位为 $ 形符号（含 Unicode 名称含 DOLLAR 的字符）
    if len(compact) == 3 and compact[:2].upper() == "GM":
        tail = compact[2]
        if tail in ("%", "％"):
            return False
        if tail == "$" or tail in "＄﹩":
            return True
        try:
            if "DOLLAR" in unicodedata.name(tail).upper():
                return True
        except ValueError:
            pass
    return False


def _map_roster_csv_header(cell: str) -> Optional[str]:
    if cell is None:
        return None
    h = _strip_csv_header_noise(cell)
    if h in _CHINESE_ROSTER_HEADER_MAP:
        return _CHINESE_ROSTER_HEADER_MAP[h]
    if h in ROSTER_FIELD_KEYS:
        return h
    if _is_gms_column_header(h):
        return "gms"
    return None


def _decode_roster_upload_bytes(raw: bytes) -> str:
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


def _detect_csv_delimiter(first_line: str) -> str:
    """根据首行分隔符数量判断逗号/分号/制表符（Excel 区域设置不同）。"""
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
    """用 csv.reader 统计字段数（遵守引号规则，比单纯 count(',') 可靠）。"""
    try:
        row = next(csv.reader([line], delimiter=delim))
        return len(row)
    except Exception:
        return 0


def _best_csv_delimiter(first_line: str) -> str:
    """
    在逗号/分号/制表符中选能解析出最多列的分隔符，避免误用分隔符导致整行成一列、GM$ 等无法匹配。
    """
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


def _iter_roster_csv_data_rows(text: str):
    """
    用 csv.reader 按列下标与表头对齐解析（比 DictReader 更不易受异常表头影响）。
    每行 yield dict：内部字段名 -> 单元格字符串。
    """
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
            fk = _map_roster_csv_header(hcell or "")
            if fk:
                row_dict[fk] = (val or "").strip()
        yield row_dict


def _strip_excel_sep_directive(text: str) -> str:
    """部分 Excel 导出首行为 sep=; 或 sep=,，需跳过再解析表头。"""
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].strip().lower().startswith("sep="):
        return "\n".join(lines[1:])
    return text


ROSTER_EXPORT_HEADERS = [
    "序号",
    "在职情况",
    "姓名",
    "工号",
    "联系方式",
    "客户",
    "工作地",
    "岗位",
    "业务线",
    "入职日期",
    "转正时间",
    "月报价(含税)",
    "税前工资",
    "薪资报价比",
    "GM$",
    "GM%",
    "员工+1",
    "员工+2",
    "接口",
    "项目释放日期",
    "公司离职日期",
    "离职或释放原因",
    "备注",
]

ZNTX_ROSTER_EXPORT_HEADERS = [
    "序号",
    "在职情况",
    "姓名",
    "工号",
    "联系方式",
    "客户",
    "工作地",
    "岗位",
    "业务线",
    "入职时间",
    "转正时间",
    "月报价(含税)",
    "税前工资",
    "薪资报价比",
    "GM$",
    "GM%",
    "员工+1",
    "入职渠道",
    "打卡",
    "员工+2",
    "接口",
    "备注",
]


def get_host_ip():
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


# --- API 接口 (全量 CRUD) ---


@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    phases = ["初步接触", "方案/报价", "合同签订", "成交"]
    stats = {p: db.query(Client).filter(Client.phase == p).count() for p in phases}

    trash_count = 0
    trash_size = 0
    if os.path.exists(TRASH_DIR):
        for f in os.listdir(TRASH_DIR):
            fp = os.path.join(TRASH_DIR, f)
            trash_count += 1
            trash_size += os.path.getsize(fp)

    return {"funnel": stats, "trash": {"count": trash_count, "size": f"{trash_size/1024/1024:.2f} MB"}}


@app.get("/api/clients")
async def list_clients(phase: Optional[str] = None, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    query = db.query(Client)
    if phase:
        query = query.filter(Client.phase == phase)
    return query.order_by(desc(Client.created_at)).all()


@app.post("/api/clients")
async def create_client(
    name: str = Form(...),
    industry: str = Form(...),
    owner: str = Form(...),
    scale: str = Form(...),
    phase: str = Form(...),
    description: str = Form(...),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    client = Client(name=name, industry=industry, owner=owner, scale=scale, phase=phase, description=description)
    db.add(client)
    db.commit()
    db.refresh(client)
    log = AuditLog(client_id=client.id, operator=user, action=f"创建了客户: {name}")
    db.add(log)
    db.commit()
    return client


@app.get("/api/clients/{client_id}")
async def get_client(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")
    return client


@app.put("/api/clients/{client_id}")
async def update_client(
    client_id: int,
    name: str = Form(...),
    industry: str = Form(...),
    owner: str = Form(...),
    scale: str = Form(...),
    phase: str = Form(...),
    description: str = Form(...),
    remarks: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")
    duplicate = db.query(Client).filter(Client.name == name, Client.id != client_id).first()
    if duplicate:
        raise HTTPException(status_code=400, detail="客户名称已存在")

    old_name = client.name or ""
    updates = []
    if old_name != name:
        updates.append(f"客户名称从[{old_name}]变更为[{name}]")
    if client.industry != industry:
        updates.append(f"行业从[{client.industry}]变更为[{industry}]")
    if client.owner != owner:
        updates.append(f"销售负责人从[{client.owner}]变更为[{owner}]")
    if client.scale != scale:
        updates.append(f"外包规模从[{client.scale}]变更为[{scale}]")
    if client.phase != phase:
        updates.append(f"阶段从[{client.phase}]变更为[{phase}]")
    if client.description != description:
        updates.append("更新了客户描述")
    if (client.remarks or "") != (remarks or ""):
        updates.append("更新了备注信息")

    client.name = name
    client.industry = industry
    client.owner = owner
    client.scale = scale
    client.phase = phase
    client.description = description
    client.remarks = remarks or ""

    old_folder = f"{old_name}_{client_id}"
    new_folder = f"{name}_{client_id}"
    src_path = os.path.join(UPLOAD_DIR, old_folder)
    dst_path = os.path.join(UPLOAD_DIR, new_folder)
    if old_folder != new_folder and os.path.exists(src_path) and not os.path.exists(dst_path):
        shutil.move(src_path, dst_path)
        visits = db.query(VisitRecord).filter(VisitRecord.client_id == client_id).all()
        for visit in visits:
            if visit.attachment and visit.attachment.startswith(f"{old_folder}/"):
                visit.attachment = visit.attachment.replace(f"{old_folder}/", f"{new_folder}/", 1)

    if updates:
        log = AuditLog(client_id=client_id, operator=user, action="; ".join(updates))
        db.add(log)
    db.commit()
    return {"status": "ok"}


@app.delete("/api/clients/{client_id}")
async def delete_client(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    client = db.query(Client).filter(Client.id == client_id).first()
    client_folder = f"{client.name}_{client.id}"
    src_path = os.path.join(UPLOAD_DIR, client_folder)
    if os.path.exists(src_path):
        shutil.move(src_path, os.path.join(TRASH_DIR, f"{client_folder}_{int(time.time())}"))

    db.delete(client)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/clients/{client_id}/details")
async def get_details(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    visits = db.query(VisitRecord).filter(VisitRecord.client_id == client_id).all()
    logs = db.query(AuditLog).filter(AuditLog.client_id == client_id).order_by(desc(AuditLog.created_at)).all()
    return {"visits": visits, "logs": logs}


@app.post("/api/visits")
async def add_visit(
    client_id: int = Form(...),
    date: str = Form(...),
    location: str = Form(...),
    content: str = Form(...),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    folder_name = f"{client.name}_{client.id}"
    target_dir = os.path.join(UPLOAD_DIR, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    file_path = None
    if file:
        content_bytes = await file.read()
        if len(content_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="文件超过20MB限制")
        file_path = f"{folder_name}/{int(time.time())}_{file.filename}"
        with open(os.path.join(UPLOAD_DIR, file_path), "wb") as f:
            f.write(content_bytes)

    visit = VisitRecord(client_id=client_id, date=date, location=location, content=content, attachment=file_path)
    db.add(visit)
    db.commit()
    return {"status": "ok"}


@app.get("/api/export/clients")
async def export_clients(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["ID", "客户名称", "行业", "负责人", "外包规模", "开拓阶段", "创建时间"])
    clients = db.query(Client).all()
    for c in clients:
        writer.writerow([c.id, c.name, c.industry, c.owner, c.scale, c.phase, c.created_at.strftime("%Y-%m-%d")])

    response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    _set_csv_download_headers(
        response,
        chinese_filename=f"客户列表_{ts}.csv",
        ascii_base=f"clients_{ts}",
    )
    return response


@app.get("/api/clients/{client_id}/brief")
async def get_client_brief(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    return {"id": c.id, "name": c.name, "owner": c.owner or "", "phase": c.phase or ""}


@app.get("/api/roster")
async def roster_list_all(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    rows = db.query(RosterEntry).order_by(RosterEntry.id).all()
    return [_roster_entry_to_dict(r) for r in rows]


@app.post("/api/roster")
async def roster_create_row_all(
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    data = _normalize_roster_payload(body if isinstance(body, dict) else {})
    missing = [k for k in ROSTER_CREATE_REQUIRED_FIELDS if not str(data.get(k, "")).strip()]
    if missing:
        labels = [ROSTER_REQUIRED_LABELS.get(k, k) for k in missing]
        raise HTTPException(status_code=400, detail=f"新增失败，以下必填项未填写：{'、'.join(labels)}")
    _validate_roster_business_fields(data)
    _assert_roster_contact_unique_global(db, data.get("contact_info", ""))
    mc, normalized_cn = _resolve_roster_customer_client(db, data.get("customer_name", ""))
    if mc:
        data["customer_name"] = normalized_cn
    entry = RosterEntry(client_id=(mc.id if mc else 0), **data)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    db.add(AuditLog(client_id=0, operator=user, action=f"整体花名册新增一行: {data.get('full_name') or ('#' + str(entry.id))}"))
    db.commit()
    return _roster_entry_to_dict(entry)


@app.get("/api/clients/{client_id}/roster")
async def roster_list(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    rows = db.query(RosterEntry).filter(RosterEntry.client_id == client_id).order_by(RosterEntry.id).all()
    return [_roster_entry_to_dict(r) for r in rows]


@app.post("/api/clients/{client_id}/roster")
async def roster_create_row(
    client_id: int,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    data = _normalize_roster_payload(body if isinstance(body, dict) else {})
    missing = [k for k in ROSTER_CREATE_REQUIRED_FIELDS if not str(data.get(k, "")).strip()]
    if missing:
        labels = [ROSTER_REQUIRED_LABELS.get(k, k) for k in missing]
        raise HTTPException(status_code=400, detail=f"新增失败，以下必填项未填写：{'、'.join(labels)}")
    _validate_roster_business_fields(data)
    _assert_roster_contact_unique(db, client_id, data.get("contact_info", ""))
    mc, normalized_cn = _resolve_roster_customer_client(db, data.get("customer_name", ""))
    if mc:
        data["customer_name"] = normalized_cn
    entry = RosterEntry(client_id=client_id, **data)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    log = AuditLog(
        client_id=client_id,
        operator=user,
        action=f"花名册新增一行: {data.get('full_name') or ('#' + str(entry.id))}",
    )
    db.add(log)
    db.commit()
    return _roster_entry_to_dict(entry)


@app.put("/api/roster/{row_id}")
async def roster_update_row(
    row_id: int,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    entry = db.query(RosterEntry).filter(RosterEntry.id == row_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="记录不存在")
    data = _normalize_roster_payload(body if isinstance(body, dict) else {})
    _validate_roster_business_fields(data)
    mc, normalized_cn = _resolve_roster_customer_client(db, data.get("customer_name", ""))
    if mc:
        entry.client_id = mc.id
        data["customer_name"] = normalized_cn
    # 未匹配到客户时保留原 client_id，避免「客户」简称与库中全称不一致时被置为 0，从当前客户花名册中消失
    for k, v in data.items():
        setattr(entry, k, v)
    db.commit()
    db.refresh(entry)
    log = AuditLog(client_id=entry.client_id, operator=user, action=f"花名册修改行 id={row_id}")
    db.add(log)
    db.commit()
    return _roster_entry_to_dict(entry)


@app.delete("/api/roster/{row_id}")
async def roster_delete_row(row_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    entry = db.query(RosterEntry).filter(RosterEntry.id == row_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="记录不存在")
    cid = int(entry.client_id) if entry.client_id is not None else 0
    db.delete(entry)
    db.flush()
    _resequence_roster_serial_no(db, cid)
    db.commit()
    log = AuditLog(client_id=0, operator=user, action=f"整体花名册删除行 id={row_id}")
    db.add(log)
    db.commit()
    return {"status": "deleted"}


@app.post("/api/roster/import")
async def roster_import_csv_all(
    file: UploadFile = File(...),
    confirm: str = Form(""),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    def _skip_serial_hint(merged_row: Dict[str, str], csv_line_no: int) -> str:
        serial = (merged_row.get("serial_no") or "").strip()
        if serial:
            return serial
        return f"CSV第{csv_line_no}行"

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件超过大小限制")
    if str(confirm).strip().upper() != "CONFIRM":
        raise HTTPException(status_code=400, detail="导入前请确认覆盖操作（confirm=CONFIRM）")
    text = _strip_excel_sep_directive(_decode_roster_upload_bytes(raw))
    existing_rows = db.query(RosterEntry).order_by(RosterEntry.id).all()
    cleared_existing = len(existing_rows)
    backup_file = _write_roster_backup_csv_all(existing_rows) if cleared_existing else ""
    if cleared_existing:
        db.query(RosterEntry).delete()
        db.commit()

    imported = 0
    skipped_duplicates = 0
    skipped_empty = 0
    skipped_details: List[Dict[str, str]] = []
    seen_contact_keys: set = set()
    for row_index, mapped in enumerate(_iter_roster_csv_data_rows(text), start=2):
        merged = _normalize_roster_payload(mapped)
        if not any(merged.values()):
            skipped_empty += 1
            skipped_details.append({"serial_no": _skip_serial_hint(merged, row_index), "reason": "空行或全部字段为空"})
            continue
        ck = _contact_dedup_key(merged.get("contact_info", ""))
        if ck:
            if ck in seen_contact_keys:
                skipped_duplicates += 1
                skipped_details.append({"serial_no": _skip_serial_hint(merged, row_index), "reason": "联系方式重复（文件内去重）"})
                continue
            seen_contact_keys.add(ck)
        mc, normalized_cn = _resolve_roster_customer_client(db, merged.get("customer_name", ""))
        if mc:
            merged["customer_name"] = normalized_cn
        mapped_client_id = mc.id if mc else 0
        db.add(RosterEntry(client_id=mapped_client_id, **merged))
        imported += 1
    _resequence_roster_serial_no_all_clients(db)
    db.commit()
    skip_total = skipped_duplicates + skipped_empty
    skip_brief = ""
    if skip_total:
        preview = "；".join([f"{x['serial_no']}({x['reason']})" for x in skipped_details[:8]])
        skip_brief = f"；跳过 {skip_total} 行：{preview}"
        if len(skipped_details) > 8:
            skip_brief += f"；其余 {len(skipped_details) - 8} 行见导入提示"
    db.add(
        AuditLog(
            client_id=0,
            operator=user,
            action=(
                f"整体花名册 CSV 导入前备份 {cleared_existing} 行到 {backup_file or '无备份'}，"
                f"清空 {cleared_existing} 行，导入新增 {imported} 行"
                f"（文件内去重跳过 {skipped_duplicates} 行，空行跳过 {skipped_empty} 行）"
                f"{skip_brief}"
            ),
        )
    )
    db.commit()
    return {
        "cleared_existing": cleared_existing,
        "backup_file": backup_file,
        "imported": imported,
        "skipped_duplicates": skipped_duplicates,
        "skipped_empty": skipped_empty,
        "skipped_total": skip_total,
        "skipped_details": skipped_details,
    }


@app.post("/api/clients/{client_id}/roster/import")
async def roster_import_csv(
    client_id: int,
    file: UploadFile = File(...),
    confirm: str = Form(""),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    def _skip_serial_hint(merged_row: Dict[str, str], csv_line_no: int) -> str:
        serial = (merged_row.get("serial_no") or "").strip()
        if serial:
            return serial
        return f"CSV第{csv_line_no}行"

    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件超过大小限制")
    if str(confirm).strip().upper() != "CONFIRM":
        raise HTTPException(status_code=400, detail="导入前请确认覆盖操作（confirm=CONFIRM）")
    text = _strip_excel_sep_directive(_decode_roster_upload_bytes(raw))
    # 按用户要求：导入前先清空当前客户花名册，再重建导入。
    existing_rows = db.query(RosterEntry).filter(RosterEntry.client_id == client_id).order_by(RosterEntry.id).all()
    cleared_existing = len(existing_rows)
    backup_file = _write_roster_backup_csv(c, existing_rows) if cleared_existing else ""
    if cleared_existing:
        db.query(RosterEntry).filter(RosterEntry.client_id == client_id).delete()
        db.commit()

    imported = 0
    skipped_duplicates = 0
    skipped_empty = 0
    skipped_details: List[Dict[str, str]] = []
    seen_contact_keys: set = set()
    for row_index, mapped in enumerate(_iter_roster_csv_data_rows(text), start=2):
        merged = _normalize_roster_payload(mapped)
        if not any(merged.values()):
            skipped_empty += 1
            skipped_details.append({"serial_no": _skip_serial_hint(merged, row_index), "reason": "空行或全部字段为空"})
            continue
        ck = _contact_dedup_key(merged.get("contact_info", ""))
        if ck:
            if ck in seen_contact_keys:
                skipped_duplicates += 1
                skipped_details.append({"serial_no": _skip_serial_hint(merged, row_index), "reason": "联系方式重复（文件内去重）"})
                continue
            seen_contact_keys.add(ck)
        entry = RosterEntry(client_id=client_id, **merged)
        db.add(entry)
        imported += 1
    _resequence_roster_serial_no(db, client_id)
    db.commit()
    skip_total = skipped_duplicates + skipped_empty
    skip_brief = ""
    if skip_total:
        preview = "；".join([f"{x['serial_no']}({x['reason']})" for x in skipped_details[:8]])
        skip_brief = f"；跳过 {skip_total} 行：{preview}"
        if len(skipped_details) > 8:
            skip_brief += f"；其余 {len(skipped_details) - 8} 行见导入提示"
    log = AuditLog(
        client_id=client_id,
        operator=user,
        action=(
            f"花名册 CSV 导入前备份 {cleared_existing} 行到 {backup_file or '无备份'}，"
            f"清空 {cleared_existing} 行，导入新增 {imported} 行"
            f"（文件内去重跳过 {skipped_duplicates} 行，空行跳过 {skipped_empty} 行）"
            f"{skip_brief}"
        ),
    )
    db.add(log)
    if skipped_details:
        detail_lines = [f"{item['serial_no']}：{item['reason']}" for item in skipped_details]
        detail_text = "\n".join(detail_lines)
        detail_log = AuditLog(
            client_id=client_id,
            operator=user,
            action=f"花名册导入跳过明细：\n{detail_text}",
        )
        db.add(detail_log)
    db.commit()
    return {
        "cleared_existing": cleared_existing,
        "backup_file": backup_file,
        "imported": imported,
        "skipped_duplicates": skipped_duplicates,
        "skipped_empty": skipped_empty,
        "skipped_total": skip_total,
        "skipped_details": skipped_details,
    }


@app.get("/api/roster/export")
async def roster_export_csv_all(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    rows = db.query(RosterEntry).order_by(RosterEntry.id).all()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(ROSTER_EXPORT_HEADERS)
    for e in rows:
        d = _roster_entry_to_dict(e)
        line = []
        for zh in ROSTER_EXPORT_HEADERS:
            fn = _CHINESE_ROSTER_HEADER_MAP[zh]
            line.append(d.get(fn, ""))
        writer.writerow(line)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
    _set_csv_download_headers(
        response,
        chinese_filename=f"整体花名册_{ts}.csv",
        ascii_base=f"roster_all_{ts}",
    )
    return response


@app.get("/api/clients/{client_id}/roster/export")
async def roster_export_csv(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    rows = db.query(RosterEntry).filter(RosterEntry.client_id == client_id).order_by(RosterEntry.id).all()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    export_headers = ZNTX_ROSTER_EXPORT_HEADERS if c.name == "中诺通讯" else ROSTER_EXPORT_HEADERS
    writer.writerow(export_headers)
    for e in rows:
        d = _roster_entry_to_dict(e)
        line = []
        for zh in export_headers:
            fn = _CHINESE_ROSTER_HEADER_MAP[zh]
            line.append(d.get(fn, ""))
        writer.writerow(line)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    chinese_name = f"{c.name}_花名册_{ts}.csv"
    response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
    _set_csv_download_headers(
        response,
        chinese_filename=chinese_name,
        ascii_base=f"client_{client_id}_roster_{ts}",
    )
    return response


@app.post("/api/roster/restore/latest")
async def roster_restore_latest_backup_all(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    latest = _pick_latest_backup("roster_backup_all__")
    if not latest:
        raise HTTPException(status_code=404, detail="未找到整体花名册备份文件")
    backup_path = os.path.join(BACKUP_DIR, latest)
    with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    text = _strip_excel_sep_directive(text)
    cleared_existing = db.query(RosterEntry).count()
    if cleared_existing:
        db.query(RosterEntry).delete()
        db.commit()
    restored_rows = 0
    for mapped in _iter_roster_csv_data_rows(text):
        merged = _normalize_roster_payload(mapped)
        if not any(merged.values()):
            continue
        mc, normalized_cn = _resolve_roster_customer_client(db, merged.get("customer_name", ""))
        if mc:
            merged["customer_name"] = normalized_cn
        mapped_client_id = mc.id if mc else 0
        db.add(RosterEntry(client_id=mapped_client_id, **merged))
        restored_rows += 1
    _resequence_roster_serial_no_all_clients(db)
    db.commit()
    db.add(
        AuditLog(
            client_id=0,
            operator=user,
            action=f"整体花名册从备份恢复：{latest}，清空 {cleared_existing} 行，恢复 {restored_rows} 行",
        )
    )
    db.commit()
    return {"backup_file": latest, "cleared_existing": cleared_existing, "restored_rows": restored_rows}


@app.post("/api/clients/{client_id}/roster/restore/latest")
async def roster_restore_latest_backup(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    latest = _pick_latest_backup("roster_backup_", client_id=client_id)
    if not latest:
        raise HTTPException(status_code=404, detail="未找到该客户花名册备份文件")
    backup_path = os.path.join(BACKUP_DIR, latest)
    with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    text = _strip_excel_sep_directive(text)
    cleared_existing = db.query(RosterEntry).filter(RosterEntry.client_id == client_id).count()
    if cleared_existing:
        db.query(RosterEntry).filter(RosterEntry.client_id == client_id).delete()
        db.commit()
    restored_rows = 0
    for mapped in _iter_roster_csv_data_rows(text):
        merged = _normalize_roster_payload(mapped)
        if not any(merged.values()):
            continue
        db.add(RosterEntry(client_id=client_id, **merged))
        restored_rows += 1
    _resequence_roster_serial_no(db, client_id)
    db.commit()
    db.add(
        AuditLog(
            client_id=client_id,
            operator=user,
            action=f"花名册从备份恢复：{latest}，清空 {cleared_existing} 行，恢复 {restored_rows} 行",
        )
    )
    db.commit()
    return {"backup_file": latest, "cleared_existing": cleared_existing, "restored_rows": restored_rows}


@app.get("/api/roster/logs")
async def roster_logs_all(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    logs = db.query(AuditLog).filter(AuditLog.action.like("%花名册%")).order_by(desc(AuditLog.created_at)).limit(300).all()
    return logs


def _parse_loose_date(raw: str) -> Optional[Any]:
    s = str(raw or "").strip()
    if not s:
        return None
    # 保留年月日数字，兼容 2026-04-16 / 2026/4/16 / 2026年4月16日 等常见格式。
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", s)
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2))
    d = int(m.group(3))
    try:
        return datetime(y, mo, d).date()
    except Exception:
        return None


def _week_label_from_date(d: Any) -> str:
    # 口径：周一到周日；例如 3/30-4/5 记作 4m1w（按该周周四所在月份归属）
    monday_start = d - timedelta(days=d.weekday())
    week_anchor = monday_start + timedelta(days=3)  # Thursday anchor
    target_month = int(week_anchor.month)
    target_year = int(week_anchor.year)
    first_day = datetime(target_year, target_month, 1).date()
    cursor = first_day - timedelta(days=first_day.weekday())
    while int((cursor + timedelta(days=3)).month) != target_month:
        cursor += timedelta(days=7)
    week_no = ((monday_start - cursor).days // 7) + 1
    return f"{target_month}w{week_no}"


def _period_sort_key(period: str) -> tuple:
    s = str(period or "").strip()
    if not s:
        return (999, 999, "")
    m1 = re.match(r"^\s*(\d{1,2})\s*m\s*(\d{1,2})\s*w\s*$", s, re.IGNORECASE)
    if m1:
        return (int(m1.group(1)), int(m1.group(2)), s)
    # 兼容类似 4w3 的历史写法：按 4月第3周 解释
    m2 = re.match(r"^\s*(\d{1,2})\s*w\s*(\d{1,2})\s*$", s, re.IGNORECASE)
    if m2:
        return (int(m2.group(1)), int(m2.group(2)), s)
    return (999, 999, s)


def _extract_period_month(period: str) -> Optional[int]:
    s = str(period or "").strip()
    m1 = re.match(r"^\s*(\d{1,2})\s*m", s, re.IGNORECASE)
    if m1:
        return int(m1.group(1))
    m2 = re.match(r"^\s*(\d{1,2})\s*w", s, re.IGNORECASE)
    if m2:
        return int(m2.group(1))
    m3 = re.search(r"(\d{1,2})\s*月", s)
    if m3:
        return int(m3.group(1))
    return None


def _normalize_period_label(period: str) -> str:
    """统一周期标签为 XwY，兼容 4W3 / 4w3 / 4m3w 等写法。"""
    s = str(period or "").strip()
    if not s:
        return ""
    m1 = re.match(r"^\s*(\d{1,2})\s*m\s*(\d{1,2})\s*w\s*$", s, re.IGNORECASE)
    if m1:
        return f"{int(m1.group(1))}w{int(m1.group(2))}"
    m2 = re.match(r"^\s*(\d{1,2})\s*w\s*(\d{1,2})\s*$", s, re.IGNORECASE)
    if m2:
        return f"{int(m2.group(1))}w{int(m2.group(2))}"
    return s


@app.get("/api/clients/{client_id}/delivery/pipeline/insight")
async def pipeline_insight(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    demand_rows = (
        db.query(DeliveryPipelineInsightDemand)
        .filter(DeliveryPipelineInsightDemand.client_id == client_id)
        .all()
    )
    demand_map = {
        (
            str(item.period or "").strip(),
            str(item.position or "").strip(),
            str(item.region or "").strip(),
        ): str(item.demand_qty or "").strip()
        for item in demand_rows
    }
    rows = (
        db.query(DeliveryPipelineEntry)
        .filter(DeliveryPipelineEntry.client_id == client_id)
        .order_by(DeliveryPipelineEntry.id)
        .all()
    )
    today = datetime.now().date()
    grouped: Dict[tuple, Dict[str, Any]] = {}
    inner_fail_counts: Dict[tuple, int] = {}
    weekly_onboard_counts: Dict[tuple, int] = {}
    weekly_in_transit_counts: Dict[tuple, int] = {}
    weekly_in_transit_loss_counts: Dict[tuple, int] = {}
    anomalies: List[Dict[str, str]] = []
    for e in rows:
        period = _normalize_period_label(str(e.date or "").strip())
        position = str(e.position or "").strip()
        region = str(e.region or "").strip()
        if not period or not position:
            continue
        key = (period, position, region)
        if key not in grouped:
            grouped[key] = {
                "时间": period,
                "岗位": position,
                "需求数量": "",
                "地点": region,
                "推送简历量": 0,
                "内筛通过": 0,
                "重复": 0,
                "待客户筛选": 0,
                "客筛通过": 0,
                "放弃面试": 0,
                "待面试": 0,
                "已面试": 0,
                "面试通过": 0,
                "本周offer人数": 0,
                "弃offer/谈薪失败": 0,
                "在途人数/待入职": 0,
                "月度在途流失(包含前序)": 0,
                "本周入职人数": 0,
                "本月入职人数": 0,
            }
            inner_fail_counts[key] = 0
        item = grouped[key]
        item["推送简历量"] += 1
        resume_screening = str(e.resume_screening or "").strip()
        interviewed = str(e.interviewed or "").strip()
        interview_time = str(e.interview_time or "").strip()
        result = str(e.result or "").strip()
        got_offer = str(e.got_offer or "").strip()
        onboarded = str(e.onboarded or "").strip()
        onboarding_date = _parse_loose_date(str(e.onboarding_time or "").strip())

        if resume_screening == "友商重复":
            item["重复"] += 1
        # 口径调整：内筛不通过仅统计“简历筛选=内筛不通过”，不包含“友商重复”。
        if resume_screening == "内筛不通过":
            inner_fail_counts[key] = int(inner_fail_counts.get(key, 0)) + 1
        if resume_screening == "待反馈":
            item["待客户筛选"] += 1
        if resume_screening == "通过":
            item["客筛通过"] += 1
        if interviewed == "放弃":
            item["放弃面试"] += 1
        if interviewed == "约面":
            item["待面试"] += 1
        if interviewed == "是" and interview_time:
            item["已面试"] += 1
        if interviewed == "是" and not interview_time:
            anomalies.append(
                {
                    "row_id": int(e.id),
                    "姓名": str(e.full_name or "").strip() or "-",
                    "问题": "是否面试=是，但面试时间为空",
                    "时间": period,
                    "岗位": position,
                    "地点": region,
                }
            )
        if result == "通过":
            item["面试通过"] += 1
            if interviewed != "是":
                anomalies.append(
                    {
                        "row_id": int(e.id),
                        "姓名": str(e.full_name or "").strip() or "-",
                        "问题": "面试结果=通过，但是否面试不为“是”",
                        "时间": period,
                        "岗位": position,
                        "地点": region,
                    }
                )
        if got_offer in ("是", "否") and result != "通过":
            anomalies.append(
                {
                    "row_id": int(e.id),
                    "姓名": str(e.full_name or "").strip() or "-",
                    "问题": "是否接offer已填写，但面试结果不为“通过”",
                    "时间": period,
                    "岗位": position,
                    "地点": region,
                }
            )
        if got_offer == "是":
            item["本周offer人数"] += 1
        if got_offer == "否":
            item["弃offer/谈薪失败"] += 1
        if onboarded == "放弃入职":
            if onboarding_date:
                loss_week = _week_label_from_date(onboarding_date)
                loss_key = (loss_week, position, region)
                weekly_in_transit_loss_counts[loss_key] = int(weekly_in_transit_loss_counts.get(loss_key, 0)) + 1
            else:
                anomalies.append(
                    {
                        "row_id": int(e.id),
                        "姓名": str(e.full_name or "").strip() or "-",
                        "问题": "状态为放弃入职，但入职时间为空或无法解析",
                        "时间": period,
                        "岗位": position,
                        "地点": region,
                    }
                )
        if "待入职" in onboarded and onboarding_date and onboarding_date <= today:
            anomalies.append(
                {
                    "row_id": int(e.id),
                    "姓名": str(e.full_name or "").strip() or "-",
                    "问题": "状态为待入职，但入职时间未晚于今天",
                    "时间": period,
                    "岗位": position,
                    "地点": region,
                }
            )
        elif "待入职" in onboarded and not onboarding_date:
            m_wait = re.search(r"(\d{1,2})\s*月\s*待入职", onboarded)
            if m_wait:
                anomalies.append(
                    {
                        "row_id": int(e.id),
                        "姓名": str(e.full_name or "").strip() or "-",
                        "问题": "状态为待入职，但待入职月份早于当前月份",
                        "时间": period,
                        "岗位": position,
                        "地点": region,
                    }
                )
        is_waiting_text = bool(re.fullmatch(r"\s*\d{1,2}\s*月\s*待入职\s*", onboarded))
        if is_waiting_text and onboarding_date and onboarding_date > today:
            waiting_week = _week_label_from_date(onboarding_date)
            waiting_key = (waiting_week, position, region)
            weekly_in_transit_counts[waiting_key] = int(weekly_in_transit_counts.get(waiting_key, 0)) + 1
        if "已入职" in onboarded and not onboarding_date:
            anomalies.append(
                {
                    "row_id": int(e.id),
                    "姓名": str(e.full_name or "").strip() or "-",
                    "问题": "状态为已入职，但入职时间为空或无法解析",
                    "时间": period,
                    "岗位": position,
                    "地点": region,
                }
            )
        if onboarding_date and ("已入职" in onboarded):
            onboard_week = _week_label_from_date(onboarding_date)
            onboard_key = (onboard_week, position, region)
            weekly_onboard_counts[onboard_key] = int(weekly_onboard_counts.get(onboard_key, 0)) + 1
        period_month = _extract_period_month(period)
        if period_month is not None:
            if re.search(rf"{int(period_month)}\s*月\s*已入职", onboarded):
                item["本月入职人数"] += 1

    supplemental_keys: Dict[tuple, bool] = {}
    for k, cnt in weekly_onboard_counts.items():
        if cnt > 0:
            supplemental_keys[k] = True
    for k, cnt in weekly_in_transit_counts.items():
        if cnt > 0:
            supplemental_keys[k] = True
    for k, cnt in weekly_in_transit_loss_counts.items():
        if cnt > 0:
            supplemental_keys[k] = True

    # 若“周+岗位+地点”有入职/在途/在途流失统计但该周无推荐分组行，则补一条该岗位明细行承载统计。
    for (onboard_week, onboard_pos, onboard_region) in supplemental_keys.keys():
        synthetic_key = (onboard_week, onboard_pos, onboard_region)
        if synthetic_key in grouped:
            continue
        grouped[synthetic_key] = {
            "时间": onboard_week,
            "岗位": onboard_pos,
            "需求数量": "",
            "地点": onboard_region,
            "推送简历量": 0,
            "内筛通过": 0,
            "重复": 0,
            "待客户筛选": 0,
            "客筛通过": 0,
            "放弃面试": 0,
            "待面试": 0,
            "已面试": 0,
            "面试通过": 0,
            "本周offer人数": 0,
            "弃offer/谈薪失败": 0,
            "在途人数/待入职": 0,
            "月度在途流失(包含前序)": 0,
            "本周入职人数": 0,
            "本月入职人数": 0,
        }
        inner_fail_counts[synthetic_key] = 0

    out = list(grouped.values())
    for item in out:
        key = (item["时间"], item["岗位"], item["地点"])
        inner_fail = int(inner_fail_counts.get(key, 0))
        item["内筛通过"] = max(0, int(item["推送简历量"]) - inner_fail)
        period_norm = _normalize_period_label(str(item.get("时间", "") or "").strip())
        pos = str(item.get("岗位", "") or "").strip()
        region = str(item.get("地点", "") or "").strip()
        onboard_key = (period_norm, pos, region)
        item["本周入职人数"] = int(weekly_onboard_counts.get(onboard_key, 0))
        item["在途人数/待入职"] = int(weekly_in_transit_counts.get(onboard_key, 0))
        item["月度在途流失(包含前序)"] = int(weekly_in_transit_loss_counts.get(onboard_key, 0))
        item["需求数量"] = demand_map.get(key, "")
    out.sort(
        key=lambda x: (
            _period_sort_key(str(x.get("时间", ""))),
            str(x.get("岗位", "")),
            str(x.get("地点", "")),
        ),
        reverse=True,
    )
    return {"rows": out, "anomalies": anomalies}


@app.put("/api/clients/{client_id}/delivery/pipeline/insight-demand")
async def pipeline_insight_update_demand(
    client_id: int,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    data = _normalize_pipeline_insight_demand_payload(body if isinstance(body, dict) else {})
    period = data["period"]
    position = data["position"]
    region = data["region"]
    if not period or not position:
        raise HTTPException(status_code=400, detail="时间和岗位不能为空")
    entry = (
        db.query(DeliveryPipelineInsightDemand)
        .filter(DeliveryPipelineInsightDemand.client_id == client_id)
        .filter(DeliveryPipelineInsightDemand.period == period)
        .filter(DeliveryPipelineInsightDemand.position == position)
        .filter(DeliveryPipelineInsightDemand.region == region)
        .first()
    )
    demand_qty = data["demand_qty"]
    if entry:
        if demand_qty:
            entry.demand_qty = demand_qty
        else:
            db.delete(entry)
    elif demand_qty:
        db.add(
            DeliveryPipelineInsightDemand(
                client_id=client_id,
                period=period,
                position=position,
                region=region,
                demand_qty=demand_qty,
            )
        )
    db.commit()
    return {"status": "ok", "demand_qty": demand_qty}


@app.get("/api/clients/{client_id}/delivery/pipeline")
async def pipeline_list(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    rows = db.query(DeliveryPipelineEntry).filter(DeliveryPipelineEntry.client_id == client_id).all()
    row_dicts = [_pipeline_entry_to_dict(r) for r in rows]
    row_dicts.sort(
        key=lambda x: (
            _period_sort_key(str(x.get("date", ""))),
            int(x.get("id", 0) or 0),
        ),
        reverse=True,
    )
    return row_dicts


@app.post("/api/clients/{client_id}/delivery/pipeline")
async def pipeline_create_row(
    client_id: int,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    data = _normalize_pipeline_payload(body if isinstance(body, dict) else {})
    max_row = (
        db.query(DeliveryPipelineEntry)
        .filter(DeliveryPipelineEntry.client_id == client_id)
        .order_by(desc(DeliveryPipelineEntry.id))
        .first()
    )
    if max_row and str(max_row.serial_no or "").isdigit():
        data["serial_no"] = str(int(max_row.serial_no) + 1)
    else:
        data["serial_no"] = "1"
    entry = DeliveryPipelineEntry(client_id=client_id, **data)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    db.add(AuditLog(client_id=client_id, operator=user, action=f"管道数据新增行 id={entry.id}"))
    db.commit()
    return _pipeline_entry_to_dict(entry)


@app.put("/api/delivery/pipeline/row/{row_id}")
async def pipeline_update_row(
    row_id: int,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    entry = db.query(DeliveryPipelineEntry).filter(DeliveryPipelineEntry.id == row_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="记录不存在")
    data = _normalize_pipeline_payload(body if isinstance(body, dict) else {})
    for k, v in data.items():
        if k == "serial_no":
            continue
        setattr(entry, k, v)
    db.commit()
    db.refresh(entry)
    db.add(AuditLog(client_id=entry.client_id, operator=user, action=f"管道数据修改行 id={row_id}"))
    db.commit()
    return _pipeline_entry_to_dict(entry)


@app.delete("/api/delivery/pipeline/row/{row_id}")
async def pipeline_delete_row(row_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    entry = db.query(DeliveryPipelineEntry).filter(DeliveryPipelineEntry.id == row_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="记录不存在")
    cid = entry.client_id
    db.delete(entry)
    db.flush()
    _resequence_pipeline_serial_no(db, cid)
    db.commit()
    db.add(AuditLog(client_id=cid, operator=user, action=f"管道数据删除行 id={row_id}"))
    db.commit()
    return {"status": "deleted"}


@app.post("/api/clients/{client_id}/delivery/pipeline/import")
async def pipeline_import_csv(
    client_id: int,
    file: UploadFile = File(...),
    confirm: str = Form(""),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件超过大小限制")
    if str(confirm).strip().upper() != "CONFIRM":
        raise HTTPException(status_code=400, detail="导入前请确认覆盖操作（confirm=CONFIRM）")
    text = _strip_excel_sep_directive(_decode_roster_upload_bytes(raw))
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV 缺少表头，无法导入")

    def _norm_header(h: str) -> str:
        return str(h or "").replace("\ufeff", "").replace(" ", "").replace("\u3000", "").strip().lower()

    header_alias = {
        "姓名": "full_name",
        "候选人": "full_name",
        "候选人姓名": "full_name",
        "工作地": "region",
        "地区": "region",
        "城市": "region",
        "手机号": "phone",
        "联系电话": "phone",
        "工作年限": "years_experience",
        "经验年限": "years_experience",
        "筛选结果": "resume_screening",
        "简历筛选结果": "resume_screening",
        "是否拿offer": "got_offer",
        "是否接offer": "got_offer",
        "是否拿到offer": "got_offer",
        "拿offer": "got_offer",
        "状态": "status_note",
        "备注": "status_note",
        "面试结果": "result",
    }
    norm_map = {_norm_header(hk): fk for hk, fk in PIPELINE_HEADER_MAP.items()}
    for alias_hk, fk in header_alias.items():
        norm_map[_norm_header(alias_hk)] = fk

    matched_columns = {}
    for original_h in reader.fieldnames:
        fk = norm_map.get(_norm_header(original_h))
        if fk and fk not in matched_columns:
            matched_columns[fk] = original_h

    matched_non_serial = [k for k in matched_columns.keys() if k != "serial_no"]
    if not matched_non_serial:
        raise HTTPException(
            status_code=400,
            detail=f"CSV 表头未匹配到管道数据字段（仅匹配到序号或未匹配）。检测到表头: {', '.join([str(h or '') for h in reader.fieldnames])}",
        )

    pending_rows: List[Dict[str, str]] = []
    total_rows = 0
    skipped_empty_rows = 0
    skipped_empty_row_numbers: List[int] = []
    for row in reader:
        total_rows += 1
        csv_line_no = total_rows + 1  # +1 for header line
        mapped = {fk: "" for fk in PIPELINE_HEADER_MAP.values()}
        for fk, original_h in matched_columns.items():
            mapped[fk] = str(row.get(original_h, "") or "").strip()
        mapped["serial_no"] = ""
        if not any(mapped.get(k, "") for k in matched_non_serial):
            skipped_empty_rows += 1
            if len(skipped_empty_row_numbers) < 20:
                skipped_empty_row_numbers.append(csv_line_no)
            continue

        pending_rows.append(mapped)

    existing_rows = (
        db.query(DeliveryPipelineEntry)
        .filter(DeliveryPipelineEntry.client_id == client_id)
        .order_by(DeliveryPipelineEntry.id)
        .all()
    )
    cleared_existing = len(existing_rows)
    backup_file = _write_pipeline_backup_csv(c, existing_rows) if cleared_existing else ""
    if cleared_existing:
        db.query(DeliveryPipelineEntry).filter(DeliveryPipelineEntry.client_id == client_id).delete()
        db.commit()

    imported = 0
    for mapped in pending_rows:
        entry = DeliveryPipelineEntry(client_id=client_id, **mapped)
        db.add(entry)
        imported += 1
    _resequence_pipeline_serial_no(db, client_id)
    db.commit()
    db.add(
        AuditLog(
            client_id=client_id,
            operator=user,
            action=(
                f"管道数据 CSV 导入前备份 {cleared_existing} 行到 {backup_file or '无备份'}，"
                f"清空 {cleared_existing} 行，CSV 总行数 {total_rows}，"
                f"空行跳过 {skipped_empty_rows}，导入新增 {imported} 行"
            ),
        )
    )
    db.commit()
    return {
        "cleared_existing": cleared_existing,
        "backup_file": backup_file,
        "imported": imported,
        "total_rows": total_rows,
        "skipped_empty_rows": skipped_empty_rows,
        "skipped_rows": skipped_empty_rows,
        "skipped_empty_row_numbers_preview": skipped_empty_row_numbers,
        "skipped_empty_row_numbers_truncated": skipped_empty_rows > len(skipped_empty_row_numbers),
        "matched_columns_count": len(matched_non_serial),
        "matched_columns": sorted(matched_non_serial),
    }


@app.post("/api/delivery/pipeline/import")
async def pipeline_import_csv_global(
    client_id: int = Form(...),
    file: UploadFile = File(...),
    confirm: str = Form(""),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    return await pipeline_import_csv(
        client_id=client_id,
        file=file,
        confirm=confirm,
        db=db,
        user=user,
    )


@app.get("/api/clients/{client_id}/delivery/pipeline/export")
async def pipeline_export_csv(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    rows = (
        db.query(DeliveryPipelineEntry)
        .filter(DeliveryPipelineEntry.client_id == client_id)
        .order_by(DeliveryPipelineEntry.id)
        .all()
    )
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(PIPELINE_EXPORT_HEADERS)
    for e in rows:
        d = _pipeline_entry_to_dict(e)
        writer.writerow([d.get(PIPELINE_HEADER_MAP[h], "") for h in PIPELINE_EXPORT_HEADERS])
    response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    _set_csv_download_headers(
        response,
        chinese_filename=f"{c.name}_管道数据_{ts}.csv",
        ascii_base=f"client_{client_id}_pipeline_{ts}",
    )
    return response


@app.get("/api/clients/{client_id}/delivery/pipeline/logs")
async def pipeline_logs(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.client_id == client_id)
        .filter(AuditLog.action.like("管道数据%"))
        .order_by(desc(AuditLog.created_at))
        .all()
    )
    return logs


@app.post("/api/clients/{client_id}/delivery/pipeline/restore/latest")
async def pipeline_restore_latest_backup(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    latest = _pick_latest_backup("pipeline_backup_", client_id=client_id)
    if not latest:
        raise HTTPException(status_code=404, detail="未找到该客户管道数据备份文件")
    backup_path = os.path.join(BACKUP_DIR, latest)
    with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    cleared_existing = db.query(DeliveryPipelineEntry).filter(DeliveryPipelineEntry.client_id == client_id).count()
    if cleared_existing:
        db.query(DeliveryPipelineEntry).filter(DeliveryPipelineEntry.client_id == client_id).delete()
        db.commit()
    restored_rows = 0
    for row in rows:
        mapped = {fk: "" for fk in set(PIPELINE_HEADER_MAP.values())}
        for hk, fk in PIPELINE_HEADER_MAP.items():
            cell = str(row.get(hk, "") or "").strip()
            if cell:
                mapped[fk] = cell
        mapped["serial_no"] = ""
        if not any(mapped.values()):
            continue
        db.add(DeliveryPipelineEntry(client_id=client_id, **mapped))
        restored_rows += 1
    _resequence_pipeline_serial_no(db, client_id)
    db.commit()
    db.add(
        AuditLog(
            client_id=client_id,
            operator=user,
            action=f"管道数据从备份恢复：{latest}，清空 {cleared_existing} 行，恢复 {restored_rows} 行",
        )
    )
    db.commit()
    return {"backup_file": latest, "cleared_existing": cleared_existing, "restored_rows": restored_rows}


@app.get("/api/clients/{client_id}/delivery/interviews")
async def interview_list(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    rows = (
        db.query(DeliveryInterviewEntry)
        .filter(DeliveryInterviewEntry.client_id == client_id)
        .order_by(DeliveryInterviewEntry.id)
        .all()
    )
    return [_interview_entry_to_dict(r) for r in rows]


@app.post("/api/clients/{client_id}/delivery/interviews")
async def interview_create_row(
    client_id: int,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    data = _normalize_interview_payload(body if isinstance(body, dict) else {})
    max_row = (
        db.query(DeliveryInterviewEntry)
        .filter(DeliveryInterviewEntry.client_id == client_id)
        .order_by(desc(DeliveryInterviewEntry.id))
        .first()
    )
    if max_row and str(max_row.serial_no or "").isdigit():
        data["serial_no"] = str(int(max_row.serial_no) + 1)
    else:
        data["serial_no"] = "1"
    entry = DeliveryInterviewEntry(client_id=client_id, **data)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    db.add(AuditLog(client_id=client_id, operator=user, action=f"员工访谈新增行 id={entry.id}"))
    db.commit()
    return _interview_entry_to_dict(entry)


@app.put("/api/delivery/interviews/row/{row_id}")
async def interview_update_row(
    row_id: int,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    entry = db.query(DeliveryInterviewEntry).filter(DeliveryInterviewEntry.id == row_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="记录不存在")
    data = _normalize_interview_payload(body if isinstance(body, dict) else {})
    for k, v in data.items():
        if k == "serial_no":
            continue
        setattr(entry, k, v)
    db.commit()
    db.refresh(entry)
    db.add(AuditLog(client_id=entry.client_id, operator=user, action=f"员工访谈修改行 id={row_id}"))
    db.commit()
    return _interview_entry_to_dict(entry)


@app.delete("/api/delivery/interviews/row/{row_id}")
async def interview_delete_row(row_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    entry = db.query(DeliveryInterviewEntry).filter(DeliveryInterviewEntry.id == row_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="记录不存在")
    cid = entry.client_id
    db.delete(entry)
    db.flush()
    _resequence_interview_serial_no(db, cid)
    db.commit()
    db.add(AuditLog(client_id=cid, operator=user, action=f"员工访谈删除行 id={row_id}"))
    db.commit()
    return {"status": "deleted"}


@app.post("/api/clients/{client_id}/delivery/interviews/import")
async def interview_import_csv(
    client_id: int,
    file: UploadFile = File(...),
    confirm: str = Form(""),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件超过大小限制")
    if str(confirm).strip().upper() != "CONFIRM":
        raise HTTPException(status_code=400, detail="导入前请确认覆盖操作（confirm=CONFIRM）")
    text = _strip_excel_sep_directive(_decode_roster_upload_bytes(raw))
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV 缺少表头，无法导入")

    def _norm_header(h: str) -> str:
        # 兼容 Excel 导出的 BOM、零宽字符、换行、全角空格等脏表头
        s = _strip_csv_header_noise(h)
        s = re.sub(r"\s+", "", s)
        for plus_ch in ("\uff0b", "\u2795", "\u229e", "\u208a"):
            s = s.replace(plus_ch, "+")
        return s.strip().lower()

    header_alias = {
        "姓名": "full_name",
        "被访谈人": "full_name",
        "候选人": "full_name",
        "面谈日期": "interview_date",
        "访谈时间": "interview_date",
        "日期": "interview_date",
        "时间": "interview_date",
        "业务部门": "project_name",
        "项目组": "project_name",
        "项目": "project_name",
        "分部": "project_name",
        "工种": "position",
        "职务": "position",
        "手机号": "contact",
        "电话": "contact",
        "手机": "contact",
        "司龄天数": "days_since_onboarding",
        "入职日": "onboarding_time",
        "访谈内容": "interview_content",
        "谈话内容": "interview_content",
        "面谈记录": "interview_content",
        "内容": "interview_content",
        "记录": "interview_content",
        "摘要": "interview_content",
        "状态": "employment_status",
        "籍贯": "hometown",
        "地点": "work_location",
        "城市": "work_location",
        "改进措施": "delivery_todos",
        "待办事项": "delivery_todos",
        "1d": "followup_1d",
        "7d": "followup_7d",
        "30d": "followup_30d",
        "90d": "followup_90d",
    }
    norm_map: Dict[str, str] = {}
    for hk, fk in INTERVIEW_HEADER_MAP.items():
        norm_map[_norm_header(hk)] = fk
    for alias_hk, fk in header_alias.items():
        norm_map[_norm_header(alias_hk)] = fk

    matched_columns: Dict[str, str] = {}
    for original_h in reader.fieldnames:
        normalized_h = _norm_header(original_h)
        fk = norm_map.get(normalized_h)
        if not fk:
            # 「员工加1」这一列在不同模板里偶发携带换行/隐藏字符/变体写法，做额外兜底
            if ("员工" in normalized_h and "1" in normalized_h and any(token in normalized_h for token in ("加", "+", "q"))):
                fk = "employee_q1"
        if fk and fk not in matched_columns:
            matched_columns[fk] = original_h

    matched_non_serial = [k for k in matched_columns.keys() if k != "serial_no"]
    if not matched_non_serial:
        raise HTTPException(
            status_code=400,
            detail=(
                "CSV 表头未匹配到员工访谈字段（仅匹配到序号或未匹配）。检测到表头: "
                + ", ".join([str(h or "") for h in reader.fieldnames])
            ),
        )

    interview_fk_set = set(INTERVIEW_HEADER_MAP.values())

    pending_rows: List[Dict[str, str]] = []
    total_rows = 0
    skipped_empty_rows = 0
    skipped_empty_row_numbers: List[int] = []
    for row in reader:
        total_rows += 1
        csv_line_no = total_rows + 1
        mapped = {fk: "" for fk in interview_fk_set}
        for fk, original_h in matched_columns.items():
            mapped[fk] = str(row.get(original_h, "") or "").strip()
        mapped["serial_no"] = ""
        if not any(mapped.get(k, "") for k in matched_non_serial):
            skipped_empty_rows += 1
            if len(skipped_empty_row_numbers) < 20:
                skipped_empty_row_numbers.append(csv_line_no)
            continue
        pending_rows.append(mapped)

    existing_rows = (
        db.query(DeliveryInterviewEntry)
        .filter(DeliveryInterviewEntry.client_id == client_id)
        .order_by(DeliveryInterviewEntry.id)
        .all()
    )
    cleared_existing = len(existing_rows)
    backup_file = _write_interview_backup_csv(c, existing_rows) if cleared_existing else ""
    if cleared_existing:
        db.query(DeliveryInterviewEntry).filter(DeliveryInterviewEntry.client_id == client_id).delete()
        db.commit()

    imported = 0
    for mapped in pending_rows:
        entry = DeliveryInterviewEntry(client_id=client_id, **mapped)
        db.add(entry)
        imported += 1
    _resequence_interview_serial_no(db, client_id)
    db.commit()
    db.add(
        AuditLog(
            client_id=client_id,
            operator=user,
            action=(
                f"员工访谈 CSV 导入前备份 {cleared_existing} 行到 {backup_file or '无备份'}，"
                f"清空 {cleared_existing} 行，CSV 总行数 {total_rows}，"
                f"空行跳过 {skipped_empty_rows}，导入新增 {imported} 行"
            ),
        )
    )
    db.commit()
    return {
        "cleared_existing": cleared_existing,
        "backup_file": backup_file,
        "imported": imported,
        "total_rows": total_rows,
        "skipped_empty_rows": skipped_empty_rows,
        "skipped_rows": skipped_empty_rows,
        "skipped_empty_row_numbers_preview": skipped_empty_row_numbers,
        "skipped_empty_row_numbers_truncated": skipped_empty_rows > len(skipped_empty_row_numbers),
        "matched_columns_count": len(matched_non_serial),
        "matched_columns": sorted(matched_non_serial),
    }


@app.post("/api/delivery/interviews/import")
async def interview_import_csv_global(
    client_id: int = Form(...),
    file: UploadFile = File(...),
    confirm: str = Form(""),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    return await interview_import_csv(
        client_id=client_id,
        file=file,
        confirm=confirm,
        db=db,
        user=user,
    )


@app.get("/api/clients/{client_id}/delivery/interviews/export")
async def interview_export_csv(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    rows = (
        db.query(DeliveryInterviewEntry)
        .filter(DeliveryInterviewEntry.client_id == client_id)
        .order_by(DeliveryInterviewEntry.id)
        .all()
    )
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(INTERVIEW_EXPORT_HEADERS)
    for sn, e in _interview_display_serial_pairs(rows):
        d = _interview_entry_to_dict(e)
        cells = [str(sn)] + [d.get(INTERVIEW_HEADER_MAP[h], "") for h in INTERVIEW_EXPORT_HEADERS[1:]]
        writer.writerow(cells)
    response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    _set_csv_download_headers(
        response,
        chinese_filename=f"{c.name}_员工访谈_{ts}.csv",
        ascii_base=f"client_{client_id}_interviews_{ts}",
    )
    return response


@app.get("/api/clients/{client_id}/delivery/interviews/logs")
async def interview_logs(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.client_id == client_id)
        .filter(AuditLog.action.like("员工访谈%"))
        .order_by(desc(AuditLog.created_at))
        .all()
    )
    return logs


@app.post("/api/clients/{client_id}/delivery/interviews/restore/latest")
async def interview_restore_latest_backup(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    latest = _pick_latest_backup("interview_backup_", client_id=client_id)
    if not latest:
        raise HTTPException(status_code=404, detail="未找到该客户员工访谈备份文件")
    backup_path = os.path.join(BACKUP_DIR, latest)
    with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    cleared_existing = db.query(DeliveryInterviewEntry).filter(DeliveryInterviewEntry.client_id == client_id).count()
    if cleared_existing:
        db.query(DeliveryInterviewEntry).filter(DeliveryInterviewEntry.client_id == client_id).delete()
        db.commit()
    restored_rows = 0
    for row in rows:
        mapped = {fk: "" for fk in set(INTERVIEW_HEADER_MAP.values())}
        for hk, fk in INTERVIEW_HEADER_MAP.items():
            cell = str(row.get(hk, "") or "").strip()
            if cell:
                mapped[fk] = cell
        mapped["serial_no"] = ""
        if not any(mapped.values()):
            continue
        db.add(DeliveryInterviewEntry(client_id=client_id, **mapped))
        restored_rows += 1
    _resequence_interview_serial_no(db, client_id)
    db.commit()
    db.add(
        AuditLog(
            client_id=client_id,
            operator=user,
            action=f"员工访谈从备份恢复：{latest}，清空 {cleared_existing} 行，恢复 {restored_rows} 行",
        )
    )
    db.commit()
    return {"backup_file": latest, "cleared_existing": cleared_existing, "restored_rows": restored_rows}


@app.get("/api/delivery/settlement")
async def settlement_list(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    rows = db.query(DeliverySettlementEntry).order_by(DeliverySettlementEntry.id).all()
    return [_settlement_entry_to_dict(r) for r in rows]


@app.post("/api/delivery/settlement")
async def settlement_create_row(
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    data = _normalize_settlement_payload(body if isinstance(body, dict) else {})
    _validate_settlement_payload(data)
    client_id = _resolve_settlement_client_id(db, data.get("customer_name", ""), require_existing=False)
    max_id_row = db.query(DeliverySettlementEntry).order_by(desc(DeliverySettlementEntry.id)).first()
    if max_id_row and str(max_id_row.serial_no or "").isdigit():
        data["serial_no"] = str(int(max_id_row.serial_no) + 1)
    else:
        data["serial_no"] = "1"
    entry = DeliverySettlementEntry(client_id=client_id, **data)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    db.add(AuditLog(client_id=client_id or 0, operator=user, action=f"结算回款新增: {data.get('customer_name', '')}"))
    db.commit()
    return _settlement_entry_to_dict(entry)


@app.put("/api/delivery/settlement/row/{row_id}")
async def settlement_update_row(
    row_id: int,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    entry = db.query(DeliverySettlementEntry).filter(DeliverySettlementEntry.id == row_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="记录不存在")
    data = _normalize_settlement_payload(body if isinstance(body, dict) else {})
    _validate_settlement_payload(data)
    entry.client_id = _resolve_settlement_client_id(db, data.get("customer_name", ""), require_existing=False)
    for k, v in data.items():
        if k == "serial_no":
            continue
        setattr(entry, k, v)
    db.commit()
    db.refresh(entry)
    db.add(AuditLog(client_id=entry.client_id or 0, operator=user, action=f"结算回款修改行 id={row_id}"))
    db.commit()
    return _settlement_entry_to_dict(entry)


@app.delete("/api/delivery/settlement/row/{row_id}")
async def settlement_delete_row(row_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    entry = db.query(DeliverySettlementEntry).filter(DeliverySettlementEntry.id == row_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="记录不存在")
    cid = entry.client_id or 0
    db.delete(entry)
    db.flush()
    _resequence_settlement_serial_no_all(db)
    db.commit()
    db.add(AuditLog(client_id=cid, operator=user, action=f"结算回款删除行 id={row_id}"))
    db.commit()
    return {"status": "deleted"}


@app.post("/api/delivery/settlement/import")
async def settlement_import_csv(
    file: UploadFile = File(...),
    confirm: str = Form(""),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件超过大小限制")
    if str(confirm).strip().upper() != "CONFIRM":
        raise HTTPException(status_code=400, detail="导入前请确认覆盖操作（confirm=CONFIRM）")
    text = _strip_excel_sep_directive(_decode_roster_upload_bytes(raw))
    existing_rows = db.query(DeliverySettlementEntry).order_by(DeliverySettlementEntry.id).all()
    cleared_existing = len(existing_rows)
    backup_file = _write_settlement_backup_csv(existing_rows) if cleared_existing else ""
    if cleared_existing:
        db.query(DeliverySettlementEntry).delete()
        db.commit()
    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    skipped_duplicates = 0
    skipped_details: List[Dict[str, str]] = []
    seen_keys: set = set()
    for row_index, row in enumerate(reader, start=2):
        mapped: Dict[str, str] = {}
        for hk, fk in SETTLEMENT_HEADER_MAP.items():
            mapped[fk] = str(row.get(hk, "") or "").strip()
        mapped["serial_no"] = ""
        if not any(mapped.values()):
            continue
        dedup_key = _settlement_dedup_key(
            mapped.get("customer_name", ""),
            mapped.get("fee_month", ""),
            mapped.get("amount", ""),
            mapped.get("remarks", ""),
        )
        if dedup_key:
            if dedup_key in seen_keys:
                skipped_duplicates += 1
                shown = mapped.get("serial_no", "").strip() or f"CSV第{row_index}行"
                skipped_details.append(
                    {
                        "serial_no": shown,
                        "reason": (
                            "客户+费用月份+金额+备注重复"
                            f"（{mapped.get('customer_name', '')} / {mapped.get('fee_month', '')} / {mapped.get('amount', '')} / {mapped.get('remarks', '')}）"
                        ),
                    }
                )
                continue
            seen_keys.add(dedup_key)
        _validate_settlement_payload(mapped)
        client_id = _resolve_settlement_client_id(db, mapped.get("customer_name", ""), require_existing=False)
        entry = DeliverySettlementEntry(client_id=client_id, **mapped)
        db.add(entry)
        imported += 1
    db.flush()
    _resequence_settlement_serial_no_all(db)
    db.commit()
    skip_total = skipped_duplicates
    log = AuditLog(
        client_id=0,
        operator=user,
        action=(
            f"结算回款 CSV 导入前备份 {cleared_existing} 行到 {backup_file or '无备份'}，"
            f"清空 {cleared_existing} 行，导入新增 {imported} 行（按客户+费用月份+金额+备注去重跳过 {skipped_duplicates} 行）"
        ),
    )
    db.add(log)
    if skipped_details:
        detail_lines = [f"{item['serial_no']}：{item['reason']}" for item in skipped_details]
        detail_log = AuditLog(
            client_id=0,
            operator=user,
            action=f"结算回款导入跳过明细：\n" + "\n".join(detail_lines),
        )
        db.add(detail_log)
    db.commit()
    return {
        "cleared_existing": cleared_existing,
        "backup_file": backup_file,
        "imported": imported,
        "skipped_duplicates": skipped_duplicates,
        "skipped_total": skip_total,
        "skipped_details": skipped_details,
    }


@app.get("/api/delivery/settlement/export")
async def settlement_export_csv(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    rows = db.query(DeliverySettlementEntry).order_by(DeliverySettlementEntry.id).all()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(SETTLEMENT_EXPORT_HEADERS)
    for e in rows:
        d = _settlement_entry_to_dict(e)
        writer.writerow([d.get(SETTLEMENT_HEADER_MAP[h], "") for h in SETTLEMENT_EXPORT_HEADERS])
    response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"结算回款_{ts}.csv"
    _set_csv_download_headers(
        response,
        chinese_filename=filename,
        ascii_base=f"settlement_{ts}",
    )
    return response


@app.get("/api/delivery/settlement/logs")
async def settlement_logs(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.action.like("结算回款%"))
        .order_by(desc(AuditLog.created_at))
        .all()
    )
    return logs


@app.post("/api/delivery/settlement/restore/latest")
async def settlement_restore_latest_backup(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    latest = _pick_latest_backup("settlement_backup_")
    if not latest:
        raise HTTPException(status_code=404, detail="未找到结算回款备份文件")
    backup_path = os.path.join(BACKUP_DIR, latest)

    with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    cleared_existing = db.query(DeliverySettlementEntry).count()
    if cleared_existing:
        db.query(DeliverySettlementEntry).delete()
        db.commit()

    restored_rows = 0
    for row in rows:
        mapped: Dict[str, str] = {}
        for hk, fk in SETTLEMENT_HEADER_MAP.items():
            mapped[fk] = str(row.get(hk, "") or "").strip()
        if not any(mapped.values()):
            continue
        _validate_settlement_payload(mapped)
        client_id = _resolve_settlement_client_id(db, mapped.get("customer_name", ""), require_existing=False)
        entry = DeliverySettlementEntry(client_id=client_id, **mapped)
        db.add(entry)
        restored_rows += 1
    db.flush()
    _resequence_settlement_serial_no_all(db)
    db.commit()
    db.add(
        AuditLog(
            client_id=0,
            operator=user,
            action=f"结算回款从备份恢复：{latest}，清空 {cleared_existing} 行，恢复 {restored_rows} 行",
        )
    )
    db.commit()
    return {"backup_file": latest, "cleared_existing": cleared_existing, "restored_rows": restored_rows}


V8_PORT = int(os.environ.get("CRM_V8_PORT", "8001"))


def _page(template: str, request: Request, **ctx):
    # Starlette 0.28+: TemplateResponse(request, name, context) — 顺序不能错
    return TEMPLATES.TemplateResponse(request, template, ctx)


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/home", status_code=302)


@app.get("/home", response_class=HTMLResponse)
async def page_home(request: Request):
    return _page("pages/home.html", request)


@app.get("/home/funnel", response_class=HTMLResponse)
async def page_home_funnel(request: Request):
    return _page("pages/home_funnel.html", request)


@app.get("/home/trash", response_class=HTMLResponse)
async def page_home_trash(request: Request):
    return _page("pages/home_trash.html", request)


@app.get("/customers", response_class=HTMLResponse)
async def page_customers(request: Request):
    return _page("pages/customers.html", request)


@app.get("/customers/new", response_class=HTMLResponse)
async def page_customers_new(request: Request):
    return _page("pages/customers_new.html", request)


@app.get("/customers/{client_id}/edit", response_class=HTMLResponse)
async def page_customers_edit(request: Request, client_id: int):
    return _page("pages/customers_new.html", request, client_id=client_id)


@app.get("/customers/roster", response_class=HTMLResponse)
async def page_roster_index(request: Request):
    return _page("pages/roster_index.html", request)


@app.get("/customers/roster/{client_id}", response_class=HTMLResponse)
async def page_roster_detail(request: Request, client_id: int):
    return _page("pages/roster_detail.html", request, client_id=client_id)


@app.get("/opportunity/leads", response_class=HTMLResponse)
async def page_opp_leads(request: Request):
    return _page(
        "pages/placeholder.html",
        request,
        title="销售线索",
        subtitle="线索池、跟进与转化（可在此接入列表与看板）。",
        section_label="商机",
    )


@app.get("/opportunity/pool", response_class=HTMLResponse)
async def page_opp_pool(request: Request):
    return _page(
        "pages/placeholder.html",
        request,
        title="销售公海池",
        subtitle="公海领取规则与回收（可在此接入公海列表）。",
        section_label="商机",
    )


@app.get("/opportunity/dashboard", response_class=HTMLResponse)
async def page_opp_dash(request: Request):
    return _page(
        "pages/placeholder.html",
        request,
        title="商机仪表盘",
        subtitle="阶段分布、赢率与预测（可在此接入图表）。",
        section_label="商机",
    )


@app.get("/goals/quarter", response_class=HTMLResponse)
async def page_goal_quarter(request: Request):
    return _page(
        "pages/placeholder.html",
        request,
        title="季度目标",
        subtitle="团队/个人季度 OKR 与完成率。",
        section_label="目标",
    )


@app.get("/goals/personal", response_class=HTMLResponse)
async def page_goal_personal(request: Request):
    return _page(
        "pages/placeholder.html",
        request,
        title="个人指标",
        subtitle="个人配额与达成进度。",
        section_label="目标",
    )


@app.get("/goals/team", response_class=HTMLResponse)
async def page_goal_team(request: Request):
    return _page(
        "pages/placeholder.html",
        request,
        title="团队看板",
        subtitle="团队排名与对比。",
        section_label="目标",
    )


@app.get("/contacts/all", response_class=HTMLResponse)
async def page_contacts_all(request: Request):
    return _page(
        "pages/placeholder.html",
        request,
        title="全部联系人",
        subtitle="统一联系人库与关联客户。",
        section_label="联系人",
    )


@app.get("/contacts/tags", response_class=HTMLResponse)
async def page_contacts_tags(request: Request):
    return _page(
        "pages/placeholder.html",
        request,
        title="分组与标签",
        subtitle="标签体系与智能分组。",
        section_label="联系人",
    )


@app.get("/contacts/import", response_class=HTMLResponse)
async def page_contacts_import(request: Request):
    return _page(
        "pages/placeholder.html",
        request,
        title="导入与导出",
        subtitle="批量导入、导出与去重。",
        section_label="联系人",
    )


DELIVERY_MODULES = {
    "requirements": "需求清单",
    "pipeline": "管道数据",
    "interviews": "员工访谈",
    "turnover": "离职率分析",
    "handbook": "交付手册",
    "settlement": "结算回款",
}


def _delivery_module_title(module_key: str) -> str:
    title = DELIVERY_MODULES.get(module_key)
    if not title:
        raise HTTPException(status_code=404, detail="交付模块不存在")
    return title


@app.get("/delivery/{module_key}", response_class=HTMLResponse)
async def page_delivery_module_index(request: Request, module_key: str):
    title = _delivery_module_title(module_key)
    if module_key == "settlement":
        return _page(
            "pages/delivery_settlement.html",
            request,
            module_key=module_key,
            module_title=title,
        )
    return _page(
        "pages/delivery_index.html",
        request,
        module_key=module_key,
        module_title=title,
    )


@app.get("/delivery/{module_key}/{client_id}", response_class=HTMLResponse)
async def page_delivery_module_detail(request: Request, module_key: str, client_id: int):
    title = _delivery_module_title(module_key)
    if module_key == "settlement":
        return RedirectResponse(url="/delivery/settlement", status_code=302)
    return _page(
        "pages/delivery_detail.html",
        request,
        module_key=module_key,
        module_title=title,
        client_id=client_id,
    )


@app.get("/delivery/pipeline/{client_id}/insight", response_class=HTMLResponse)
async def page_delivery_pipeline_insight(request: Request, client_id: int):
    return _page("pages/delivery_pipeline_insight.html", request, client_id=client_id)


@app.get("/tools/calc", response_class=HTMLResponse)
async def page_calc(request: Request):
    return _page("pages/calc.html", request)


if __name__ == "__main__":
    import uvicorn

    ip = get_host_ip()
    print(f"\n{'='*50}")
    print("ITO CRM Ultimate V8 系统启动成功")
    print(f"本地访问: http://127.0.0.1:{V8_PORT}")
    print(f"内网访问: http://{ip}:{V8_PORT}")
    print("管理员账号: admin / admin123")
    print(f"{'='*50}\n")
    uvicorn.run(app, host="0.0.0.0", port=V8_PORT)
