import os
import time
import shutil
import json
import csv
import io
import socket
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File, status
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


engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

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
