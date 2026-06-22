import os
import re
import time
import shutil
import json
import csv
import io
import socket
import tempfile
import hashlib
import secrets
import base64
import unicodedata
from collections import Counter
from urllib.parse import quote
from calendar import monthrange
from datetime import datetime, timedelta, date
from typing import List, Optional, Any, Dict, Tuple, Set
from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File, status, Body, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Float, Boolean, desc, or_, not_, and_, func, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, Field

import security_foundation as sec
from auth import deps as auth_deps
from auth import data_scope as ds
from auth import service as auth_service
from auth.data_scope_catalog import (
    RESOURCE_CRM_CLIENT,
    RESOURCE_CRM_OPPORTUNITY,
    RESOURCE_CRM_CONTACT,
    RESOURCE_CRM_VISIT,
    RESOURCE_DELIVERY_HANDBOOK,
    RESOURCE_DELIVERY_HANDOFF,
    RESOURCE_DELIVERY_INTERVIEWS,
    RESOURCE_DELIVERY_PIPELINE,
    RESOURCE_DELIVERY_ROSTER,
)
from auth.deps import get_current_context
from auth.migrate import run_all as run_schema_migrations
from auth.routes import build_router as build_auth_router
from auth.service import AuthContext
from services.date_utils import parse_loose_date as _parse_loose_date
from schemas.delivery_roster import (
    CHINESE_ROSTER_HEADER_MAP as _CHINESE_ROSTER_HEADER_MAP,
    ROSTER_FIELD_KEYS,
    ROSTER_CUSTOMER_ALIAS_RULES,
    ROSTER_CREATE_REQUIRED_FIELDS,
    ROSTER_REQUIRED_LABELS,
    ROSTER_EXPORT_HEADERS,
    ZNTX_ROSTER_EXPORT_HEADERS,
)
from services.delivery_roster import (
    roster_strip_amount_for_ratio as _roster_strip_amount_for_ratio,
    format_roster_salary_quote_ratio as _format_roster_salary_quote_ratio,
    apply_roster_salary_quote_ratio as _apply_roster_salary_quote_ratio,
    sql_roster_employment_left as _sql_roster_employment_left_svc,
    sql_roster_employment_active_pool as _sql_roster_employment_active_pool_svc,
    roster_entries_union_of_all_clients as _roster_entries_union_of_all_clients_svc,
    roster_entries_turnover_pool as _roster_entries_turnover_pool_svc,
    roster_entry_to_dict as _roster_entry_to_dict,
    normalize_roster_payload as _normalize_roster_payload,
    validate_roster_business_fields as _validate_roster_business_fields,
    resolve_roster_customer_client as _resolve_roster_customer_client_svc,
    contact_dedup_key as _contact_dedup_key,
    assert_roster_contact_unique as _assert_roster_contact_unique_svc,
    assert_roster_contact_unique_global as _assert_roster_contact_unique_global_svc,
    resequence_roster_serial_no as _resequence_roster_serial_no_svc,
    resequence_roster_serial_no_all_clients as _resequence_roster_serial_no_all_clients_svc,
    write_roster_backup_csv as _write_roster_backup_csv_svc,
    write_roster_backup_csv_all as _write_roster_backup_csv_all_svc,
    write_roster_backup_turnover_csv_all as _write_roster_backup_turnover_csv_all_svc,
    ensure_merged_turnover_employment as _ensure_merged_turnover_employment,
    decode_roster_upload_bytes as _decode_roster_upload_bytes,
    map_roster_csv_header as _map_roster_csv_header,
    iter_roster_csv_data_rows as _iter_roster_csv_data_rows,
    analyze_roster_csv_headers as _analyze_roster_csv_headers,
    roster_distinct_client_ids as _roster_distinct_client_ids_svc,
    dashboard_business_options as _dashboard_business_options_svc,
    dashboard_scope_client_ids as _dashboard_scope_client_ids_svc,
    roster_entries_for_client_ids as _roster_entries_for_client_ids_svc,
    roster_entries_for_business_scope as _roster_entries_for_business_scope_svc,
    roster_entries_department_dashboard as _roster_entries_department_dashboard_svc,
    row_is_turnover_pool as _row_is_turnover_pool,
    compute_turnover_dashboard,
)
from services.delivery_interviews import (
    normalize_interview_person_name as _normalize_interview_person_name,
    interview_mark_left_for_normalized_name_keys as _interview_mark_left_for_normalized_name_keys_svc,
)

# --- 1. 配置与初始化 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
TRASH_DIR = os.path.join(BASE_DIR, "deleted_files")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
DB_URL = os.environ.get("CRM_DB_URL", "sqlite:///./crm_v8.db")
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
MATERIALS_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ADMIN_USER = {
    "username": os.environ.get("CRM_ADMIN_USERNAME", "admin"),
    "password": os.environ.get("CRM_ADMIN_PASSWORD", "admin123"),
}
ADMIN_CREDENTIALS_STORE = os.environ.get(
    "CRM_ADMIN_CREDENTIALS_STORE",
    os.path.join(BASE_DIR, ".crm_admin_credentials.json"),
)
ADMIN_PBKDF2_ITERATIONS = 390000


def _admin_credentials_store_read() -> Optional[Dict[str, Any]]:
    if not os.path.isfile(ADMIN_CREDENTIALS_STORE):
        return None
    try:
        with open(ADMIN_CREDENTIALS_STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        for key in ("username", "salt_b64", "hash_b64"):
            if key not in data or not isinstance(data[key], str):
                return None
        return data
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _effective_admin_username() -> str:
    data = _admin_credentials_store_read()
    if data:
        return data["username"]
    return ADMIN_USER["username"]


def _pbkdf2_verify(password: str, salt_b64: str, hash_b64: str, iterations: int) -> bool:
    try:
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except Exception:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(dk, expected)


def _verify_admin_login(username: str, password: str) -> bool:
    if username.strip().lower() != _effective_admin_username().lower():
        return False
    data = _admin_credentials_store_read()
    if data:
        try:
            iters = int(data.get("iterations") or ADMIN_PBKDF2_ITERATIONS)
        except (TypeError, ValueError):
            iters = ADMIN_PBKDF2_ITERATIONS
        return _pbkdf2_verify(password, data["salt_b64"], data["hash_b64"], iters)
    if not sec.default_admin_password_allowed(
        credentials_store_path=ADMIN_CREDENTIALS_STORE,
        env_password=os.environ.get("CRM_ADMIN_PASSWORD", ""),
    ):
        return False
    return password == ADMIN_USER["password"]


def _persist_admin_credentials(username: str, new_password: str) -> None:
    salt = os.urandom(16)
    iterations = ADMIN_PBKDF2_ITERATIONS
    dk = hashlib.pbkdf2_hmac("sha256", new_password.encode("utf-8"), salt, iterations)
    payload = {
        "username": username,
        "iterations": iterations,
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "hash_b64": base64.b64encode(dk).decode("ascii"),
    }
    fd, tmp_path = tempfile.mkstemp(dir=BASE_DIR, prefix=".crm_admin_cred_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, ADMIN_CREDENTIALS_STORE)
    finally:
        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
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
    owner_user_id = Column(Integer, nullable=True, index=True)
    owner_dept_id = Column(Integer, nullable=True, index=True)
    assigned_user_id = Column(Integer, nullable=True, index=True)
    delivery_owner_user_id = Column(Integer, nullable=True, index=True)
    delivery_dept_id = Column(Integer, nullable=True, index=True)
    recruitment_owner_user_id = Column(Integer, nullable=True, index=True)
    recruitment_dept_id = Column(Integer, nullable=True, index=True)
    scale = Column(String)
    phase = Column(String)  # 初步接触, 方案/报价, 合同签订, 成交
    win_rate = Column(String, default="")
    estimated_annual_amount = Column(String, default="")
    contact_name = Column(String, default="")
    contact_info = Column(String, default="")
    contact_title = Column(String, default="")
    contact_relationship = Column(String, default="")
    contact_acquisition_channel = Column(String, default="")
    contact_superior_contact = Column(String, default="")
    contact_description = Column(Text, default="")
    city = Column(String, default="")
    description = Column(Text)
    remarks = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


class VisitRecord(Base):
    __tablename__ = "visits"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    date = Column(String, default="")
    location = Column(String, default="")
    way = Column(String, default="")
    target = Column(String, default="")
    content = Column(Text, default="")
    result = Column(Text, default="")
    next_plan = Column(Text, default="")
    attachment = Column(String, nullable=True)
    week_period = Column(String, default="")
    region = Column(String, default="")
    city = Column(String, default="")
    salesperson = Column(String, default="")
    planned_time = Column(String, default="")
    visit_purpose = Column(Text, default="")
    accompanying = Column(String, default="")
    completed = Column(String, default="")
    completion_time = Column(String, default="")
    duration_minutes = Column(String, default="")
    summary_formed = Column(String, default="")
    visit_summary = Column(Text, default="")
    owner_user_id = Column(Integer, nullable=True)
    owner_dept_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer)
    operator = Column(String)
    action = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class HandoffRequest(Base):
    """销售-交付交接单"""
    __tablename__ = "handoff_requests"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), index=True)
    opportunity_id = Column(Integer, nullable=True, index=True)
    version = Column(Integer, default=1)
    title = Column(String, default="")
    status = Column(String, default="draft", index=True)
    sales_owner = Column(String, default="")
    delivery_owner = Column(String, default="")
    delivery_owner_user_id = Column(Integer, nullable=True, index=True)
    source_text = Column(Text, default="")
    requirement_json = Column(Text, default="{}")
    ai_parsed_json = Column(Text, default="")
    ai_brief_md = Column(Text, default="")
    ai_gap_flags = Column(Text, default="[]")
    ai_status = Column(String, default="")
    reject_reason_code = Column(String, default="")
    reject_detail = Column(Text, default="")
    reviewer = Column(String, default="")
    reviewed_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class HandoffReviewLog(Base):
    __tablename__ = "handoff_review_logs"
    id = Column(Integer, primary_key=True)
    handoff_id = Column(Integer, ForeignKey("handoff_requests.id"), index=True)
    client_id = Column(Integer, index=True)
    operator = Column(String)
    action = Column(String)
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


class CrmNotification(Base):
    __tablename__ = "crm_notifications"
    id = Column(Integer, primary_key=True)
    username = Column(String, index=True)
    ntype = Column(String)
    handoff_id = Column(Integer, nullable=True)
    client_id = Column(Integer, nullable=True)
    application_id = Column(Integer, nullable=True)
    offer_record_id = Column(Integer, nullable=True)
    link_url = Column(String, default="")
    message = Column(Text)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), index=True)
    name = Column(String, default="")
    title = Column(String, default="")
    city = Column(String, default="")
    phone = Column(String, default="")
    email = Column(String, default="")
    tags = Column(String, default="")
    remarks = Column(Text, default="")
    superior_contact = Column(String, default="")
    acquisition_channel = Column(String, default="")
    description = Column(Text, default="")
    created_by = Column(String, default="")
    created_at = Column(DateTime, default=datetime.now)


class Opportunity(Base):
    __tablename__ = "opportunities"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), index=True)
    name = Column(String, default="")
    amount = Column(String, default="")
    estimated_current_year_amount = Column(String, default="")
    probability = Column(String, default="")
    expected_close_date = Column(String, default="")
    stage = Column(String, default="initial", index=True)
    owner = Column(String, default="")
    owner_user_id = Column(Integer, nullable=True, index=True)
    owner_dept_id = Column(Integer, nullable=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    remarks = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


class Contract(Base):
    __tablename__ = "contracts"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), index=True)
    handoff_id = Column(Integer, nullable=True, index=True)
    opportunity_id = Column(Integer, nullable=True, index=True)
    contract_no = Column(String, default="")
    contract_type = Column(String, default="")
    title = Column(String, default="")
    total_amount = Column(String, default="")
    start_date = Column(String, default="")
    end_date = Column(String, default="")
    status = Column(String, default="draft", index=True)
    sow_markdown = Column(Text, default="")
    file_name = Column(String, default="")
    stored_path = Column(String, default="")
    mime_type = Column(String, default="")
    file_size = Column(Integer, default=0)
    uploaded_by = Column(Integer, nullable=True)
    remarks = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_at = Column(DateTime, default=datetime.now)


class ContractMilestone(Base):
    __tablename__ = "contract_milestones"
    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), index=True)
    name = Column(String, default="")
    deliverable = Column(Text, default="")
    invoice_pct = Column(String, default="")
    planned_date = Column(String, default="")
    amount = Column(String, default="")
    status = Column(String, default="pending")
    settlement_entry_id = Column(Integer, nullable=True)
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
    regularization_status = Column(String, default="未转正")
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
    delivery_communication = Column(String, default="")
    business_action = Column(String, default="")
    bp_involved = Column(String, default="")
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
    invoice_customer_entity = Column(String, default="")
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
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


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
    recruiter_user_id = Column(Integer, nullable=True)
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


class DashboardDashboard(Base):
    """团队共享仪表盘定义。"""

    __tablename__ = "dashboard_dashboards"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    layout_json = Column(Text, default="{}")
    scope = Column(String, nullable=False, default="crm", index=True)
    created_by = Column(String, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DashboardTab(Base):
    __tablename__ = "dashboard_tabs"
    id = Column(Integer, primary_key=True, index=True)
    dashboard_id = Column(Integer, ForeignKey("dashboard_dashboards.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)
    layout_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DashboardWidget(Base):
    __tablename__ = "dashboard_widgets"
    id = Column(Integer, primary_key=True, index=True)
    tab_id = Column(Integer, ForeignKey("dashboard_tabs.id"), index=True, nullable=False)
    title = Column(String, nullable=False)
    widget_type = Column(String, nullable=False)
    source_key = Column(String, default="")
    config_json = Column(Text, default="{}")
    x = Column(Integer, default=0)
    y = Column(Integer, default=0)
    w = Column(Integer, default=4)
    h = Column(Integer, default=3)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class SocialInsuranceLocation(Base):
    """GM 测算：参保地最低社保/公积金（管理员可维护）。"""

    __tablename__ = "social_insurance_locations"
    id = Column(Integer, primary_key=True, index=True)
    location = Column(String, unique=True, nullable=False, index=True)
    social_insurance = Column(Float, nullable=False, default=0)
    housing_fund = Column(Float, nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DeliveryHandbookFile(Base):
    """客户交付手册：元数据 + 文件；PDF 存书签树；音视频可配时间锚点。"""

    __tablename__ = "delivery_handbook_files"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), index=True)
    original_filename = Column(String, default="")
    stored_path = Column(String, default="")
    version_label = Column(String, default="")
    status = Column(String, default="draft")
    tags_json = Column(Text, default="[]")
    permission_departments_json = Column(Text, default="[]")
    permission_levels_json = Column(Text, default="[]")
    media_kind = Column(String, default="")
    pdf_outline_json = Column(Text, default="[]")
    media_cues_json = Column(Text, default="[]")
    search_status = Column(String, default="pending")
    search_method = Column(String, default="")
    search_error = Column(Text, default="")
    search_body = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DeliveryEmployeeFile(Base):
    """客户员工文件：按客户归档的上传文档。"""

    __tablename__ = "delivery_employee_files"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), index=True)
    original_filename = Column(String, default="")
    stored_path = Column(String, default="")
    status = Column(String, default="draft")
    media_kind = Column(String, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class CompanyMaterial(Base):
    """公司资料库：全局资质/模板/介绍等文件。"""

    __tablename__ = "company_materials"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, default="")
    category = Column(String, nullable=False, default="other")
    description = Column(Text, default="")
    confidentiality = Column(String, default="internal")
    owner_dept_id = Column(Integer, nullable=True, index=True)
    file_name = Column(String, default="")
    stored_path = Column(String, default="")
    mime_type = Column(String, default="")
    file_size = Column(Integer, default=0)
    status = Column(String, default="active", index=True)
    expires_at = Column(String, nullable=True)
    uploaded_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    archived_at = Column(DateTime, nullable=True)
    archived_by = Column(Integer, nullable=True)


# Handbook constants/helpers: migrated to schemas/delivery_handbook.py and services/delivery_handbook.py (Phase 5D)
from schemas.delivery_handbook import HANDBOOK_ALLOWED_SUFFIXES, HANDBOOK_STATUS_SET, HANDBOOK_SEARCH_BODY_MAX



engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def _ensure_clients_schema_compat():
    """补齐 clients 表新增字段，兼容旧库。"""
    with engine.begin() as conn:
        try:
            existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(clients)").fetchall()}
        except Exception:
            return
        add_cols = {
            "win_rate": "TEXT DEFAULT ''",
            "estimated_annual_amount": "TEXT DEFAULT ''",
            "contact_name": "TEXT DEFAULT ''",
            "contact_info": "TEXT DEFAULT ''",
            "contact_title": "TEXT DEFAULT ''",
            "contact_relationship": "TEXT DEFAULT ''",
            "contact_acquisition_channel": "TEXT DEFAULT ''",
            "contact_superior_contact": "TEXT DEFAULT ''",
            "contact_description": "TEXT DEFAULT ''",
            "city": "TEXT DEFAULT ''",
            "owner_user_id": "INTEGER NULL",
            "owner_dept_id": "INTEGER NULL",
            "assigned_user_id": "INTEGER NULL",
            "delivery_owner_user_id": "INTEGER NULL",
            "delivery_dept_id": "INTEGER NULL",
            "recruitment_owner_user_id": "INTEGER NULL",
            "recruitment_dept_id": "INTEGER NULL",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE clients ADD COLUMN {col} {ddl}")


_ensure_clients_schema_compat()


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
            "owner_user_id": "INTEGER NULL",
            "owner_dept_id": "INTEGER NULL",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE delivery_interview_entries ADD COLUMN {col} {ddl}")


def _ensure_roster_schema_compat():
    """为已存在 sqlite 表补齐后续新增列，避免旧库导入/编辑失败。"""
    with engine.begin() as conn:
        existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(roster_entries)").fetchall()}
        add_cols = {
            "regularization_status": "TEXT DEFAULT '未转正'",
            "zntx_staff_no": "TEXT DEFAULT ''",
            "zntx_onboarding_channel": "TEXT DEFAULT ''",
            "zntx_attendance_checkin": "TEXT DEFAULT ''",
            "zntx_attendance_makeup": "TEXT DEFAULT ''",
            "zntx_separation_type": "TEXT DEFAULT ''",
            "zntx_compensation_amount": "TEXT DEFAULT ''",
            "delivery_communication": "TEXT DEFAULT ''",
            "business_action": "TEXT DEFAULT ''",
            "bp_involved": "TEXT DEFAULT ''",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE roster_entries ADD COLUMN {col} {ddl}")


def _ensure_handbook_schema_compat():
    """旧库 delivery_handbook_files 仅含路径字段时补齐元数据列。"""
    with engine.begin() as conn:
        try:
            existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(delivery_handbook_files)").fetchall()}
        except Exception:
            return
        add_cols = {
            "version_label": "TEXT DEFAULT ''",
            "status": "TEXT DEFAULT 'draft'",
            "tags_json": "TEXT DEFAULT '[]'",
            "permission_departments_json": "TEXT DEFAULT '[]'",
            "permission_levels_json": "TEXT DEFAULT '[]'",
            "media_kind": "TEXT DEFAULT ''",
            "pdf_outline_json": "TEXT DEFAULT '[]'",
            "media_cues_json": "TEXT DEFAULT '[]'",
            "updated_at": "TEXT DEFAULT ''",
            "search_status": "TEXT DEFAULT 'pending'",
            "search_method": "TEXT DEFAULT ''",
            "search_error": "TEXT DEFAULT ''",
            "search_body": "TEXT DEFAULT ''",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE delivery_handbook_files ADD COLUMN {col} {ddl}")


def _ensure_handbook_fts_schema():
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS handbook_fts USING fts5(
              original_filename,
              body,
              handbook_id UNINDEXED,
              client_id UNINDEXED,
              tokenize = 'unicode61'
            );
            """
        )


def _ensure_handoff_phase2_schema_compat():
    with engine.begin() as conn:
        try:
            existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(handoff_requests)").fetchall()}
        except Exception:
            existing = set()
        if existing and "opportunity_id" not in existing:
            conn.exec_driver_sql("ALTER TABLE handoff_requests ADD COLUMN opportunity_id INTEGER")
        if existing and "delivery_owner_user_id" not in existing:
            conn.exec_driver_sql("ALTER TABLE handoff_requests ADD COLUMN delivery_owner_user_id INTEGER")


def _ensure_opportunities_schema_compat():
    """补齐 opportunities 表新增字段，兼容旧库。"""
    with engine.begin() as conn:
        try:
            existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(opportunities)").fetchall()}
        except Exception:
            return
        add_cols = {
            "estimated_current_year_amount": "TEXT DEFAULT ''",
            "owner_user_id": "INTEGER NULL",
            "owner_dept_id": "INTEGER NULL",
            "contact_id": "INTEGER NULL",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE opportunities ADD COLUMN {col} {ddl}")


def _ensure_pipeline_schema_compat():
    with engine.begin() as conn:
        try:
            existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(delivery_pipeline_entries)").fetchall()}
        except Exception:
            return
        if "recruiter_user_id" not in existing:
            conn.exec_driver_sql("ALTER TABLE delivery_pipeline_entries ADD COLUMN recruiter_user_id INTEGER")


def _ensure_contacts_schema_compat():
    """补齐 contacts 表新增字段，兼容旧库。"""
    with engine.begin() as conn:
        try:
            existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(contacts)").fetchall()}
        except Exception:
            return
        add_cols = {
            "superior_contact": "TEXT DEFAULT ''",
            "acquisition_channel": "TEXT DEFAULT ''",
            "description": "TEXT DEFAULT ''",
            "created_by": "TEXT DEFAULT ''",
            "city": "TEXT DEFAULT ''",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE contacts ADD COLUMN {col} {ddl}")


def _ensure_visits_schema_compat():
    """补齐客户拜访周计划字段，兼容旧库 visits 表。"""
    with engine.begin() as conn:
        try:
            existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(visits)").fetchall()}
        except Exception:
            return
        add_cols = {
            "way": "TEXT DEFAULT ''",
            "target": "TEXT DEFAULT ''",
            "result": "TEXT DEFAULT ''",
            "next_plan": "TEXT DEFAULT ''",
            "week_period": "TEXT DEFAULT ''",
            "region": "TEXT DEFAULT ''",
            "city": "TEXT DEFAULT ''",
            "salesperson": "TEXT DEFAULT ''",
            "planned_time": "TEXT DEFAULT ''",
            "visit_purpose": "TEXT DEFAULT ''",
            "accompanying": "TEXT DEFAULT ''",
            "completed": "TEXT DEFAULT ''",
            "completion_time": "TEXT DEFAULT ''",
            "duration_minutes": "TEXT DEFAULT ''",
            "summary_formed": "TEXT DEFAULT ''",
            "visit_summary": "TEXT DEFAULT ''",
            "created_at": "TEXT DEFAULT ''",
            "updated_at": "TEXT DEFAULT ''",
            "owner_user_id": "INTEGER NULL",
            "owner_dept_id": "INTEGER NULL",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE visits ADD COLUMN {col} {ddl}")
        # 旧库迁移时 created_at/updated_at 可能为 TEXT 空串，ORM DateTime 读取会报错
        conn.exec_driver_sql(
            "UPDATE visits SET created_at = datetime('now') "
            "WHERE created_at IS NULL OR trim(CAST(created_at AS TEXT)) = ''"
        )
        conn.exec_driver_sql(
            "UPDATE visits SET updated_at = datetime('now') "
            "WHERE updated_at IS NULL OR trim(CAST(updated_at AS TEXT)) = ''"
        )


def _ensure_contracts_schema_compat():
    """补齐 contracts 表附件字段，兼容旧库。"""
    with engine.begin() as conn:
        try:
            existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(contracts)").fetchall()}
        except Exception:
            return
        add_cols = {
            "file_name": "TEXT DEFAULT ''",
            "stored_path": "TEXT DEFAULT ''",
            "mime_type": "TEXT DEFAULT ''",
            "file_size": "INTEGER DEFAULT 0",
            "uploaded_by": "INTEGER NULL",
            "updated_at": "DATETIME NULL",
            "remarks": "TEXT DEFAULT ''",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE contracts ADD COLUMN {col} {ddl}")


def _ensure_rms_jobs_schema_compat():
    """补齐 rms_jobs 表新增字段，兼容旧库。"""
    with engine.begin() as conn:
        try:
            existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(rms_jobs)").fetchall()}
        except Exception:
            return
        add_cols = {
            "priority": "TEXT NOT NULL DEFAULT 'medium'",
            "salary_cap": "TEXT NOT NULL DEFAULT ''",
            "years_required": "TEXT NOT NULL DEFAULT ''",
            "education": "TEXT NOT NULL DEFAULT ''",
            "overtime_travel": "TEXT NOT NULL DEFAULT ''",
            "interviewer": "TEXT NOT NULL DEFAULT ''",
            "note": "TEXT NOT NULL DEFAULT ''",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE rms_jobs ADD COLUMN {col} {ddl}")


_ensure_roster_schema_compat()
_ensure_interview_schema_compat()
_ensure_handbook_schema_compat()
_ensure_handbook_fts_schema()
_ensure_handoff_phase2_schema_compat()
_ensure_opportunities_schema_compat()
_ensure_pipeline_schema_compat()
_ensure_clients_schema_compat()
_ensure_contacts_schema_compat()
_ensure_visits_schema_compat()
_ensure_contracts_schema_compat()

run_schema_migrations(engine)
_ensure_rms_jobs_schema_compat()


def _ensure_settlement_schema_compat():
    with engine.begin() as conn:
        try:
            existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(delivery_settlement_entries)").fetchall()}
        except Exception:
            return
        if "updated_at" not in existing:
            conn.exec_driver_sql("ALTER TABLE delivery_settlement_entries ADD COLUMN updated_at DATETIME")
            conn.exec_driver_sql(
                "UPDATE delivery_settlement_entries SET updated_at = created_at WHERE updated_at IS NULL"
            )
        if "invoice_customer_entity" not in existing:
            conn.exec_driver_sql(
                "ALTER TABLE delivery_settlement_entries ADD COLUMN invoice_customer_entity VARCHAR DEFAULT ''"
            )


_ensure_settlement_schema_compat()
from models.rms import register_rms_models

RMS_MODELS = register_rms_models(Base)
auth_service.bootstrap_after_migrate(
    engine,
    admin_username=_effective_admin_username(),
    admin_password=ADMIN_USER["password"],
)

from services.dashboards import seed_default_dashboards

_db_seed_dashboards = SessionLocal()
try:
    seed_default_dashboards(_db_seed_dashboards, DashboardDashboard, DashboardTab, DashboardWidget)
    _db_seed_dashboards.commit()
except Exception:
    _db_seed_dashboards.rollback()
    raise
finally:
    _db_seed_dashboards.close()

from services.gm_insurance import ensure_social_insurance_schema, seed_social_insurance_locations

ensure_social_insurance_schema(engine)
_db_seed = SessionLocal()
try:
    seed_social_insurance_locations(_db_seed, SocialInsuranceLocation, base_dir=BASE_DIR)
finally:
    _db_seed.close()

# Handbook FTS/search/background helpers: migrated to services/delivery_handbook.py (Phase 5D)


# --- 3. 后端核心逻辑 ---
app = FastAPI(title="ITO BMS Ultimate")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
security = HTTPBasic(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


auth_deps.configure_auth(
    get_db=get_db,
    legacy_verify=_verify_admin_login,
    legacy_effective_username=_effective_admin_username,
)
app.add_middleware(
    sec.html_auth_middleware(
        _verify_admin_login,
        _effective_admin_username,
        is_authenticated=auth_deps.request_is_authenticated,
    )
)
app.include_router(
    build_auth_router(
        get_db,
        legacy_verify=_verify_admin_login,
        legacy_effective_username=_effective_admin_username,
        Client=Client,
    )
)


def authenticate(user: str = Depends(auth_deps.authenticate)):
    return user


def authenticate_admin(user: str = Depends(auth_deps.authenticate_admin)):
    return user


def require_permission(code: str):
    return auth_deps.require_permission(code)


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=256)


@app.post("/api/auth/legacy-bootstrap")
async def api_auth_legacy_bootstrap(
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """Set HttpOnly cookie after login (legacy admin or rbac sys_user)."""
    from auth.permissions import ALL_PERMISSION_CODES

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    ctx = None
    if auth_service.is_rbac_mode():
        ctx = auth_service.verify_sys_user_password(db, credentials.username, credentials.password)
    if not ctx and _verify_admin_login(credentials.username, credentials.password):
        row = auth_service._fetch_user_by_username(db, credentials.username)
        if row and row.get("status") == "active":
            ctx = auth_service.build_auth_context(db, int(row["id"]), credentials.username)
        else:
            ctx = auth_service.AuthContext(
                username=credentials.username,
                display_name=credentials.username,
                roles=["SUPER_ADMIN"],
                permissions=set(ALL_PERMISSION_CODES),
                is_super=True,
            )
    if not ctx:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    if ctx.user_id is not None:
        auth_service.record_login(db, ctx.user_id)
        db.commit()
    resp = JSONResponse({"ok": True, "user": ctx.username})
    token = sec.make_legacy_session_token(ctx.username)
    resp.set_cookie(
        sec.LEGACY_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=7 * 86400,
        path="/",
    )
    if ctx.user_id is not None:
        ver = auth_service._user_session_version(db, ctx.user_id)
        session_token = auth_service.make_session_token(ctx.user_id, ctx.username, ver)
        resp.set_cookie(
            auth_service.SESSION_COOKIE_NAME,
            session_token,
            httponly=True,
            samesite="lax",
            max_age=auth_service.SESSION_MAX_AGE,
            path="/",
        )
    return resp


@app.post("/api/auth/logout")
async def api_auth_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(sec.LEGACY_COOKIE_NAME, path="/")
    resp.delete_cookie(auth_service.SESSION_COOKIE_NAME, path="/")
    return resp


@app.get("/api/files/access")
async def api_files_access(path: str, user: str = Depends(authenticate)):
    """Authenticated file download; replaces public /previews (phase 01)."""
    try:
        abs_path = sec.resolve_upload_path(UPLOAD_DIR, path)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非法文件路径")
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    return FileResponse(abs_path, filename=os.path.basename(abs_path))


@app.post("/api/account/change-password")
async def api_account_change_password(body: ChangePasswordBody, user: str = Depends(authenticate)):
    if body.new_password == body.current_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与当前密码相同")
    if not _verify_admin_login(user, body.current_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码错误")
    _persist_admin_credentials(user, body.new_password)
    return {"ok": True}


def _sql_roster_employment_left():
    return _sql_roster_employment_left_svc(RosterEntry)


def _sql_roster_employment_active_pool():
    return _sql_roster_employment_active_pool_svc(RosterEntry)


def _roster_entries_union_of_all_clients(db: Session, ctx: Optional[AuthContext] = None) -> List[RosterEntry]:
    return _roster_entries_union_of_all_clients_svc(db, ctx, RosterEntry, Client)


def _roster_entries_turnover_pool(db: Session, ctx: Optional[AuthContext] = None) -> List[RosterEntry]:
    return _roster_entries_turnover_pool_svc(db, RosterEntry, Client, ctx)


# _roster_entry_to_dict, _normalize_roster_payload: imported from services.delivery_roster


# _pipeline_entry_to_dict, _normalize_pipeline_payload: migrated to services/delivery_pipeline.py


# Interview helpers: migrated to services/delivery_interviews.py (Phase 5C)


def _write_roster_backup_csv(client: Client, rows: List[RosterEntry]) -> str:
    return _write_roster_backup_csv_svc(client, rows, BACKUP_DIR, RosterEntry)


def _write_roster_backup_csv_all(rows: List[RosterEntry]) -> str:
    return _write_roster_backup_csv_all_svc(rows, BACKUP_DIR)


def _write_roster_backup_turnover_csv_all(rows: List[RosterEntry]) -> str:
    return _write_roster_backup_turnover_csv_all_svc(rows, BACKUP_DIR)


# Interview constants/backup: migrated to schemas/delivery_interviews.py and services/delivery_interviews.py (Phase 5C)


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


# ROSTER_FIELD_KEYS: imported from schemas.delivery_roster


# _CHINESE_ROSTER_HEADER_MAP: imported from schemas.delivery_roster


# ROSTER_CUSTOMER_ALIAS_RULES: imported from schemas.delivery_roster


def _resolve_roster_customer_client(db: Session, raw: str) -> Tuple[Optional[Client], str]:
    return _resolve_roster_customer_client_svc(db, raw, Client)


def _assert_roster_contact_unique(
    db: Session,
    client_id: int,
    contact_info: str,
    exclude_row_id: Optional[int] = None,
) -> None:
    _assert_roster_contact_unique_svc(db, client_id, contact_info, RosterEntry, exclude_row_id)


def _resequence_roster_serial_no(db: Session, client_id: int) -> bool:
    return _resequence_roster_serial_no_svc(db, client_id, RosterEntry)


def _resequence_roster_serial_no_all_clients(db: Session) -> bool:
    return _resequence_roster_serial_no_all_clients_svc(db, RosterEntry)


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


def _assert_roster_contact_unique_global(
    db: Session,
    contact_info: str,
    exclude_row_id: Optional[int] = None,
) -> None:
    _assert_roster_contact_unique_global_svc(db, contact_info, RosterEntry, exclude_row_id)


# ROSTER_CREATE_REQUIRED_FIELDS, ROSTER_REQUIRED_LABELS: imported from schemas.delivery_roster


_resequence_all_rosters_once()


# CSV parsing helpers (_decode_roster_upload_bytes, _map_roster_csv_header,
# _iter_roster_csv_data_rows, _analyze_roster_csv_headers): imported from services.delivery_roster


def _strip_excel_sep_directive(text: str) -> str:
    """部分 Excel 导出首行为 sep=; 或 sep=,，需跳过再解析表头。"""
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].strip().lower().startswith("sep="):
        return "\n".join(lines[1:])
    return text


# ROSTER_EXPORT_HEADERS, ZNTX_ROSTER_EXPORT_HEADERS: imported from schemas.delivery_roster


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




def _sync_client_primary_contact(db: Session, client: Client) -> None:
    """将 Client 内联联系人同步到 contacts 表。"""
    from phase2_core import sync_client_primary_contact

    sync_client_primary_contact(db, Contact, client)




from routes.clients import register_client_related_routes, register_client_read_routes, register_client_write_routes

register_client_related_routes(
    app,
    get_db=get_db,
    Client=Client,
    HandoffRequest=HandoffRequest,
    VisitRecord=VisitRecord,
    AuditLog=AuditLog,
)

register_client_read_routes(
    app,
    get_db=get_db,
    Client=Client,
    Opportunity=Opportunity,
    HandoffRequest=HandoffRequest,
    CrmNotification=CrmNotification,
    trash_dir=TRASH_DIR,
    set_csv_download_headers=_set_csv_download_headers,
)

register_client_write_routes(
    app,
    get_db=get_db,
    Client=Client,
    Contact=Contact,
    Opportunity=Opportunity,
    AuditLog=AuditLog,
    VisitRecord=VisitRecord,
    DeliveryHandbookFile=DeliveryHandbookFile,
    upload_dir=UPLOAD_DIR,
    trash_dir=TRASH_DIR,
    sync_primary_contact=_sync_client_primary_contact,
)




@app.post("/api/visits")
async def add_visit(
    client_id: int = Form(...),
    date: str = Form(...),
    location: str = Form(...),
    content: str = Form(...),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: str = Depends(require_permission("crm.visits.write")),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")
    folder_name = f"{client.name}_{client.id}"
    target_dir = os.path.join(UPLOAD_DIR, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    file_path = None
    if file:
        content_bytes = await file.read()
        if len(content_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="文件超过20MB限制")
        safe_name = sec.safe_visit_attachment_name(file.filename or "")
        file_path = f"{folder_name}/{safe_name}"
        try:
            abs_target = sec.resolve_upload_path(UPLOAD_DIR, file_path)
        except ValueError:
            raise HTTPException(status_code=400, detail="非法文件路径")
        with open(abs_target, "wb") as f:
            f.write(content_bytes)

    now = datetime.now()
    visit = VisitRecord(
        client_id=client_id,
        date=date,
        location=location,
        content=content,
        attachment=file_path,
        created_at=now,
        updated_at=now,
    )
    db.add(visit)
    db.commit()
    return {"status": "ok"}





# Handbook serialization helpers: migrated to services/delivery_handbook.py (Phase 5D)


# --- Handbook API routes: migrated to routes/delivery_handbook.py (Phase 5D) ---
from routes.delivery_handbook import register_delivery_handbook_routes

register_delivery_handbook_routes(
    app,
    get_db=get_db,
    Client=Client,
    DeliveryHandbookFile=DeliveryHandbookFile,
    AuditLog=AuditLog,
    engine=engine,
    session_factory=SessionLocal,
    upload_dir=UPLOAD_DIR,
    max_file_size=MAX_FILE_SIZE,
)


from routes.delivery_employee_files import register_delivery_employee_file_routes

register_delivery_employee_file_routes(
    app,
    get_db=get_db,
    Client=Client,
    DeliveryEmployeeFile=DeliveryEmployeeFile,
    AuditLog=AuditLog,
    upload_dir=UPLOAD_DIR,
    max_file_size=MAX_FILE_SIZE,
)

from routes.company_materials import register_company_materials_routes

register_company_materials_routes(
    app,
    get_db=get_db,
    CompanyMaterial=CompanyMaterial,
    upload_dir=UPLOAD_DIR,
    max_file_size=MATERIALS_MAX_FILE_SIZE,
)


# --- Roster API routes: migrated to routes/delivery_roster.py (Phase 5A-2) ---
from routes.delivery_roster import register_delivery_roster_routes

register_delivery_roster_routes(
    app,
    get_db=get_db,
    Client=Client,
    RosterEntry=RosterEntry,
    AuditLog=AuditLog,
    backup_dir=BACKUP_DIR,
    max_file_size=MAX_FILE_SIZE,
    strip_excel_sep=_strip_excel_sep_directive,
    pick_latest_backup=_pick_latest_backup,
    set_csv_download_headers=_set_csv_download_headers,
    interview_mark_left_fn=lambda db, cid, keys: _interview_mark_left_for_normalized_name_keys_svc(db, cid, keys, DeliveryInterviewEntry),
    normalize_interview_name_fn=_normalize_interview_person_name,
)






# _parse_loose_date: imported from services.date_utils


# Period/week-label functions: migrated to services/period_utils.py (Phase 5B)


# --- Pipeline API routes: migrated to routes/delivery_pipeline.py (Phase 5B) ---
from routes.delivery_pipeline import register_delivery_pipeline_routes

register_delivery_pipeline_routes(
    app,
    get_db=get_db,
    Client=Client,
    PipelineEntry=DeliveryPipelineEntry,
    InsightDemand=DeliveryPipelineInsightDemand,
    AuditLog=AuditLog,
    backup_dir=BACKUP_DIR,
    max_file_size=MAX_FILE_SIZE,
    strip_excel_sep=_strip_excel_sep_directive,
    decode_upload_bytes=_decode_roster_upload_bytes,
    pick_latest_backup=_pick_latest_backup,
    set_csv_download_headers=_set_csv_download_headers,
)



# --- Interviews API routes: migrated to routes/delivery_interviews.py (Phase 5C) ---
from routes.delivery_interviews import register_delivery_interviews_routes

register_delivery_interviews_routes(
    app,
    get_db=get_db,
    Client=Client,
    InterviewEntry=DeliveryInterviewEntry,
    AuditLog=AuditLog,
    backup_dir=BACKUP_DIR,
    max_file_size=MAX_FILE_SIZE,
    strip_excel_sep=_strip_excel_sep_directive,
    decode_upload_bytes=_decode_roster_upload_bytes,
    pick_latest_backup=_pick_latest_backup,
    set_csv_download_headers=_set_csv_download_headers,
)


V8_PORT = int(os.environ.get("CRM_V8_PORT", "8001"))


def _page(template: str, request: Request, **ctx):
    # Starlette 0.28+: TemplateResponse(request, name, context) — 顺序不能错
    ctx.setdefault("auth_mode", auth_service.auth_mode())
    return TEMPLATES.TemplateResponse(request, template, ctx)


from handoff_routes import register_handoff_routes
from phase2_routes import register_phase2_routes
from visit_routes import register_visit_routes
from routes.delivery_settlement import register_delivery_settlement_routes

register_handoff_routes(
    app,
    get_db=get_db,
    authenticate=authenticate,
    authenticate_admin=authenticate_admin,
    review_dep=require_permission("delivery.handoff.review"),
    effective_admin_username=_effective_admin_username,
    page_renderer=_page,
    Client=Client,
    HandoffRequest=HandoffRequest,
    HandoffReviewLog=HandoffReviewLog,
    CrmNotification=CrmNotification,
    VisitRecord=VisitRecord,
    DeliveryPipelineInsightDemand=DeliveryPipelineInsightDemand,
    Contract=Contract,
    ContractMilestone=ContractMilestone,
)

register_phase2_routes(
    app,
    get_db=get_db,
    authenticate=authenticate,
    page_renderer=_page,
    Client=Client,
    Contact=Contact,
    Opportunity=Opportunity,
    Contract=Contract,
    ContractMilestone=ContractMilestone,
    HandoffRequest=HandoffRequest,
    DeliverySettlementEntry=DeliverySettlementEntry,
    set_csv_download_headers=_set_csv_download_headers,
    max_file_size=MAX_FILE_SIZE,
    upload_dir=UPLOAD_DIR,
    contracts_max_file_size=MATERIALS_MAX_FILE_SIZE,
)

register_visit_routes(
    app,
    get_db=get_db,
    authenticate=authenticate,
    page_renderer=_page,
    Client=Client,
    VisitRecord=VisitRecord,
)

from routes.gm_config import register_gm_config_routes

register_gm_config_routes(
    app,
    get_db=get_db,
    SocialInsuranceLocation=SocialInsuranceLocation,
)

register_delivery_settlement_routes(
    app,
    get_db=get_db,
    Client=Client,
    DeliverySettlementEntry=DeliverySettlementEntry,
    ContractMilestone=ContractMilestone,
    AuditLog=AuditLog,
    backup_dir=BACKUP_DIR,
    max_file_size=MAX_FILE_SIZE,
    decode_upload_bytes=_decode_roster_upload_bytes,
    strip_excel_sep=_strip_excel_sep_directive,
    pick_latest_backup=_pick_latest_backup,
    set_csv_download_headers=_set_csv_download_headers,
)

from routes.dashboards import register_dashboard_routes

register_dashboard_routes(
    app,
    get_db=get_db,
    page_renderer=_page,
    DashboardDashboard=DashboardDashboard,
    DashboardTab=DashboardTab,
    DashboardWidget=DashboardWidget,
    Client=Client,
    Contact=Contact,
    Opportunity=Opportunity,
    VisitRecord=VisitRecord,
    HandoffRequest=HandoffRequest,
    DeliveryPipelineEntry=DeliveryPipelineEntry,
    RosterEntry=RosterEntry,
    DeliverySettlementEntry=DeliverySettlementEntry,
    DeliveryInterviewEntry=DeliveryInterviewEntry,
)

from routes.rms_shell import register_rms_shell_routes
from routes.rms_jobs import register_rms_jobs_routes
from routes.rms_candidates import register_rms_candidates_routes
from routes.rms_applications import register_rms_applications_routes
from routes.rms_dashboard import register_rms_dashboard_routes
from routes.rms_offers import register_rms_offers_routes

register_rms_jobs_routes(
    app,
    get_db=get_db,
    Client=Client,
    RmsJob=RMS_MODELS["RmsJob"],
    RmsApplication=RMS_MODELS["RmsApplication"],
)
register_rms_candidates_routes(
    app,
    get_db=get_db,
    upload_dir=UPLOAD_DIR,
    Client=Client,
    RmsCandidate=RMS_MODELS["RmsCandidate"],
    RmsApplication=RMS_MODELS["RmsApplication"],
    RmsResume=RMS_MODELS["RmsResume"],
    RmsJob=RMS_MODELS["RmsJob"],
)
register_rms_applications_routes(
    app,
    get_db=get_db,
    upload_dir=UPLOAD_DIR,
    Client=Client,
    RmsJob=RMS_MODELS["RmsJob"],
    RmsCandidate=RMS_MODELS["RmsCandidate"],
    RmsApplication=RMS_MODELS["RmsApplication"],
    RmsApplicationStatusHistory=RMS_MODELS["RmsApplicationStatusHistory"],
    RmsResume=RMS_MODELS["RmsResume"],
    RosterEntry=RosterEntry,
    RmsInterview=RMS_MODELS["RmsInterview"],
    RmsOffer=RMS_MODELS["RmsOffer"],
    RmsOfferRecord=RMS_MODELS["RmsOfferRecord"],
    RmsOfferApprovalStep=RMS_MODELS["RmsOfferApprovalStep"],
    RmsMatchResult=RMS_MODELS["RmsMatchResult"],
    AuditLog=AuditLog,
)
register_rms_dashboard_routes(
    app,
    get_db=get_db,
    Client=Client,
    Contact=Contact,
    Opportunity=Opportunity,
    VisitRecord=VisitRecord,
    HandoffRequest=HandoffRequest,
    DeliveryPipelineEntry=DeliveryPipelineEntry,
    RosterEntry=RosterEntry,
    DeliverySettlementEntry=DeliverySettlementEntry,
    DeliveryInterviewEntry=DeliveryInterviewEntry,
    RmsJob=RMS_MODELS["RmsJob"],
    RmsCandidate=RMS_MODELS["RmsCandidate"],
    RmsApplication=RMS_MODELS["RmsApplication"],
    RmsApplicationStatusHistory=RMS_MODELS["RmsApplicationStatusHistory"],
    DashboardDashboard=DashboardDashboard,
    DashboardTab=DashboardTab,
    DashboardWidget=DashboardWidget,
)
from routes.rms_offer_approval_config import register_rms_offer_approval_config_routes

register_rms_offer_approval_config_routes(
    app,
    get_db=get_db,
    RmsOfferApprovalConfig=RMS_MODELS["RmsOfferApprovalConfig"],
)

register_rms_offers_routes(
    app,
    get_db=get_db,
    upload_dir=UPLOAD_DIR,
    Client=Client,
    CrmNotification=CrmNotification,
    RmsApplication=RMS_MODELS["RmsApplication"],
    RmsApplicationStatusHistory=RMS_MODELS["RmsApplicationStatusHistory"],
    RmsCandidate=RMS_MODELS["RmsCandidate"],
    RmsJob=RMS_MODELS["RmsJob"],
    RmsOfferRecord=RMS_MODELS["RmsOfferRecord"],
    RmsOfferApprovalStep=RMS_MODELS["RmsOfferApprovalStep"],
    RmsOfferApprovalConfig=RMS_MODELS["RmsOfferApprovalConfig"],
)

register_rms_shell_routes(app, page_renderer=_page)


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/home", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def page_login(request: Request):
    return _page("pages/login.html", request, auth_mode=auth_service.auth_mode())


@app.get("/system/users", response_class=HTMLResponse)
async def page_system_users(
    request: Request,
    ctx=Depends(auth_deps.require_any_permission(
        "system.users.manage", "system.roles.manage", "system.audit.read"
    )),
):
    return _page(
        "pages/system_admin.html",
        request,
        auth_mode=auth_service.auth_mode(),
        can_users=auth_service.user_has_permission(ctx, "system.users.manage"),
        can_roles=auth_service.user_has_permission(ctx, "system.roles.manage"),
        can_audit=auth_service.user_has_permission(ctx, "system.audit.read"),
        is_super=ctx.is_super,
    )


@app.get("/home", response_class=HTMLResponse)
async def page_home(request: Request):
    return _page("pages/home.html", request)


@app.get("/home/funnel", response_class=HTMLResponse)
async def page_home_funnel(request: Request):
    return _page("pages/home_funnel.html", request)


@app.get("/home/trash", response_class=HTMLResponse)
async def page_home_trash(request: Request):
    return _page("pages/home_trash.html", request)


@app.get("/materials", response_class=HTMLResponse)
async def page_materials(
    request: Request,
    _ctx: AuthContext = Depends(auth_deps.require_any_permission(
        "materials.read",
        "materials.public.read",
        "materials.internal.read",
    )),
):
    return _page("pages/materials.html", request)


@app.get("/customers", response_class=HTMLResponse)
async def page_customers(
    request: Request,
    _user: str = Depends(require_permission("crm.clients.read")),
):
    return _page("pages/customers.html", request)


@app.get("/customers/new", response_class=HTMLResponse)
async def page_customers_new(
    request: Request,
    _user: str = Depends(require_permission("crm.clients.write")),
):
    return _page("pages/customers_new.html", request)


@app.get("/customers/{client_id}/edit", response_class=HTMLResponse)
async def page_customers_edit(
    request: Request,
    client_id: int,
    _user: str = Depends(require_permission("crm.clients.write")),
):
    return _page("pages/customers_new.html", request, client_id=client_id)


@app.get("/customers/roster", response_class=HTMLResponse)
async def page_roster_index(request: Request):
    return _page("pages/roster_index.html", request)


@app.get("/customers/roster/{client_id}", response_class=HTMLResponse)
async def page_roster_detail(request: Request, client_id: int):
    return _page("pages/roster_detail.html", request, client_id=client_id)


DELIVERY_MODULES = {
    "requirements": "需求清单",
    "pipeline": "管道数据",
    "interviews": "员工访谈",
    "employee_files": "员工文件",
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
    if module_key == "turnover":
        return _page(
            "pages/delivery_turnover.html",
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
    if module_key == "turnover":
        return RedirectResponse(url="/delivery/turnover", status_code=302)
    return _page(
        "pages/delivery_detail.html",
        request,
        module_key=module_key,
        module_title=title,
        client_id=client_id,
        handbook_admin_cross_search=(module_key == "handbook"),
    )


@app.get("/delivery/pipeline/{client_id}/insight", response_class=HTMLResponse)
async def page_delivery_pipeline_insight(request: Request, client_id: int):
    return _page("pages/delivery_pipeline_insight.html", request, client_id=client_id)


@app.get("/tools/calc", response_class=HTMLResponse)
async def page_calc(
    request: Request,
    _user: str = Depends(require_permission("tools.gm_calc.read")),
):
    return _page("pages/calc.html", request)


if __name__ == "__main__":
    import uvicorn

    ip = get_host_ip()
    print(f"\n{'='*50}")
    print("ITO BMS Ultimate V8 系统启动成功")
    print(f"本地访问: http://127.0.0.1:{V8_PORT}")
    print(f"内网访问: http://{ip}:{V8_PORT}")
    print(
        sec.admin_startup_auth_hint(
            effective_username=_effective_admin_username(),
            credentials_store_path=ADMIN_CREDENTIALS_STORE,
            env_password_set=bool(os.environ.get("CRM_ADMIN_PASSWORD", "").strip()),
        )
    )
    print(f"{'='*50}\n")
    uvicorn.run(app, host="0.0.0.0", port=V8_PORT)
