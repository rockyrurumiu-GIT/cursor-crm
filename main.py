import os
import re
import time
import shutil
import json
import csv
import io
import socket
import unicodedata
from collections import Counter
from urllib.parse import quote
from calendar import monthrange
from datetime import datetime, timedelta, date
from typing import List, Optional, Any, Dict, Tuple
from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File, status, Body, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Float, desc, or_, not_, and_, func, text
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


HANDBOOK_ALLOWED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".doc",
    ".mp4",
    ".webm",
    ".ogg",
    ".mov",
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
}

HANDBOOK_STATUS_SET = frozenset({"draft", "published", "deprecated"})


def _handbook_split_comma_labels(s: str) -> List[str]:
    return [x.strip() for x in str(s or "").replace("，", ",").split(",") if x.strip()]


def _handbook_labels_to_json_array(s: str) -> str:
    return json.dumps(_handbook_split_comma_labels(s), ensure_ascii=False)


def _handbook_normalize_status(raw: str) -> str:
    v = str(raw or "").strip().lower()
    if v in HANDBOOK_STATUS_SET:
        return v
    return "draft"


def _handbook_suffix_to_media_kind(ext: str) -> str:
    e = str(ext or "").lower()
    if e == ".pdf":
        return "pdf"
    if e in (".mp4", ".webm", ".ogg", ".mov"):
        return "video"
    if e in (".mp3", ".wav", ".m4a", ".aac", ".flac"):
        return "audio"
    if e in (".doc", ".docx"):
        return "document"
    return "document"


def _handbook_parse_json_list(raw: Optional[str], default: Optional[List[Any]] = None) -> List[Any]:
    default = default if default is not None else []
    if not raw or not str(raw).strip():
        return list(default)
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else list(default)
    except Exception:
        return list(default)


def _toc_levels_to_tree(toc: List[List[Any]]) -> List[Dict[str, Any]]:
    if not toc:
        return []
    root: List[Dict[str, Any]] = []
    stack: List[Tuple[int, Dict[str, Any]]] = []
    for entry in toc:
        if not entry or len(entry) < 3:
            continue
        try:
            lvl = int(entry[0])
            title = str(entry[1] or "").strip() or "未命名"
            page = int(entry[2])
        except (TypeError, ValueError):
            continue
        node = {"title": title, "page": max(1, page), "children": []}
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        if not stack:
            root.append(node)
        else:
            stack[-1][1]["children"].append(node)
        stack.append((lvl, node))
    return root


def _pdf_outline_fitz(data: bytes) -> List[Dict[str, Any]]:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        toc = doc.get_toc(simple=False) or doc.get_toc(simple=True)
        doc.close()
    except Exception:
        return []
    return _toc_levels_to_tree(toc) if toc else []


def _pypdf_outline_aux(items: Any, reader: Any) -> List[Dict[str, Any]]:
    """将 pypdf 嵌套 outline（Destination 与 list 混排）转为树。"""
    if not items:
        return []
    if not isinstance(items, list):
        items = [items]
    tree: List[Dict[str, Any]] = []
    i = 0
    while i < len(items):
        el = items[i]
        if isinstance(el, list):
            if tree:
                tree[-1]["children"] = _pypdf_outline_aux(el, reader)
            else:
                tree.extend(_pypdf_outline_aux(el, reader))
            i += 1
            continue
        try:
            title = str(getattr(el, "title", "") or "").strip() or "未命名"
            page = int(reader.get_destination_page_number(el)) + 1
        except Exception:
            i += 1
            continue
        node = {"title": title, "page": max(1, page), "children": []}
        tree.append(node)
        i += 1
        if i < len(items) and isinstance(items[i], list):
            node["children"] = _pypdf_outline_aux(items[i], reader)
            i += 1
    return tree


def _pdf_outline_pypdf(data: bytes) -> List[Dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except Exception:
        return []
    try:
        outline = reader.outline
    except Exception:
        return []
    if not outline:
        return []
    try:
        tree = _pypdf_outline_aux(outline, reader)
    except Exception:
        return []
    return tree if tree else []


_HANDBOOK_TOC_LINE = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\s+(.+?)\s*(?:\.{2,}|…{1,}|·{2,}|＊{2,}|\s{3,})\s*(\d{1,4})\s*$"
)

_HANDBOOK_TOC_INLINE = re.compile(
    r"(\d+(?:\.\d+)*)\s+(.+?)\s*(?:\.{2,}|…{1,}|·{2,}|\s{2,})\s*(\d{1,4})"
)


def _handbook_normalize_toc_text(s: str) -> str:
    """全角数字/空格归一化，便于匹配目录行。"""
    trans = str.maketrans(
        "０１２３４５６７８９　．，",
        "0123456789 .,",
    )
    return (s or "").translate(trans)


def _section_key_depth(sec: str) -> int:
    parts = str(sec or "").strip().split(".")
    return max(0, len([p for p in parts if p]) - 1)


def _fitz_link_target_page_1based(doc: Any, link: Dict[str, Any]) -> Optional[int]:
    """Resolve PyMuPDF link destination to a 1-based page number, or None."""
    raw = link.get("page")
    if raw is not None:
        try:
            return int(raw) + 1
        except (TypeError, ValueError):
            pass
    uri = str(link.get("uri") or "").strip()
    if uri and not re.match(r"^https?://", uri, re.I):
        m = re.search(r"(?:[#&?]|^)(?:page|pg)\s*=\s*(\d+)", uri, re.I)
        if m:
            try:
                return max(1, int(m.group(1)))
            except ValueError:
                pass
    dest = link.get("dest")
    if dest is not None:
        try:
            p = getattr(dest, "page", None)
            if p is not None:
                pi = int(p)
                if pi >= 0:
                    return pi + 1
        except (TypeError, ValueError, AttributeError):
            pass
    rslv = getattr(doc, "resolve_link", None)
    if callable(rslv):
        try:
            loc = rslv(link)
            if loc is not None:
                if isinstance(loc, (list, tuple)) and len(loc) > 0:
                    try:
                        pi = int(loc[0])
                        if pi >= 0:
                            return pi + 1
                    except (TypeError, ValueError):
                        pass
                elif isinstance(loc, int) and loc >= 0:
                    return loc + 1
        except Exception:
            pass
    return None


def _pdf_outline_from_internal_links(data: bytes) -> List[Dict[str, Any]]:
    """从前几页收集「正文里可点的目录」：LINK_GOTO 区域文字 + 目标页（与 PDF 内点击行为一致）。"""
    try:
        import fitz
    except ImportError:
        return []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return []
    LINK_GOTO = getattr(fitz, "LINK_GOTO", 1)
    LINK_GOTOR = getattr(fitz, "LINK_GOTOR", 5)
    candidates: List[Tuple[float, float, str, int]] = []
    max_scan = min(24, doc.page_count)
    for pno in range(max_scan):
        page = doc.load_page(pno)
        for link in page.get_links() or []:
            kind = link.get("kind")
            if kind not in (LINK_GOTO, LINK_GOTOR):
                continue
            dest_1 = _fitz_link_target_page_1based(doc, link)
            if dest_1 is None:
                continue
            rect = link.get("from")
            title = ""
            if rect:
                try:
                    r = fitz.Rect(rect)
                    title = page.get_textbox(r).strip()
                    if not title:
                        title = (page.get_text("text", clip=r) or "").strip()
                except Exception:
                    title = ""
            title = re.sub(r"\s+", " ", title).strip()
            if len(title) > 160:
                title = title[:160].rstrip()
            if not title:
                if dest_1 != pno + 1:
                    title = f"· 第{dest_1}页"
                else:
                    continue
            if rect:
                r = fitz.Rect(rect)
                candidates.append((float(r.y0), float(r.x0), title, dest_1))
            else:
                candidates.append((0.0, 0.0, title, dest_1))
    doc.close()
    if len(candidates) < 1:
        return []
    candidates.sort(key=lambda t: (round(t[0], 2), round(t[1], 2)))
    found: List[Tuple[int, str, int]] = []
    seen: set = set()
    for _, _, title, pg in candidates:
        key = (title, pg)
        if key in seen:
            continue
        seen.add(key)
        raw_t = title.strip()
        m = re.match(r"^(\d+(?:\.\d+)*)", raw_t)
        sec = m.group(1) if m else ""
        depth = _section_key_depth(sec) if sec else 0
        found.append((depth, raw_t, max(1, pg)))
    if len(found) < 2:
        return []
    root: List[Dict[str, Any]] = []
    stack: List[Tuple[int, Dict[str, Any]]] = []
    for depth, title, page in found:
        node = {"title": title, "page": max(1, page), "children": []}
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if not stack:
            root.append(node)
        else:
            stack[-1][1]["children"].append(node)
        stack.append((depth, node))
    return root


def _pdf_outline_heuristic_text(data: bytes) -> List[Dict[str, Any]]:
    """从正文前几页识别「1.1 标题 … 3」式目录行（无 PDF 书签时）。"""
    try:
        import fitz
    except ImportError:
        return []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return []
    found: List[Tuple[int, str, int]] = []
    max_pages = min(16, doc.page_count)
    for pno in range(max_pages):
        page = doc.load_page(pno)
        try:
            text = page.get_text("text", sort=True) or page.get_text("text") or ""
        except Exception:
            text = page.get_text("text") or ""
        text = _handbook_normalize_toc_text(text)
        # 目录页：截取「目录」后一段，减少误匹配正文
        chunk = text
        if "目录" in chunk:
            idx = chunk.find("目录")
            chunk_after = chunk[idx : idx + 6000]
        else:
            chunk_after = chunk
        for m in _HANDBOOK_TOC_INLINE.finditer(chunk_after):
            sec, title, pstr = m.group(1), m.group(2).strip(), m.group(3)
            title = re.sub(r"\s+", " ", title).strip(" .,，")
            if not title or len(title) > 120:
                continue
            try:
                pg = int(pstr)
            except ValueError:
                continue
            depth = _section_key_depth(sec)
            found.append((depth, f"{sec} {title}", pg))
        for line in text.splitlines():
            raw = _handbook_normalize_toc_text(line.strip())
            if not raw:
                continue
            m = _HANDBOOK_TOC_LINE.match(raw)
            if not m and len(raw) < 140:
                m = re.match(
                    r"^\s*(\d+(?:\.\d+)*)\s+(.+?)\s{2,}(\d{1,4})\s*$",
                    raw,
                )
            if not m and len(raw) < 140:
                m = re.match(
                    r"^\s*(\d+(?:\.\d+)*)\s+(.+?)\s+(\d{1,4})\s*$",
                    raw,
                )
            if not m:
                continue
            sec, title, pstr = m.group(1), m.group(2).strip(), m.group(3)
            title = re.sub(r"\s+", " ", title).strip(" .,，")
            if not title or len(title) > 120:
                continue
            try:
                pg = int(pstr)
            except ValueError:
                continue
            depth = _section_key_depth(sec)
            found.append((depth, f"{sec} {title}", pg))
    doc.close()
    if not found:
        return []
    # 去重，保留首次出现
    uniq: List[Tuple[int, str, int]] = []
    seen_line: set = set()
    for item in found:
        k = (item[1], item[2])
        if k in seen_line:
            continue
        seen_line.add(k)
        uniq.append(item)
    found = uniq
    root: List[Dict[str, Any]] = []
    stack: List[Tuple[int, Dict[str, Any]]] = []
    for depth, title, page in found:
        node = {"title": title, "page": max(1, page), "children": []}
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if not stack:
            root.append(node)
        else:
            stack[-1][1]["children"].append(node)
        stack.append((depth, node))
    return root


def _pdf_bytes_to_outline_tree(data: bytes) -> List[Dict[str, Any]]:
    tree = _pdf_outline_fitz(data)
    if tree:
        return tree
    tree = _pdf_outline_pypdf(data)
    if tree:
        return tree
    tree = _pdf_outline_from_internal_links(data)
    if tree:
        return tree
    return _pdf_outline_heuristic_text(data)


def _handbook_normalize_media_cues(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip() or "锚点"
        try:
            sec = float(item.get("seconds", 0))
        except (TypeError, ValueError):
            sec = 0.0
        if sec < 0:
            sec = 0.0
        out.append({"label": label, "seconds": sec})
    return out


def _client_upload_folder_name(client: Client) -> str:
    return f"{client.name}_{client.id}"


def _handbook_client_dir_rel(client: Client) -> str:
    return f"handbooks/{_client_upload_folder_name(client)}"


def _safe_handbook_filename(name: str) -> str:
    base = os.path.basename(str(name or "")).strip()
    if not base:
        base = "handbook.bin"
    base = re.sub(r"[^\w\-. \u4e00-\u9fff]", "_", base)
    return (base[:200] if len(base) > 200 else base) or "handbook.bin"


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


_ensure_roster_schema_compat()
_ensure_interview_schema_compat()
_ensure_handbook_schema_compat()
_ensure_handbook_fts_schema()
HANDBOOK_SEARCH_BODY_MAX = 2_000_000
HANDBOOK_SEARCH_SNIPPET_LIST = 780
HANDBOOK_SEARCH_SNIPPET_MODAL = min(32_000, HANDBOOK_SEARCH_BODY_MAX)
HANDBOOK_OCR_MAX_PAGES = 120
HANDBOOK_OCR_ZOOM = 2.0


def _handbook_fts_delete_row(row_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM handbook_fts WHERE rowid = :rid"), {"rid": row_id})


def _handbook_fts_upsert_row(row_id: int, client_id: int, filename: str, body: str) -> None:
    fn = (filename or "")[:2000]
    bd = (body or "")[:HANDBOOK_SEARCH_BODY_MAX]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM handbook_fts WHERE rowid = :rid"), {"rid": row_id})
        conn.execute(
            text(
                "INSERT INTO handbook_fts (rowid, original_filename, body, handbook_id, client_id) "
                "VALUES (:rid, :fn, :body, :hid, :cid)"
            ),
            {"rid": row_id, "fn": fn, "body": bd, "hid": row_id, "cid": client_id},
        )


def _handbook_build_fts_query(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    s = re.sub(r'["\']', " ", s)
    tokens: List[str] = []
    for m in re.finditer(r"[\w.]+|[\u4e00-\u9fff]+", s):
        t = m.group(0)
        if t:
            tokens.append(t)
    if not tokens:
        return ""
    tokens = tokens[:24]
    return " OR ".join(f'"{t}"' for t in tokens)


def _handbook_search_snippet(
    haystack: Optional[str],
    needle: str,
    max_len: int = 680,
    *,
    collapse_ws: bool = True,
) -> str:
    """围绕首次命中截取摘录；列表用 collapse_ws 压成单行，详情保留换行。"""
    hay = haystack or ""
    nd = (needle or "").strip()

    def pack(s: str) -> str:
        s = (s or "").strip()
        if collapse_ws:
            return re.sub(r"\s+", " ", s).strip()
        return s

    if not hay:
        return ""
    if not nd:
        s0 = pack(hay[:max_len])
        return s0 + ("…" if len(hay) > max_len else "")
    i = hay.find(nd)
    if i < 0:
        lh = hay.casefold()
        ln = nd.casefold()
        if ln and lh != hay:
            j = lh.find(ln)
            i = int(j) if j >= 0 else -1
    if i < 0:
        s0 = pack(hay[:max_len])
        return s0 + ("…" if len(hay) > max_len else "")
    half = max_len // 2
    start = max(0, i - half)
    end = min(len(hay), start + max_len)
    start = max(0, end - max_len)
    frag = hay[start:end]
    frag = pack(frag)
    if start > 0:
        frag = "…" + frag
    if end < len(hay):
        frag = frag + "…"
    return frag


def _handbook_query_terms(raw: str) -> List[str]:
    s = (raw or "").strip()
    if not s:
        return []
    terms = [s]
    for m in re.finditer(r"[\w.]+|[\u4e00-\u9fff]+", s):
        t = (m.group(0) or "").strip()
        if t and t not in terms:
            terms.append(t)
    return terms[:24]


def _handbook_text_matches(text_value: Optional[str], terms: List[str]) -> bool:
    hay = (text_value or "").casefold()
    return bool(hay and any(t.casefold() in hay for t in terms if t))


def _handbook_locate_pdf_page(row: DeliveryHandbookFile, query: str) -> int:
    """Best-effort source page for a PDF hit; fallback to page 1."""
    terms = _handbook_query_terms(query)
    if not terms:
        return 1
    abs_path = os.path.join(UPLOAD_DIR, (row.stored_path or "").strip())
    if not os.path.isfile(abs_path):
        return 1
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return 1
    doc = None
    try:
        doc = fitz.open(abs_path)
        for i in range(len(doc)):
            try:
                page_text = doc.load_page(i).get_text() or ""
            except Exception:
                page_text = ""
            if _handbook_text_matches(page_text, terms):
                return i + 1
    except Exception:
        return 1
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
    return 1


def _handbook_locate_media_seconds(row: DeliveryHandbookFile, query: str) -> Optional[float]:
    terms = _handbook_query_terms(query)
    cues = _handbook_cues_from_json_string(getattr(row, "media_cues_json", None))
    if not cues:
        return None
    for c in cues:
        if _handbook_text_matches(str(c.get("label") or ""), terms):
            return float(c.get("seconds") or 0)
    return None


def _pdf_plain_text_and_pagecount(data: bytes) -> Tuple[str, int]:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return "", 0
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return "", 0
    try:
        n = len(doc)
        parts: List[str] = []
        for i in range(n):
            try:
                parts.append(doc.load_page(i).get_text() or "")
            except Exception:
                parts.append("")
        return "\n".join(parts), n
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _pdf_text_suggests_ocr(plain: str, page_count: int) -> bool:
    t = (plain or "").strip()
    if page_count <= 0:
        return False
    if len(t) < 80:
        return True
    avg = len(t) / max(page_count, 1)
    return avg < 35


def _pdf_ocr_tesseract(data: bytes) -> Tuple[str, str]:
    """
    returns (text, detail) detail empty if ok else error hint
    Requires: tesseract on PATH + tessdata chi_sim (+eng recommended).
    """
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
        import io
    except ImportError as e:
        return "", f"Python 依赖未安装（{e}）"
    if os.environ.get("TESSERACT_CMD"):
        pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
    doc = None
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:
        return "", str(e)
    mat = fitz.Matrix(HANDBOOK_OCR_ZOOM, HANDBOOK_OCR_ZOOM)
    parts: List[str] = []
    try:
        n = min(len(doc), HANDBOOK_OCR_MAX_PAGES)
        ocr_fatal = ""
        for i in range(n):
            try:
                pix = doc.load_page(i).get_pixmap(matrix=mat, alpha=False)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                txt = pytesseract.image_to_string(img, lang="chi_sim+eng") or ""
                parts.append(txt)
            except pytesseract.TesseractNotFoundError:
                ocr_fatal = (
                    "未检测到 Tesseract 可执行程序，请安装并把 tesseract 加入 PATH，或设置环境变量 TESSERACT_CMD"
                )
                break
            except Exception:
                parts.append("")
        if ocr_fatal:
            return "", ocr_fatal
        return "\n".join(parts), ""
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass



def _handbook_manual_search_blob(r: DeliveryHandbookFile) -> str:
    """音视频 / Word：在无语义转写时，用语义化元数据与时间戳锚点文案拼接可检索文本。"""
    lines: List[str] = []
    fn = (r.original_filename or "").strip()
    if fn:
        lines.append(fn)
        base = os.path.splitext(fn)[0].strip()
        if base and base != fn:
            lines.append(base)
    vl = str(getattr(r, "version_label", None) or "").strip()
    if vl:
        lines.append(vl)
    for lst, prefix in (
        (_handbook_parse_json_list(getattr(r, "tags_json", None)), "标签"),
        (_handbook_parse_json_list(getattr(r, "permission_departments_json", None)), "部门"),
        (_handbook_parse_json_list(getattr(r, "permission_levels_json", None)), "级别"),
    ):
        for x in lst:
            sx = str(x).strip()
            if sx:
                lines.append(f"{prefix} {sx}")
                lines.append(sx)
    mk = (getattr(r, "media_kind", None) or "").strip()
    if mk == "video":
        lines.append("视频")
    elif mk == "audio":
        lines.append("音频")
    elif mk == "document":
        lines.append("文档")
    try:
        cues = json.loads(getattr(r, "media_cues_json", None) or "[]")
    except Exception:
        cues = []
    if isinstance(cues, list):
        for c in cues:
            if not isinstance(c, dict):
                continue
            label = str(c.get("label") or "").strip()
            if not label:
                continue
            lines.append(label)
            sec = c.get("seconds")
            if sec is not None:
                try:
                    lines.append(f"{label} {float(sec)}秒")
                except (TypeError, ValueError):
                    lines.append(f"{label} {sec}秒")
    return "\n".join(x for x in lines if str(x).strip())


def _handbook_background_index_manual_meta(row_id: int) -> None:
    """为非 PDF 手册建立元数据检索（音视频不包含自动语音识别转正文）。"""
    db = SessionLocal()
    try:
        row = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
        if not row:
            return
        mk = (row.media_kind or "").strip() or _handbook_suffix_to_media_kind(
            os.path.splitext(row.original_filename or "")[1].lower()
        )
        if mk == "pdf":
            return
        if mk not in ("video", "audio", "document"):
            row.search_status = "skipped"
            row.search_method = "none"
            row.search_body = ""
            row.search_error = ""
            row.updated_at = datetime.now()
            db.commit()
            try:
                _handbook_fts_delete_row(row_id)
            except Exception:
                pass
            return
        blob = _handbook_manual_search_blob(row).strip()
        row.search_body = blob[:HANDBOOK_SEARCH_BODY_MAX]
        row.search_method = "meta"
        row.search_status = "indexed" if blob else "skipped"
        row.search_error = ""
        row.updated_at = datetime.now()
        db.commit()
        if blob:
            _handbook_fts_upsert_row(int(row.id), int(row.client_id), row.original_filename or "", row.search_body)
        else:
            try:
                _handbook_fts_delete_row(row_id)
            except Exception:
                pass
    except Exception as e:
        try:
            r2 = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
            if r2 and (r2.media_kind or "").strip() in ("video", "audio", "document"):
                r2.search_status = "failed"
                r2.search_error = str(e)[:500]
                r2.updated_at = datetime.now()
                db.commit()
        except Exception:
            db.rollback()
        try:
            _handbook_fts_delete_row(row_id)
        except Exception:
            pass
    finally:
        db.close()


def _handbook_background_index_pdf(row_id: int) -> None:
    db = SessionLocal()
    try:
        row = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
        if not row:
            return
        mk = (row.media_kind or "").strip() or _handbook_suffix_to_media_kind(
            os.path.splitext(row.original_filename or "")[1].lower()
        )
        if mk != "pdf":
            row.search_status = "skipped"
            row.search_method = "none"
            row.search_error = ""
            row.search_body = ""
            row.updated_at = datetime.now()
            db.commit()
            _handbook_fts_delete_row(row_id)
            return
        abs_path = os.path.join(UPLOAD_DIR, (row.stored_path or "").strip())
        if not os.path.isfile(abs_path):
            row.search_status = "failed"
            row.search_method = ""
            row.search_error = "文件不存在"
            row.search_body = ""
            row.updated_at = datetime.now()
            db.commit()
            _handbook_fts_delete_row(row_id)
            return
        row.search_status = "indexing"
        row.search_error = ""
        db.commit()

        try:
            with open(abs_path, "rb") as fp:
                data = fp.read()
        except OSError as e:
            row.search_status = "failed"
            row.search_error = str(e)
            row.search_body = ""
            row.updated_at = datetime.now()
            db.commit()
            _handbook_fts_delete_row(row_id)
            return

        extracted, pg = _pdf_plain_text_and_pagecount(data)
        method = "text_extract"
        final_text = extracted
        if _pdf_text_suggests_ocr(extracted, max(pg, 1)):
            ocr_txt, err = _pdf_ocr_tesseract(data)
            if err:
                row.search_body = extracted[:HANDBOOK_SEARCH_BODY_MAX]
                row.updated_at = datetime.now()
                ext_ok = bool((extracted or "").strip())
                if ext_ok:
                    row.search_status = "indexed"
                    row.search_method = "text_extract"
                    row.search_error = f"OCR 未执行（{err[:400]}）"
                    db.commit()
                    _handbook_fts_upsert_row(row.id, row.client_id, row.original_filename or "", row.search_body)
                    return
                row.search_status = "failed"
                row.search_method = ""
                row.search_error = err
                db.commit()
                _handbook_fts_delete_row(row_id)
                return
            merged = ((ocr_txt or "").strip())
            final_text = merged if merged else extracted
            method = "ocr" if merged else method
        trimmed = final_text.strip()
        row.search_body = final_text[:HANDBOOK_SEARCH_BODY_MAX]
        row.search_method = method
        row.search_status = "indexed" if trimmed else "failed"
        row.search_error = "" if trimmed else "未识别到可读文本（可检查是否为加密 PDF）"
        row.updated_at = datetime.now()
        db.commit()
        if trimmed:
            _handbook_fts_upsert_row(row.id, row.client_id, row.original_filename or "", row.search_body)
        else:
            _handbook_fts_delete_row(row_id)
    except Exception as e:
        try:
            r2 = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
            if r2:
                r2.search_status = "failed"
                r2.search_error = str(e)[:500]
                r2.updated_at = datetime.now()
                db.commit()
        except Exception:
            db.rollback()
        try:
            _handbook_fts_delete_row(row_id)
        except Exception:
            pass
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


def authenticate_admin(user: str = Depends(authenticate)):
    """跨客户手册全文检索等能力：仅管理员。当前仅 admin 账号，后续多用户时在此扩展。"""
    if user != ADMIN_USER["username"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def _roster_strip_amount_for_ratio(v: str) -> str:
    return re.sub(r"[¥￥,\s\u00a0]", "", str(v or "").strip())


def _format_roster_salary_quote_ratio(monthly_quote_tax: str, pre_tax_salary: str) -> str:
    """薪资报价比 = 税前工资 / 月报价(含税)，百分比保留两位小数（与 GM% 展示风格一致）。"""
    q = _roster_strip_amount_for_ratio(monthly_quote_tax)
    p = _roster_strip_amount_for_ratio(pre_tax_salary)
    if not q or not p:
        return ""
    if not re.fullmatch(r"\d{4,6}", q) or not re.fullmatch(r"\d{4,6}", p):
        return ""
    qf = float(q)
    pf = float(p)
    if qf <= 0:
        return ""
    return f"{(pf / qf) * 100:.2f}%"


def _apply_roster_salary_quote_ratio(data: Dict[str, str]) -> None:
    data["salary_quote_ratio"] = _format_roster_salary_quote_ratio(
        data.get("monthly_quote_tax", ""),
        data.get("pre_tax_salary", ""),
    )


def _sql_roster_employment_left():
    """在职情况含「离职」即归入离职档案池（与离职率分析一致）。"""
    return RosterEntry.employment_status.like("%离职%")


def _sql_roster_employment_active_pool():
    """花名册在职池：空/未填视为在岗；含「离职」则不在花名册中展示。"""
    col = RosterEntry.employment_status
    return or_(col.is_(None), col == "", not_(col.like("%离职%")))


def _roster_entries_union_of_all_clients(db: Session) -> List[RosterEntry]:
    """整体花名册（在职池）：各客户已关联行，且不含离职档案。"""
    return (
        db.query(RosterEntry)
        .join(Client, RosterEntry.client_id == Client.id)
        .filter(_sql_roster_employment_active_pool())
        .order_by(RosterEntry.id)
        .all()
    )


def _roster_entries_turnover_pool(db: Session) -> List[RosterEntry]:
    """离职率分析：全部为离职档案行（可与在职花名册并存于同一表，互不展示重叠）。"""
    return db.query(RosterEntry).filter(_sql_roster_employment_left()).order_by(RosterEntry.id).all()


def _write_roster_backup_turnover_csv_all(rows: List[RosterEntry]) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"roster_backup_turnover_all__{ts}.csv"
    path = os.path.join(BACKUP_DIR, name)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(ROSTER_EXPORT_HEADERS)
        for e in rows:
            d = _roster_entry_to_dict(e)
            w.writerow([d.get(_CHINESE_ROSTER_HEADER_MAP[h], "") for h in ROSTER_EXPORT_HEADERS])
    return name


def _ensure_merged_turnover_employment(merged: Dict[str, str]) -> None:
    st = str(merged.get("employment_status", "")).strip()
    if not st or "离职" not in st:
        merged["employment_status"] = "离职"


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
        "salary_quote_ratio": _format_roster_salary_quote_ratio(
            e.monthly_quote_tax or "",
            e.pre_tax_salary or "",
        ),
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


def _validate_pipeline_payload(
    data: Dict[str, str],
    *,
    context: str = "保存",
    row_hint: str = "",
) -> None:
    allowed_interviewed = {"", "是", "放弃", "约面"}
    # 兼容少量历史脏值，避免旧记录无法打开/保存；前端新录入仅提供标准选项。
    allowed_result = {"", "通过", "不通过", "待定", "放弃面试", "待面ing"}
    name = str(data.get("full_name") or "").strip()
    interviewed = str(data.get("interviewed") or "").strip()
    interview_time = str(data.get("interview_time") or "").strip()
    result = str(data.get("result") or "").strip()
    got_offer = str(data.get("got_offer") or "").strip()
    onboarding_time = str(data.get("onboarding_time") or "").strip()
    onboarded = str(data.get("onboarded") or "").strip()

    label_parts = [context]
    if row_hint:
        label_parts.append(row_hint)
    if name:
        label_parts.append(name)
    prefix = "｜".join(label_parts)

    if interviewed not in allowed_interviewed:
        raise HTTPException(status_code=400, detail=f"{prefix}：是否面试仅支持填写“是 / 放弃 / 约面”")
    if result not in allowed_result:
        raise HTTPException(status_code=400, detail=f"{prefix}：面试结果仅支持填写“通过 / 不通过 / 待定”")
    if got_offer and got_offer not in ("是", "否"):
        raise HTTPException(status_code=400, detail=f"{prefix}：是否接offer仅支持填写“是”或“否”")
    if interviewed == "是" and not interview_time:
        raise HTTPException(status_code=400, detail=f"{prefix}：是否面试为“是”时，必须填写面试时间")
    if got_offer and result != "通过":
        raise HTTPException(status_code=400, detail=f"{prefix}：已填写是否接offer时，面试结果必须为“通过”")

    has_onboarding_signal = bool(onboarding_time) or ("已入职" in onboarded) or ("待入职" in onboarded)
    if has_onboarding_signal and not got_offer:
        raise HTTPException(status_code=400, detail=f"{prefix}：已填写入职时间或将是否入职改为“X月已入职/待入职”时，必须填写是否接offer")
    if has_onboarding_signal and result != "通过":
        raise HTTPException(status_code=400, detail=f"{prefix}：已填写入职时间或已标记待入职/已入职时，面试结果必须为“通过”")
    if has_onboarding_signal and got_offer == "否":
        raise HTTPException(status_code=400, detail=f"{prefix}：已填写入职时间或已标记待入职/已入职时，是否接offer不能为“否”")


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


def _validate_interview_business_fields(data: Dict[str, str]) -> None:
    if len(str(data.get("delivery_judgment", "")).strip()) < 20:
        raise HTTPException(status_code=400, detail="交付判断至少需要填写20个字")
    if len(str(data.get("delivery_todos", "")).strip()) < 10:
        raise HTTPException(status_code=400, detail="交付待办事项至少需要填写10个字")


def _assert_interview_delivery_judgment_unique(
    db: Session,
    client_id: int,
    full_name: str,
    delivery_judgment: str,
    exclude_row_id: Optional[int] = None,
) -> None:
    name = str(full_name or "").strip()
    judgment = str(delivery_judgment or "").strip()
    if not name or not judgment:
        return
    q = db.query(DeliveryInterviewEntry).filter(DeliveryInterviewEntry.client_id == client_id)
    if exclude_row_id is not None:
        q = q.filter(DeliveryInterviewEntry.id != exclude_row_id)
    for row in q.all():
        if str(row.full_name or "").strip() == name and str(row.delivery_judgment or "").strip() == judgment:
            raise HTTPException(status_code=409, detail="同一员工的多条访谈记录中，交付判断内容不能重复")


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
        "delivery_communication",
        "business_action",
        "bp_involved",
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
    "项目": "business_line",
    "入职日期": "entry_date",
    "入职时间": "entry_date",
    "转正时间": "regularization_date",
    "月报价(含税)": "monthly_quote_tax",
    "报价（含税）": "monthly_quote_tax",
    "报价": "monthly_quote_tax",
    "税前工资": "pre_tax_salary",
    "薪资": "pre_tax_salary",
    "薪资报价比": "salary_quote_ratio",
    "GM$": "gms",
    "GMS": "gms",  # 旧表头兼容
    "GM%": "gm_pct",
    "员工+1": "employee_plus1",
    "员工加1": "employee_plus1",
    "入职渠道": "zntx_onboarding_channel",
    "打卡": "zntx_attendance_checkin",
    "补卡": "zntx_attendance_makeup",
    "员工+2": "employee_plus2",
    "接口": "interface_contact",
    "项目释放日期": "project_release_date",
    "项目释放时间": "project_release_date",
    "公司离职日期": "company_resign_date",
    "离职时间": "company_resign_date",
    "主动/被动": "zntx_separation_type",
    "主动被动": "zntx_separation_type",
    "工号": "zntx_staff_no",
    "中诺工号": "zntx_staff_no",
    "中河工号": "zntx_staff_no",  # 兼容旧误写
    "离职类型": "zntx_separation_type",
    "补偿金": "zntx_compensation_amount",
    "薪酬金": "zntx_compensation_amount",
    "交付沟通": "delivery_communication",
    "业务处理动作": "business_action",
    "BP参与与否": "bp_involved",
    "BP参与": "bp_involved",
    "BP参与动作": "bp_involved",
    "bp参与动作": "bp_involved",
    "离职或释放原因": "leave_reason",
    "离职和离职原因": "leave_reason",
    "释放/离职原因": "leave_reason",
    "释放成功离职原因": "leave_reason",
    "备注": "remarks",
}


# 花名册「客户」：单元格中含左侧关键字即视为右侧 clients.name；
# 花名册内统一存左侧简称/展示名，右侧仅用于匹配客户主数据（须与客户管理中全称完全一致；左侧越长越优先匹配）
ROSTER_CUSTOMER_ALIAS_RULES: Tuple[Tuple[str, str], ...] = (
    ("远景智能", "远景智能"),
    ("中诺", "中诺通讯"),
    ("华勤", "华勤科技"),
    ("帷幄", "帷幄科技"),
    ("日产", "日产中国"),
    ("元枢", "元枢智汇"),
)


def _resolve_roster_customer_client(db: Session, raw: str) -> Tuple[Optional[Client], str]:
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


def _analyze_roster_csv_headers(text: str) -> Dict[str, Any]:
    """返回 CSV 首行表头的识别情况，便于导入提示未识别列。"""
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
        if _map_roster_csv_header(name):
            matched_headers.append(name)
        else:
            unmatched_headers.append(name)
    return {
        "headers": headers,
        "matched_headers": matched_headers,
        "unmatched_headers": unmatched_headers,
    }


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
    "交付沟通",
    "业务处理动作",
    "BP参与与否",
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
    "交付沟通",
    "业务处理动作",
    "BP参与与否",
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

        old_hb_prefix = f"handbooks/{old_folder}/"
        new_hb_prefix = f"handbooks/{new_folder}/"
        old_hb_dir = os.path.join(UPLOAD_DIR, "handbooks", old_folder)
        new_hb_dir = os.path.join(UPLOAD_DIR, "handbooks", new_folder)
        if old_folder != new_folder and os.path.isdir(old_hb_dir) and not os.path.exists(new_hb_dir):
            os.makedirs(os.path.join(UPLOAD_DIR, "handbooks"), exist_ok=True)
            shutil.move(old_hb_dir, new_hb_dir)
            hb_rows = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.client_id == client_id).all()
            for hb in hb_rows:
                if (hb.stored_path or "").startswith(old_hb_prefix):
                    hb.stored_path = hb.stored_path.replace(old_hb_prefix, new_hb_prefix, 1)

    if updates:
        log = AuditLog(client_id=client_id, operator=user, action="; ".join(updates))
        db.add(log)
    db.commit()
    return {"status": "ok"}


@app.delete("/api/clients/{client_id}")
async def delete_client(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")
    client_folder = f"{client.name}_{client.id}"
    src_path = os.path.join(UPLOAD_DIR, client_folder)
    if os.path.exists(src_path):
        shutil.move(src_path, os.path.join(TRASH_DIR, f"{client_folder}_{int(time.time())}"))
    hb_dir = os.path.join(UPLOAD_DIR, "handbooks", client_folder)
    if os.path.isdir(hb_dir):
        shutil.move(hb_dir, os.path.join(TRASH_DIR, f"handbooks_{client_folder}_{int(time.time())}"))
    db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.client_id == client_id).delete()

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


def _handbook_outline_coerce(raw: Optional[str]) -> List[Dict[str, Any]]:
    try:
        v = json.loads(raw or "[]")
    except Exception:
        return []
    return v if isinstance(v, list) else []


def _handbook_cues_from_json_string(raw: Optional[str]) -> List[Dict[str, Any]]:
    try:
        v = json.loads(raw or "[]")
    except Exception:
        return []
    return _handbook_normalize_media_cues(v if isinstance(v, list) else [])


def _handbook_dt_iso(val: Any) -> str:
    if val is None or val == "":
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    try:
        return str(val)
    except Exception:
        return ""


def _handbook_row_to_dict(r: DeliveryHandbookFile) -> Dict[str, Any]:
    sp = (r.stored_path or "").strip()
    mk = (getattr(r, "media_kind", None) or "").strip()
    if not mk:
        mk = _handbook_suffix_to_media_kind(os.path.splitext(r.original_filename or "")[1].lower())
    outline = _handbook_outline_coerce(getattr(r, "pdf_outline_json", None))
    return {
        "id": r.id,
        "client_id": r.client_id,
        "original_filename": r.original_filename or "",
        "stored_path": sp,
        "preview_url": f"/previews/{sp}" if sp else "",
        "version_label": (getattr(r, "version_label", None) or "") or "",
        "status": _handbook_normalize_status(getattr(r, "status", None) or "draft"),
        "tags": _handbook_parse_json_list(getattr(r, "tags_json", None)),
        "permission_departments": _handbook_parse_json_list(getattr(r, "permission_departments_json", None)),
        "permission_levels": _handbook_parse_json_list(getattr(r, "permission_levels_json", None)),
        "media_kind": mk,
        "pdf_outline": outline,
        "media_cues": _handbook_cues_from_json_string(getattr(r, "media_cues_json", None)),
        "search_status": ("pending" if getattr(r, "search_status", None) is None else str(r.search_status).strip())
        or "pending",
        "search_method": (getattr(r, "search_method", None) or "").strip(),
        "search_error": (getattr(r, "search_error", None) or "").strip(),
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "updated_at": _handbook_dt_iso(getattr(r, "updated_at", None)),
    }


@app.get("/api/clients/{client_id}/delivery/handbooks")
async def list_delivery_handbooks(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    rows = (
        db.query(DeliveryHandbookFile)
        .filter(DeliveryHandbookFile.client_id == client_id)
        .order_by(desc(DeliveryHandbookFile.created_at))
        .all()
    )
    return [_handbook_row_to_dict(r) for r in rows]


@app.post("/api/clients/{client_id}/delivery/handbooks")
async def upload_delivery_handbooks(
    client_id: int,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(default=[]),
    version_label: str = Form(default=""),
    status: str = Form(default="draft"),
    tags: str = Form(default=""),
    permission_departments: str = Form(default=""),
    permission_levels: str = Form(default=""),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    if not files:
        raise HTTPException(status_code=400, detail="请选择文件")
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")
    rel_dir = _handbook_client_dir_rel(client)
    abs_dir = os.path.join(UPLOAD_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    ts_base = int(time.time() * 1000000)
    st = _handbook_normalize_status(status)
    tags_js = _handbook_labels_to_json_array(tags)
    pd_js = _handbook_labels_to_json_array(permission_departments)
    pl_js = _handbook_labels_to_json_array(permission_levels)
    vlabel = str(version_label or "").strip()
    payloads: List[Tuple[str, bytes, str, str, str]] = []
    for idx, up in enumerate(files):
        raw_name = up.filename or ""
        ext = os.path.splitext(raw_name)[1].lower()
        if ext not in HANDBOOK_ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"不支持的文件类型：{raw_name or '（未命名）'}，"
                    "允许：PDF、Word、常见音视频（mp4/webm/mp3 等）"
                ),
            )
        content_bytes = await up.read()
        if len(content_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"文件超过20MB限制：{raw_name or '未命名'}")
        safe = _safe_handbook_filename(raw_name)
        if not os.path.splitext(safe)[1]:
            safe = safe + ext
        stored_rel = f"{rel_dir}/{ts_base}_{idx}_{safe}"
        mk = _handbook_suffix_to_media_kind(ext)
        payloads.append((stored_rel, content_bytes, raw_name, safe, mk))
    saved: List[DeliveryHandbookFile] = []
    now = datetime.now()
    for stored_rel, content_bytes, raw_name, safe, mk in payloads:
        with open(os.path.join(UPLOAD_DIR, stored_rel), "wb") as f:
            f.write(content_bytes)
        outline_js = "[]"
        if mk == "pdf":
            tree = _pdf_bytes_to_outline_tree(content_bytes)
            outline_js = json.dumps(tree, ensure_ascii=False)
        row = DeliveryHandbookFile(
            client_id=client_id,
            original_filename=raw_name or safe,
            stored_path=stored_rel,
            version_label=vlabel,
            status=st,
            tags_json=tags_js,
            permission_departments_json=pd_js,
            permission_levels_json=pl_js,
            media_kind=mk,
            pdf_outline_json=outline_js,
            media_cues_json="[]",
            search_status=("pending" if mk in ("pdf", "video", "audio", "document") else "skipped"),
            search_method=("none" if mk not in ("pdf", "video", "audio", "document") else ""),
            search_error="",
            search_body="",
            updated_at=now,
        )
        db.add(row)
        saved.append(row)
    db.commit()
    for row in saved:
        db.refresh(row)
        if row.media_kind == "pdf":
            background_tasks.add_task(_handbook_background_index_pdf, int(row.id))
        elif row.media_kind in ("video", "audio", "document"):
            background_tasks.add_task(_handbook_background_index_manual_meta, int(row.id))
    return [_handbook_row_to_dict(r) for r in saved]


@app.patch("/api/clients/{client_id}/delivery/handbooks/{row_id}")
async def patch_delivery_handbook(
    client_id: int,
    row_id: int,
    background_tasks: BackgroundTasks,
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    row = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
    if not row or row.client_id != client_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    if not isinstance(body, dict):
        body = {}
    if "version_label" in body:
        row.version_label = str(body.get("version_label") or "").strip()
    if "status" in body:
        row.status = _handbook_normalize_status(str(body.get("status") or ""))
    if "tags" in body:
        t = body.get("tags")
        if isinstance(t, list):
            row.tags_json = json.dumps([str(x).strip() for x in t if str(x).strip()], ensure_ascii=False)
        else:
            row.tags_json = _handbook_labels_to_json_array(str(t or ""))
    if "permission_departments" in body:
        t = body.get("permission_departments")
        if isinstance(t, list):
            row.permission_departments_json = json.dumps(
                [str(x).strip() for x in t if str(x).strip()], ensure_ascii=False
            )
        else:
            row.permission_departments_json = _handbook_labels_to_json_array(str(t or ""))
    if "permission_levels" in body:
        t = body.get("permission_levels")
        if isinstance(t, list):
            row.permission_levels_json = json.dumps(
                [str(x).strip() for x in t if str(x).strip()], ensure_ascii=False
            )
        else:
            row.permission_levels_json = _handbook_labels_to_json_array(str(t or ""))
    if "media_cues" in body:
        row.media_cues_json = json.dumps(
            _handbook_normalize_media_cues(body.get("media_cues")), ensure_ascii=False
        )
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    mk = (row.media_kind or "").strip() or _handbook_suffix_to_media_kind(
        os.path.splitext(row.original_filename or "")[1].lower()
    )
    if mk in ("video", "audio", "document"):
        background_tasks.add_task(_handbook_background_index_manual_meta, int(row.id))
    return _handbook_row_to_dict(row)


@app.post("/api/clients/{client_id}/delivery/handbooks/{row_id}/rebuild-pdf-outline")
async def rebuild_handbook_pdf_outline(
    client_id: int,
    row_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    row = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
    if not row or row.client_id != client_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    mk = (row.media_kind or "").strip() or _handbook_suffix_to_media_kind(
        os.path.splitext(row.original_filename or "")[1].lower()
    )
    if mk != "pdf":
        raise HTTPException(status_code=400, detail="仅支持 PDF 重新提取目录")
    path = os.path.join(UPLOAD_DIR, row.stored_path)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    with open(path, "rb") as f:
        data = f.read()
    tree = _pdf_bytes_to_outline_tree(data)
    row.pdf_outline_json = json.dumps(tree, ensure_ascii=False)
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return _handbook_row_to_dict(row)


@app.delete("/api/clients/{client_id}/delivery/handbooks/{row_id}")
async def delete_delivery_handbook(
    client_id: int,
    row_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    row = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
    if not row or row.client_id != client_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    path = os.path.join(UPLOAD_DIR, row.stored_path)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
    rid = int(row.id)
    db.delete(row)
    db.commit()
    try:
        _handbook_fts_delete_row(rid)
    except Exception:
        pass
    return {"status": "ok"}


@app.get("/api/delivery/handbooks/search")
async def delivery_handbooks_search_cross_client(
    q: str,
    limit: int = 40,
    db: Session = Depends(get_db),
    user: str = Depends(authenticate_admin),
):
    """跨客户检索手册：PDF 为正文+OCR；音视频/Word 为元数据+锚点文案。FTS5 + 子串回退。"""
    q_strip = (q or "").strip()
    if not q_strip:
        raise HTTPException(status_code=400, detail="请输入检索词")
    lim = max(1, min(int(limit or 40), 100))
    fq = _handbook_build_fts_query(q_strip)
    seen: Dict[int, Dict[str, Any]] = {}

    def row_to_hit(hrow: DeliveryHandbookFile) -> Dict[str, Any]:
        c = db.query(Client).filter(Client.id == hrow.client_id).first()
        d = _handbook_row_to_dict(hrow)
        d["client_name"] = (c.name if c else "") or ""
        d["snippet"] = _handbook_search_snippet(
            hrow.search_body, q_strip, max_len=HANDBOOK_SEARCH_SNIPPET_LIST, collapse_ws=True
        )
        d["excerpt_detail"] = _handbook_search_snippet(
            hrow.search_body, q_strip, max_len=HANDBOOK_SEARCH_SNIPPET_MODAL, collapse_ws=False
        )
        return d

    # ① FTS（排序优；部分中文 QUERY 可能与分词不符导致零结果）
    if fq:
        try:
            with engine.connect() as conn:
                frows = (
                    conn.execute(
                        text(
                            "SELECT handbook_fts.rowid AS id, handbook_fts.client_id AS client_id, "
                            "bm25(handbook_fts) AS rk FROM handbook_fts "
                            "WHERE handbook_fts MATCH :match ORDER BY rk LIMIT :lim"
                        ),
                        {"match": fq, "lim": lim},
                    )
                    .mappings()
                    .all()
                )
            for m in frows:
                hid = int(m["id"])
                if hid in seen or len(seen) >= lim:
                    continue
                hrow = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == hid).first()
                if not hrow or hrow.search_status != "indexed":
                    continue
                seen[hid] = row_to_hit(hrow)
        except Exception:
            pass

    # ② 子串检索（与用户可见「已索引」正文一致）
    if len(seen) < lim:
        needle = q_strip
        tail = lim - len(seen)
        sub_rows = (
            db.query(DeliveryHandbookFile)
            .filter(
                DeliveryHandbookFile.media_kind.in_(["pdf", "video", "audio", "document"]),
                DeliveryHandbookFile.search_status == "indexed",
                or_(
                    func.instr(DeliveryHandbookFile.search_body, needle) > 0,
                    func.instr(DeliveryHandbookFile.original_filename, needle) > 0,
                ),
            )
            .order_by(desc(DeliveryHandbookFile.updated_at))
            .limit(max(tail * 4, 8))
            .all()
        )
        for hrow in sub_rows:
            if len(seen) >= lim:
                break
            if int(hrow.id) in seen:
                continue
            seen[int(hrow.id)] = row_to_hit(hrow)

    out_list = list(seen.values())[:lim]
    return {"query": q_strip, "results": out_list}


@app.post("/api/handbook-assistant/chat")
async def handbook_assistant_chat(
    body: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate_admin),
):
    """全局悬浮问答第一版：检索式回答 + 可点击来源；后续可替换为 LLM RAG。"""
    q_strip = str((body or {}).get("q") or (body or {}).get("query") or "").strip()
    if not q_strip:
        raise HTTPException(status_code=400, detail="请输入问题或检索词")
    lim = max(1, min(int((body or {}).get("limit") or 6), 12))
    fq = _handbook_build_fts_query(q_strip)
    terms = _handbook_query_terms(q_strip)
    seen: Dict[int, DeliveryHandbookFile] = {}

    if fq:
        try:
            with engine.connect() as conn:
                frows = (
                    conn.execute(
                        text(
                            "SELECT handbook_fts.rowid AS id, bm25(handbook_fts) AS rk "
                            "FROM handbook_fts WHERE handbook_fts MATCH :match ORDER BY rk LIMIT :lim"
                        ),
                        {"match": fq, "lim": lim},
                    )
                    .mappings()
                    .all()
                )
            for m in frows:
                hid = int(m["id"])
                if hid in seen:
                    continue
                hrow = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == hid).first()
                if (
                    hrow
                    and hrow.search_status == "indexed"
                    and (
                        _handbook_text_matches(hrow.search_body, terms)
                        or _handbook_text_matches(hrow.original_filename, terms)
                    )
                ):
                    seen[hid] = hrow
        except Exception:
            pass

    if len(seen) < lim:
        tail = lim - len(seen)
        sub_rows = (
            db.query(DeliveryHandbookFile)
            .filter(
                DeliveryHandbookFile.media_kind.in_(["pdf", "video", "audio", "document"]),
                DeliveryHandbookFile.search_status == "indexed",
                or_(
                    func.instr(DeliveryHandbookFile.search_body, q_strip) > 0,
                    func.instr(DeliveryHandbookFile.original_filename, q_strip) > 0,
                ),
            )
            .order_by(desc(DeliveryHandbookFile.updated_at))
            .limit(max(tail * 4, 8))
            .all()
        )
        for hrow in sub_rows:
            if len(seen) >= lim:
                break
            seen.setdefault(int(hrow.id), hrow)

    sources: List[Dict[str, Any]] = []
    for hrow in list(seen.values())[:lim]:
        if not (
            _handbook_text_matches(hrow.search_body, terms)
            or _handbook_text_matches(hrow.original_filename, terms)
        ):
            continue
        c = db.query(Client).filter(Client.id == hrow.client_id).first()
        mk = (hrow.media_kind or "").strip() or _handbook_suffix_to_media_kind(
            os.path.splitext(hrow.original_filename or "")[1].lower()
        )
        summary = _handbook_search_snippet(
            hrow.search_body, q_strip, max_len=760, collapse_ws=True
        )
        source: Dict[str, Any] = {
            "client_id": int(hrow.client_id),
            "client_name": (c.name if c else "") or "",
            "handbook_id": int(hrow.id),
            "filename": hrow.original_filename or "",
            "media_kind": mk,
            "snippet": summary,
            "summary": summary,
            "matched_terms": terms,
            "search_method": (hrow.search_method or "").strip(),
        }
        params = f"handbook_id={int(hrow.id)}"
        if mk == "pdf":
            page = _handbook_locate_pdf_page(hrow, q_strip)
            source["page"] = page
            params += f"&page={page}"
        elif mk in ("video", "audio"):
            seconds = _handbook_locate_media_seconds(hrow, q_strip)
            if seconds is not None:
                source["seconds"] = seconds
                params += f"&seconds={seconds:g}"
        source["url"] = f"/delivery/handbook/{int(hrow.client_id)}?{params}"
        sources.append(source)

    if sources:
        client_names = [s.get("client_name") or f"客户#{s.get('client_id')}" for s in sources[:3]]
        answer = (
            f"找到 {len(sources)} 条相关来源，主要来自 {'、'.join(client_names)}。"
            "下面的来源参考可直接打开对应手册位置。"
        )
    else:
        answer = "暂未找到相关手册来源。可尝试换一个关键词，或先在手册页同步 FTS / 重排索引。"
    return {"query": q_strip, "answer": answer, "sources": sources, "mode": "retrieval"}


@app.post("/api/delivery/handbooks/sync-fts-indexed")
async def delivery_handbooks_sync_fts_from_body(
    db: Session = Depends(get_db),
    user: str = Depends(authenticate_admin),
):
    """重写 FTS：PDF 用已索引正文；音视频/文档用元数据摘录。"""
    rows = (
        db.query(DeliveryHandbookFile)
        .filter(
            DeliveryHandbookFile.media_kind == "pdf",
            DeliveryHandbookFile.search_status == "indexed",
            DeliveryHandbookFile.search_body.isnot(None),
            DeliveryHandbookFile.search_body != "",
        )
        .all()
    )
    synced = 0
    for r in rows:
        try:
            _handbook_fts_upsert_row(int(r.id), int(r.client_id), r.original_filename or "", r.search_body or "")
            synced += 1
        except Exception:
            continue
    media_rows = (
        db.query(DeliveryHandbookFile)
        .filter(DeliveryHandbookFile.media_kind.in_(["video", "audio", "document"]))
        .all()
    )
    for r in media_rows:
        blob = _handbook_manual_search_blob(r).strip()
        if not blob:
            try:
                _handbook_fts_delete_row(int(r.id))
            except Exception:
                pass
            continue
        r.search_body = blob[:HANDBOOK_SEARCH_BODY_MAX]
        r.search_method = "meta"
        r.search_status = "indexed"
        r.search_error = ""
        r.updated_at = datetime.now()
        try:
            db.commit()
            _handbook_fts_upsert_row(int(r.id), int(r.client_id), r.original_filename or "", r.search_body or "")
            synced += 1
        except Exception:
            db.rollback()
            continue
    return {"synced": synced}


@app.post("/api/delivery/handbooks/reindex-stale")
async def delivery_handbooks_reindex_stale(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: str = Depends(authenticate_admin),
):
    """将未完成索引的条目重新排队（PDF 抽正文；音视频/Word 建元数据索引）。"""
    rows = (
        db.query(DeliveryHandbookFile)
        .filter(
            or_(
                and_(
                    DeliveryHandbookFile.media_kind == "pdf",
                    DeliveryHandbookFile.search_status.in_(["pending", "failed", "indexing"]),
                ),
                and_(
                    DeliveryHandbookFile.media_kind.in_(["video", "audio", "document"]),
                    DeliveryHandbookFile.search_status.in_(["pending", "failed", "indexing"]),
                ),
            )
        )
        .all()
    )
    for r in rows:
        if r.media_kind == "pdf":
            background_tasks.add_task(_handbook_background_index_pdf, int(r.id))
        else:
            background_tasks.add_task(_handbook_background_index_manual_meta, int(r.id))
    return {"queued": len(rows)}


@app.get("/api/roster")
async def roster_list_all(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    rows = _roster_entries_union_of_all_clients(db)
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
    _apply_roster_salary_quote_ratio(data)
    _assert_roster_contact_unique_global(db, data.get("contact_info", ""))
    mc, normalized_cn = _resolve_roster_customer_client(db, data.get("customer_name", ""))
    if not mc:
        raise HTTPException(
            status_code=400,
            detail="整体花名册仅汇总各客户花名册：「客户」须能匹配到系统中的客户，或请到对应客户下的花名册中新增。",
        )
    data["customer_name"] = normalized_cn
    entry = RosterEntry(client_id=mc.id, **data)
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
    rows = (
        db.query(RosterEntry)
        .filter(RosterEntry.client_id == client_id, _sql_roster_employment_active_pool())
        .order_by(RosterEntry.id)
        .all()
    )
    return [_roster_entry_to_dict(r) for r in rows]


@app.get("/api/roster/turnover")
async def roster_turnover_list(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    """离职率分析专用列表（仅 employment 含「离职」的行）。"""
    rows = _roster_entries_turnover_pool(db)
    return [_roster_entry_to_dict(r) for r in rows]


def _roster_distinct_client_ids(db: Session) -> List[int]:
    """花名册中出现过的客户（roster_entries.client_id 去重），与整体/分客户花名册数据来源一致。"""
    rows = (
        db.query(RosterEntry.client_id)
        .filter(RosterEntry.client_id.isnot(None), RosterEntry.client_id > 0)
        .distinct()
        .all()
    )
    return sorted({int(r[0]) for r in rows if r[0] is not None})


def _dashboard_business_options(db: Session) -> List[Dict[str, Any]]:
    opts: List[Dict[str, Any]] = []
    for cid in _roster_distinct_client_ids(db):
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


def _dashboard_scope_client_ids(
    db: Session, scope: str, business_key: str
) -> Tuple[List[int], str]:
    roster_cids = _roster_distinct_client_ids(db)
    sk = str(business_key or "").strip()
    if str(scope or "").strip().lower() == "business" and sk:
        c, _ = _resolve_roster_customer_client(db, sk)
        if not c:
            raise HTTPException(
                status_code=400,
                detail="未识别客户，请使用与花名册「客户」列一致的简称或「客户管理」中的全称",
            )
        if c.id not in set(roster_cids):
            raise HTTPException(status_code=400, detail="花名册中尚无该客户的数据")
        return [c.id], (c.name or "").strip() or sk
    return roster_cids, "整体客户"


def _roster_entries_for_client_ids(db: Session, client_ids: List[int]) -> List[RosterEntry]:
    if not client_ids:
        return []
    return (
        db.query(RosterEntry)
        .filter(RosterEntry.client_id.in_(client_ids))
        .order_by(RosterEntry.id)
        .all()
    )


def _roster_entries_for_business_scope(db: Session, client_ids: List[int]) -> List[RosterEntry]:
    """单一业务看板：该客户下全部行，加上 client 未绑但「客户」可解析为同一客户的离职档案行。

    与整体看板类似，避免离职导入为 client_id=0 时，单一业务下分子恒为 0、分母却含已绑行。"""
    if not client_ids:
        return []
    target_id = int(client_ids[0])
    by_id: Dict[int, RosterEntry] = {e.id: e for e in _roster_entries_for_client_ids(db, client_ids)}
    orphan_turnover = and_(
        or_(RosterEntry.client_id.is_(None), RosterEntry.client_id == 0),
        _sql_roster_employment_left(),
    )
    for r in db.query(RosterEntry).filter(orphan_turnover).order_by(RosterEntry.id).all():
        if r.id in by_id:
            continue
        c, _ = _resolve_roster_customer_client(db, r.customer_name or "")
        if c and c.id == target_id:
            by_id[r.id] = r
    return sorted(by_id.values(), key=lambda e: e.id)


def _roster_entries_department_dashboard(db: Session) -> List[RosterEntry]:
    """花名册整体看板：已关联客户的全部行 + client_id 未绑定的离职档案行。

    ``_roster_distinct_client_ids`` 会排除 ``client_id`` 为空/0 的行；这些行仍会出现在
    ``/api/roster/turnover`` 列表中，若不在此并入，会出现「整体看板离职数少于列表」。"""
    roster_cids = _roster_distinct_client_ids(db)
    orphan_turnover = and_(
        or_(RosterEntry.client_id.is_(None), RosterEntry.client_id == 0),
        _sql_roster_employment_left(),
    )
    filt = or_(RosterEntry.client_id.in_(roster_cids), orphan_turnover) if roster_cids else orphan_turnover
    return db.query(RosterEntry).filter(filt).order_by(RosterEntry.id).all()


def _row_is_turnover_pool(r: RosterEntry) -> bool:
    st = str(r.employment_status or "")
    return "离职" in st


def _employed_on_date_row(r: RosterEntry, d: date) -> bool:
    """某日是否计为在职（计头计尾：离职日当天仍计为在职）。无入职日期的行不计入分母。"""
    entry_d = _parse_loose_date(str(r.entry_date or ""))
    if not entry_d:
        return False
    if d < entry_d:
        return False
    resign_d = _parse_loose_date(str(r.company_resign_date or ""))
    if resign_d and d > resign_d:
        return False
    return True


def _headcount_on_date(rows: List[RosterEntry], d: date) -> int:
    return sum(1 for r in rows if _employed_on_date_row(r, d))


def _avg_headcount_period(rows: List[RosterEntry], d0: date, d1: date) -> Tuple[float, int, int]:
    h0 = _headcount_on_date(rows, d0)
    h1 = _headcount_on_date(rows, d1)
    return (h0 + h1) / 2.0, h0, h1


def _departure_events_in_range(rows: List[RosterEntry], d0: date, d1: date) -> List[RosterEntry]:
    out: List[RosterEntry] = []
    for r in rows:
        if not _row_is_turnover_pool(r):
            continue
        rd = _parse_loose_date(str(r.company_resign_date or ""))
        if not rd:
            continue
        if d0 <= rd <= d1:
            out.append(r)
    return out


def _onboarding_events_in_range(rows: List[RosterEntry], d0: date, d1: date) -> List[RosterEntry]:
    """按入职日期（entry_date）落在 [d0, d1] 内计数，与看板范围 rows_all 一致（含在职池与离职档案行）。"""
    out: List[RosterEntry] = []
    for r in rows:
        ed = _parse_loose_date(str(r.entry_date or ""))
        if not ed:
            continue
        if d0 <= ed <= d1:
            out.append(r)
    return out


def _classify_separation_kind(raw: str) -> str:
    """看板统计：主动 / 被动 / 转出 / 未标注（关键词顺序：转出、被动、主动）。"""
    s = str(raw or "")
    if "转出" in s:
        return "transfer"
    if "被动" in s:
        return "passive"
    if "主动" in s:
        return "active"
    return "unknown"


def _zntx_is_business_termination_type(raw: Optional[str]) -> bool:
    """花名册整体看板用：「离职类型」列含「业务离职」的离职事件（与主/被动/转出可并存、独立计数）。"""
    return "业务离职" in str(raw or "")


def _departure_business_termination_subset(rows: List[RosterEntry]) -> List[RosterEntry]:
    return [r for r in rows if _zntx_is_business_termination_type(r.zntx_separation_type)]


def _tenure_days_at_resign(r: RosterEntry) -> Optional[int]:
    entry_d = _parse_loose_date(str(r.entry_date or ""))
    resign_d = _parse_loose_date(str(r.company_resign_date or ""))
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
    """各月无离职、无入职、平均在职为 0：可自趋势表首尾裁掉，减少成片的空行。"""
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
    pd = _parse_loose_date(s)
    return pd if isinstance(pd, date) else None


def _norm_pos_loc(val: str, fallback: str = "(未填)") -> str:
    s = str(val or "").strip()
    return s if s else fallback


def _departures_by_business_department(
    db: Session, deps_p: List[RosterEntry]
) -> List[Dict[str, Any]]:
    """花名册整体：按客户/业务名汇总同期离职人数。优先用 client_id 对应客户名，否则用「客户」列。"""
    if not deps_p:
        return []
    cids = {int(r.client_id) for r in deps_p if r.client_id and int(r.client_id) > 0}
    id_to_name: Dict[int, str] = {}
    if cids:
        for c in db.query(Client).filter(Client.id.in_(cids)).all():
            id_to_name[c.id] = (c.name or "").strip() or f"客户#{c.id}"
    cnt = Counter()
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
    """悬停名单右侧标签：转出 / 被动 / 主动 / 未标注（与统计口径分流可并存）。"""
    s = str(raw or "")
    if "转出" in s:
        return "转出"
    if "被动" in s:
        return "被动"
    if "主动" in s:
        return "主动"
    return "未标注"


def _departure_detail_entries(rows: List[RosterEntry]) -> List[Dict[str, str]]:
    """看板悬停展示：按离职日、姓名排序；每人含名单文案与主动/被动/转出标签。"""

    def _sort_key(r: RosterEntry) -> Tuple[date, str]:
        rd = _parse_loose_date(str(r.company_resign_date or ""))
        return (rd if isinstance(rd, date) else date.min, str(r.full_name or ""))

    out: List[Dict[str, str]] = []
    for r in sorted(rows, key=_sort_key):
        nm = str(r.full_name or "").strip() or "（无姓名）"
        rd = _parse_loose_date(str(r.company_resign_date or ""))
        ds = rd.isoformat() if isinstance(rd, date) else str(r.company_resign_date or "").strip() or "—"
        cust = str(r.customer_name or r.business_line or "").strip()
        suf = f" · {cust}" if cust else ""
        out.append(
            {
                "detail": f"{nm} · 离职日 {ds}{suf}",
                "separation": _separation_detail_label(r.zntx_separation_type),
            }
        )
    return out


def _onboarding_detail_entries(rows: List[RosterEntry]) -> List[Dict[str, str]]:
    """看板悬停：按入职日、姓名排序。"""

    def _sort_key(r: RosterEntry) -> Tuple[date, str]:
        ed = _parse_loose_date(str(r.entry_date or ""))
        return (ed if isinstance(ed, date) else date.min, str(r.full_name or ""))

    out: List[Dict[str, str]] = []
    for r in sorted(rows, key=_sort_key):
        nm = str(r.full_name or "").strip() or "（无姓名）"
        ed = _parse_loose_date(str(r.entry_date or ""))
        ds = ed.isoformat() if isinstance(ed, date) else str(r.entry_date or "").strip() or "—"
        cust = str(r.customer_name or r.business_line or "").strip()
        suf = f" · {cust}" if cust else ""
        out.append({"detail": f"{nm} · 入职日 {ds}{suf}", "separation": ""})
    return out


@app.get("/api/roster/turnover/dashboard")
async def roster_turnover_dashboard(
    scope: str = "department",
    business_key: str = "",
    trend_months: int = 12,
    period_start: str = "",
    period_end: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    """
    离职率分析看板：分子为期内离职人数（离职档案行且离职日期落在区间内）；
    分母为（期初在职+期末在职）/2；在职按花名册行入职/离职日推断，无入职日期的行不计入分母。
    """
    tm = max(1, min(int(trend_months or 12), 36))
    client_ids, scope_title = _dashboard_scope_client_ids(db, scope, business_key)
    if str(scope or "").strip().lower() == "business":
        rows_all = _roster_entries_for_business_scope(db, client_ids)
    else:
        rows_all = _roster_entries_department_dashboard(db)
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

    # 主动/被动/转出/未标注 占比分母 = 同期总离职人数 dep_n（与主 KPI「离职数」相同）
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
            # 分母 0 且无离职时返回 0.0，前端不再成片「—」；有离职而仍无分母为异常保持 None
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
        by_business = _departures_by_business_department(db, deps_p)

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

    rows_denominator_base = len([r for r in rows_all if _parse_loose_date(str(r.entry_date or ""))])
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
        "business_options": _dashboard_business_options(db),
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
    _apply_roster_salary_quote_ratio(data)
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
    raw_body = body if isinstance(body, dict) else {}
    data = _normalize_roster_payload(raw_body)
    for k in list(data.keys()):
        if k not in raw_body:
            data[k] = getattr(entry, k) or ""
    _validate_roster_business_fields(data)
    _apply_roster_salary_quote_ratio(data)
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
    header_info = _analyze_roster_csv_headers(text)
    existing_rows = db.query(RosterEntry).order_by(RosterEntry.id).all()
    backup_file = _write_roster_backup_csv_all(existing_rows) if existing_rows else ""
    active_cleared = (
        db.query(RosterEntry)
        .filter(_sql_roster_employment_active_pool())
        .delete(synchronize_session=False)
    )
    db.commit()
    cleared_existing = int(active_cleared or 0)

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
                skipped_details.append({
                    "serial_no": _skip_serial_hint(merged, row_index),
                    "reason": "联系方式重复（文件内去重）",
                    "contact_info": merged.get("contact_info", ""),
                })
                continue
            seen_contact_keys.add(ck)
        mc, normalized_cn = _resolve_roster_customer_client(db, merged.get("customer_name", ""))
        if mc:
            merged["customer_name"] = normalized_cn
        mapped_client_id = mc.id if mc else 0
        _apply_roster_salary_quote_ratio(merged)
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
                f"整体花名册 CSV 导入前全量备份 {len(existing_rows)} 行到 {backup_file or '无备份'}，"
                f"清空在职池 {cleared_existing} 行（已离职档案未删），导入新增 {imported} 行"
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
        "matched_headers_count": len(header_info["matched_headers"]),
        "unmatched_headers": header_info["unmatched_headers"],
    }


@app.post("/api/roster/turnover/import")
async def roster_turnover_import_csv(
    file: UploadFile = File(...),
    confirm: str = Form(""),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    """仅替换「离职档案池」：不删在职花名册；导入行会强制标记为离职。"""

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
    header_info = _analyze_roster_csv_headers(text)
    left_rows = _roster_entries_turnover_pool(db)
    backup_file = _write_roster_backup_turnover_csv_all(left_rows) if left_rows else ""
    left_cleared = db.query(RosterEntry).filter(_sql_roster_employment_left()).delete(synchronize_session=False)
    db.commit()
    cleared_existing = int(left_cleared or 0)

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
                skipped_details.append({
                    "serial_no": _skip_serial_hint(merged, row_index),
                    "reason": "联系方式重复（文件内去重）",
                    "contact_info": merged.get("contact_info", ""),
                })
                continue
            seen_contact_keys.add(ck)
        _ensure_merged_turnover_employment(merged)
        mc, normalized_cn = _resolve_roster_customer_client(db, merged.get("customer_name", ""))
        if mc:
            merged["customer_name"] = normalized_cn
        mapped_client_id = mc.id if mc else 0
        _apply_roster_salary_quote_ratio(merged)
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
                f"离职档案 CSV 导入前备份 {len(left_rows)} 行到 {backup_file or '无备份'}，"
                f"清空离职池 {cleared_existing} 行，导入新增 {imported} 行"
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
        "matched_headers_count": len(header_info["matched_headers"]),
        "unmatched_headers": header_info["unmatched_headers"],
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
    header_info = _analyze_roster_csv_headers(text)
    existing_rows = db.query(RosterEntry).filter(RosterEntry.client_id == client_id).order_by(RosterEntry.id).all()
    backup_file = _write_roster_backup_csv(c, existing_rows) if existing_rows else ""
    active_cleared = (
        db.query(RosterEntry)
        .filter(RosterEntry.client_id == client_id, _sql_roster_employment_active_pool())
        .delete(synchronize_session=False)
    )
    db.commit()
    cleared_existing = int(active_cleared or 0)

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
                skipped_details.append({
                    "serial_no": _skip_serial_hint(merged, row_index),
                    "reason": "联系方式重复（文件内去重）",
                    "contact_info": merged.get("contact_info", ""),
                })
                continue
            seen_contact_keys.add(ck)
        _apply_roster_salary_quote_ratio(merged)
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
            f"花名册 CSV 导入前全量备份 {len(existing_rows)} 行到 {backup_file or '无备份'}，"
            f"清空在职池 {cleared_existing} 行（该客户已离职档案未删），导入新增 {imported} 行"
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
        "matched_headers_count": len(header_info["matched_headers"]),
        "unmatched_headers": header_info["unmatched_headers"],
    }


@app.get("/api/roster/turnover/export")
async def roster_turnover_export_csv_all(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    rows = _roster_entries_turnover_pool(db)
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
        chinese_filename=f"离职率分析_离职档案_{ts}.csv",
        ascii_base=f"roster_turnover_{ts}",
    )
    return response


@app.get("/api/roster/export")
async def roster_export_csv_all(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    rows = _roster_entries_union_of_all_clients(db)
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
    rows = (
        db.query(RosterEntry)
        .filter(RosterEntry.client_id == client_id, _sql_roster_employment_active_pool())
        .order_by(RosterEntry.id)
        .all()
    )
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
        _apply_roster_salary_quote_ratio(merged)
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
        _apply_roster_salary_quote_ratio(merged)
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


@app.post("/api/roster/turnover/restore/latest")
async def roster_turnover_restore_latest_backup_all(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    latest = _pick_latest_backup("roster_backup_turnover_all__")
    if not latest:
        raise HTTPException(status_code=404, detail="未找到离职档案备份文件")
    backup_path = os.path.join(BACKUP_DIR, latest)
    with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    text = _strip_excel_sep_directive(text)
    left_before = _roster_entries_turnover_pool(db)
    cleared_existing = len(left_before)
    if cleared_existing:
        db.query(RosterEntry).filter(_sql_roster_employment_left()).delete(synchronize_session=False)
        db.commit()
    restored_rows = 0
    for mapped in _iter_roster_csv_data_rows(text):
        merged = _normalize_roster_payload(mapped)
        if not any(merged.values()):
            continue
        _ensure_merged_turnover_employment(merged)
        mc, normalized_cn = _resolve_roster_customer_client(db, merged.get("customer_name", ""))
        if mc:
            merged["customer_name"] = normalized_cn
        mapped_client_id = mc.id if mc else 0
        _apply_roster_salary_quote_ratio(merged)
        db.add(RosterEntry(client_id=mapped_client_id, **merged))
        restored_rows += 1
    _resequence_roster_serial_no_all_clients(db)
    db.commit()
    db.add(
        AuditLog(
            client_id=0,
            operator=user,
            action=f"离职档案从备份恢复：{latest}，清空离职池 {cleared_existing} 行，恢复 {restored_rows} 行",
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


def _period_week_bounds(period: str, year: Optional[int] = None) -> Optional[tuple]:
    """按与 _week_label_from_date 一致的口径，返回周期对应的周一/周日日期。"""
    s = _normalize_period_label(period)
    m = re.match(r"^\s*(\d{1,2})\s*w\s*(\d{1,2})\s*$", s, re.IGNORECASE)
    if not m:
        return None
    target_month = int(m.group(1))
    week_no = int(m.group(2))
    target_year = int(year or datetime.now().year)
    try:
        first_day = datetime(target_year, target_month, 1).date()
    except Exception:
        return None
    cursor = first_day - timedelta(days=first_day.weekday())
    while int((cursor + timedelta(days=3)).month) != target_month:
        cursor += timedelta(days=7)
    monday_start = cursor + timedelta(days=(week_no - 1) * 7)
    sunday_end = monday_start + timedelta(days=6)
    return (monday_start, sunday_end)


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
    detail_metric_keys = [
        "待面试",
        "已面试",
        "面试通过",
        "本周offer人数",
        "offer在谈",
        "弃offer/谈薪失败",
        "在途人数/待入职",
        "月度在途流失(包含前序)",
        "本周入职人数",
    ]

    def empty_detail_map() -> Dict[str, List[str]]:
        return {k: [] for k in detail_metric_keys}

    def append_detail(detail_map: Dict[str, List[str]], metric_key: str, full_name: str, position: str) -> None:
        name = str(full_name or "").strip()
        pos = str(position or "").strip()
        if not name:
            return
        detail_map.setdefault(metric_key, []).append(f"{name}｜{pos or '-'}")

    def _detail_date_text(raw_value: str, parsed_date: Optional[Any]) -> str:
        if parsed_date:
            return parsed_date.strftime("%Y/%m/%d")
        return str(raw_value or "").strip() or "-"

    def _is_previous_month_interview(interview_parsed: Optional[Any], onboarding_parsed: Optional[Any]) -> bool:
        if not interview_parsed or not onboarding_parsed:
            return False
        previous_month = 12 if int(onboarding_parsed.month) == 1 else int(onboarding_parsed.month) - 1
        return int(interview_parsed.month) == previous_month

    def _detail_name_with_period_mark(full_name: str, interview_parsed: Optional[Any], onboarding_parsed: Optional[Any]) -> str:
        name = str(full_name or "").strip() or "-"
        if _is_previous_month_interview(interview_parsed, onboarding_parsed):
            return f"{name}(上月)"
        return name

    def detail_with_onboarding(
        full_name: str,
        position: str,
        interview_parsed: Optional[Any],
        onboarding_raw: str,
        onboarding_parsed: Optional[Any],
    ) -> str:
        name = _detail_name_with_period_mark(full_name, interview_parsed, onboarding_parsed)
        pos = str(position or "").strip() or "-"
        return f"{name}｜{pos}｜{_detail_date_text(onboarding_raw, onboarding_parsed)}"

    def detail_with_cross_month_mark(full_name: str, position: str, interview_parsed: Optional[Any], onboarding_parsed: Optional[Any]) -> str:
        name = _detail_name_with_period_mark(full_name, interview_parsed, onboarding_parsed)
        pos = str(position or "").strip() or "-"
        return f"{name}｜{pos}"

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
    weekly_onboard_details: Dict[tuple, List[str]] = {}
    weekly_in_transit_details: Dict[tuple, List[str]] = {}
    weekly_in_transit_loss_details: Dict[tuple, List[str]] = {}
    anomalies: List[Dict[str, str]] = []

    def ensure_group(group_key: tuple) -> Dict[str, Any]:
        group_period, group_position, group_region = group_key
        if group_key not in grouped:
            grouped[group_key] = {
                "时间": group_period,
                "岗位": group_position,
                "需求数量": "",
                "地点": group_region,
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
                "offer在谈": 0,
                "弃offer/谈薪失败": 0,
                "在途人数/待入职": 0,
                "月度在途流失(包含前序)": 0,
                "本周入职人数": 0,
                "本月入职人数": 0,
                "_metric_details": empty_detail_map(),
            }
            inner_fail_counts[group_key] = 0
        return grouped[group_key]

    for e in rows:
        period = _normalize_period_label(str(e.date or "").strip())
        position = str(e.position or "").strip()
        region = str(e.region or "").strip()
        if not period or not position:
            continue
        key = (period, position, region)
        item = ensure_group(key)
        item["推送简历量"] += 1
        detail_map = item["_metric_details"]
        resume_screening = str(e.resume_screening or "").strip()
        interviewed = str(e.interviewed or "").strip()
        interview_time = str(e.interview_time or "").strip()
        result = str(e.result or "").strip()
        got_offer = str(e.got_offer or "").strip()
        onboarded = str(e.onboarded or "").strip()
        interview_date = _parse_loose_date(interview_time)
        interview_period = _week_label_from_date(interview_date) if interview_date else ""
        onboarding_time = str(e.onboarding_time or "").strip()
        onboarding_date = _parse_loose_date(onboarding_time)
        period_bounds = _period_week_bounds(period)
        period_end = period_bounds[1] if period_bounds else None

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
        if interviewed == "约面" and (
            not interview_time or (interview_date and period_end and interview_date > period_end)
        ):
            item["待面试"] += 1
            append_detail(detail_map, "待面试", e.full_name, position)
        if interviewed == "是" and interview_date:
            interviewed_item = ensure_group((interview_period or period, position, region))
            interviewed_item["已面试"] += 1
            append_detail(interviewed_item["_metric_details"], "已面试", e.full_name, position)
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
            result_item = ensure_group((interview_period or period, position, region))
            result_item["面试通过"] += 1
            append_detail(result_item["_metric_details"], "面试通过", e.full_name, position)
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
        if got_offer == "是" and result == "通过":
            offer_item = ensure_group((interview_period or period, position, region))
            offer_item["本周offer人数"] += 1
            offer_item["_metric_details"].setdefault("本周offer人数", []).append(
                detail_with_cross_month_mark(e.full_name, position, interview_date, onboarding_date)
            )
        if result == "通过" and not got_offer:
            negotiating_item = ensure_group((interview_period or period, position, region))
            negotiating_item["offer在谈"] += 1
            append_detail(negotiating_item["_metric_details"], "offer在谈", e.full_name, position)
        if got_offer == "否" and result == "通过":
            offer_reject_item = ensure_group((interview_period or period, position, region))
            offer_reject_item["弃offer/谈薪失败"] += 1
            append_detail(offer_reject_item["_metric_details"], "弃offer/谈薪失败", e.full_name, position)
        if got_offer == "是" and onboarded == "放弃入职":
            if onboarding_date:
                loss_week = _week_label_from_date(onboarding_date)
                loss_key = (loss_week, position, region)
                weekly_in_transit_loss_counts[loss_key] = int(weekly_in_transit_loss_counts.get(loss_key, 0)) + 1
                weekly_in_transit_loss_details.setdefault(loss_key, []).append(
                    detail_with_onboarding(e.full_name, position, interview_date, onboarding_time, onboarding_date)
                )
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
            weekly_in_transit_details.setdefault(waiting_key, []).append(
                detail_with_onboarding(e.full_name, position, interview_date, onboarding_time, onboarding_date)
            )
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
            weekly_onboard_details.setdefault(onboard_key, []).append(
                detail_with_onboarding(e.full_name, position, interview_date, onboarding_time, onboarding_date)
            )
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
        ensure_group(synthetic_key)

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
        item["_metric_details"]["本周入职人数"] = list(weekly_onboard_details.get(onboard_key, []))
        item["_metric_details"]["在途人数/待入职"] = list(weekly_in_transit_details.get(onboard_key, []))
        item["_metric_details"]["月度在途流失(包含前序)"] = list(weekly_in_transit_loss_details.get(onboard_key, []))
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
    _validate_pipeline_payload(data, context="管道数据新增")
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
    _validate_pipeline_payload(data, context="管道数据修改")
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
        mapped = _normalize_pipeline_payload(mapped)
        if not any(mapped.get(k, "") for k in matched_non_serial):
            skipped_empty_rows += 1
            if len(skipped_empty_row_numbers) < 20:
                skipped_empty_row_numbers.append(csv_line_no)
            continue
        _validate_pipeline_payload(mapped, context="管道数据CSV导入", row_hint=f"第{csv_line_no}行")

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
    _validate_interview_business_fields(data)
    _assert_interview_delivery_judgment_unique(db, client_id, data.get("full_name", ""), data.get("delivery_judgment", ""))
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
    _validate_interview_business_fields(data)
    _assert_interview_delivery_judgment_unique(
        db,
        entry.client_id,
        data.get("full_name", ""),
        data.get("delivery_judgment", ""),
        exclude_row_id=row_id,
    )
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
