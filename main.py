import os
import re
import time
import shutil
import json
import csv
import io
import socket
import unicodedata
from datetime import datetime
from typing import List, Optional, Any, Dict
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
DB_URL = "sqlite:///./crm_v8.db"
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
ADMIN_USER = {"username": "admin", "password": "admin123"}

for d in [STATIC_DIR, UPLOAD_DIR, TRASH_DIR]:
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


engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


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
    "中诺工号": "zntx_staff_no",
    "中河工号": "zntx_staff_no",  # 兼容旧误写
    "离职类型": "zntx_separation_type",
    "补偿金": "zntx_compensation_amount",
    "离职或释放原因": "leave_reason",
    "释放成功离职原因": "leave_reason",
    "备注": "remarks",
}


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
    "中诺工号",
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
    "补卡",
    "员工+2",
    "接口",
    "项目释放时间",
    "离职时间",
    "离职类型",
    "释放成功离职原因",
    "补偿金",
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


@app.put("/api/clients/{client_id}")
async def update_client(
    client_id: int,
    name: str = Form(...),
    phase: str = Form(...),
    remarks: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    updates = []
    if client.phase != phase:
        updates.append(f"阶段从[{client.phase}]变更为[{phase}]")
    if remarks and client.remarks != remarks:
        updates.append("更新了备注信息")

    client.name = name
    client.phase = phase
    if remarks:
        client.remarks = remarks

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
    response.headers["Content-Disposition"] = f"attachment; filename=clients_{int(time.time())}.csv"
    return response


@app.get("/api/clients/{client_id}/brief")
async def get_client_brief(client_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    return {"id": c.id, "name": c.name, "owner": c.owner or "", "phase": c.phase or ""}


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
    _assert_roster_contact_unique(db, client_id, data.get("contact_info", ""))
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
    _assert_roster_contact_unique(
        db,
        entry.client_id,
        data.get("contact_info", ""),
        exclude_row_id=row_id,
    )
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
    cid = entry.client_id
    db.delete(entry)
    db.commit()
    log = AuditLog(client_id=cid, operator=user, action=f"花名册删除行 id={row_id}")
    db.add(log)
    db.commit()
    return {"status": "deleted"}


@app.post("/api/clients/{client_id}/roster/import")
async def roster_import_csv(
    client_id: int,
    file: UploadFile = File(...),
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
    text = _strip_excel_sep_directive(_decode_roster_upload_bytes(raw))
    # 按用户要求：导入前先清空当前客户花名册，再重建导入。
    cleared_existing = db.query(RosterEntry).filter(RosterEntry.client_id == client_id).count()
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
            f"花名册 CSV 导入前清空 {cleared_existing} 行，导入新增 {imported} 行"
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
        "imported": imported,
        "skipped_duplicates": skipped_duplicates,
        "skipped_empty": skipped_empty,
        "skipped_total": skip_total,
        "skipped_details": skipped_details,
    }


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
    safe_name = "".join(ch for ch in c.name if ch.isalnum() or ch in (" ", "-", "_")).strip() or "roster"
    response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{safe_name}_花名册_{int(time.time())}.csv"'
    return response


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
