import os
import sqlite3
import json
import socket
import shutil
import datetime
from typing import List, Optional
# 修正点 1: 确保响应类名称正确 (HTMLResponse)
from fastapi import FastAPI, Request, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# --- 配置与初始化 ---
DB_PATH = "crm.db"
UPLOAD_DIR = "attachments"
RECYCLE_BIN = "deleted_files"
APP_ID = "ito-crm-v1"

for folder in [UPLOAD_DIR, RECYCLE_BIN]:
    if not os.path.exists(folder):
        os.makedirs(folder)

app = FastAPI(title="ITO CRM Ultimate")
# 虽保留 Jinja2 配置以防后续扩展，但主页将直接返回 HTML 避免语法冲突
templates = Jinja2Templates(directory=".") 

# --- 数据库操作逻辑 ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    # 客户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            scale TEXT, -- 外包规模 (如: 10人, 100万/年)
            stage TEXT, -- 阶段: 初步接触, 技术交流, 方案报价, 合同签订, 项目交付
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 拜访记录
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visit_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            visit_date TEXT,
            note TEXT,
            attachment TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        )
    ''')
    # 审计日志
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            action TEXT, -- 新建, 修改, 删除
            details TEXT, -- JSON 格式的变更详情
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 检查是否需要 Mock 数据
    cursor.execute("SELECT COUNT(*) FROM clients")
    if cursor.fetchone()[0] == 0:
        mock_clients = [
            ("阿里巴巴 (杭州)", "张总", "50人/年", "项目交付"),
            ("腾讯科技 (深圳)", "李经理", "120人/月", "合同签订"),
            ("字节跳动", "王工", "15人/季", "技术交流"),
            ("美团外卖", "赵办", "300万/年", "初步接触"),
            ("百度搜索", "刘总", "8人核心小组", "方案报价")
        ]
        for c in mock_clients:
            cursor.execute("INSERT INTO clients (name, contact, scale, stage) VALUES (?,?,?,?)", c)
            cid = cursor.lastrowid
            cursor.execute("INSERT INTO audit_logs (client_id, action, details) VALUES (?,?,?)", 
                           (cid, "系统初始化", "自动生成 Mock 数据"))
            cursor.execute("INSERT INTO visit_records (client_id, visit_date, note) VALUES (?,?,?)",
                           (cid, "2023-10-20", "首次业务对接，对方对人才外包模式感兴趣。"))
    
    conn.commit()
    conn.close()

def cleanup_recycle_bin():
    """清理超过30天的回收站文件"""
    now = datetime.datetime.now()
    count = 0
    if os.path.exists(RECYCLE_BIN):
        for f in os.listdir(RECYCLE_BIN):
            path = os.path.join(RECYCLE_BIN, f)
            ctime = datetime.datetime.fromtimestamp(os.path.getctime(path))
            if (now - ctime).days > 30:
                if os.path.isfile(path): os.remove(path)
                elif os.path.isdir(path): shutil.rmtree(path)
                count += 1
    if count > 0:
        print(f"[*] 已从回收站永久删除 {count} 个过期文件。")

# --- API 路由 ---

@app.on_event("startup")
async def startup():
    init_db()
    cleanup_recycle_bin()

# 核心修正：直接返回 HTMLContent 字符串。
# 这避免了 Jinja2 尝试解析 Vue.js 的 {{ }} 语法和 || 运算符导致的 500 错误。
@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=HTML_CONTENT)

@app.get("/api/clients")
async def list_clients(stage: Optional[str] = None):
    conn = get_db()
    if stage:
        rows = conn.execute("SELECT * FROM clients WHERE stage = ? ORDER BY id DESC", (stage,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM clients ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/clients")
async def create_client(name: str = Form(...), contact: str = Form(...), scale: str = Form(...), stage: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO clients (name, contact, scale, stage) VALUES (?,?,?,?)", (name, contact, scale, stage))
    new_id = cursor.lastrowid
    cursor.execute("INSERT INTO audit_logs (client_id, action, details) VALUES (?,?,?)", 
                   (new_id, "新建客户", f"创建了客户: {name}"))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/api/clients/{client_id}")
async def get_client_detail(client_id: int):
    conn = get_db()
    client = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    visits = conn.execute("SELECT * FROM visit_records WHERE client_id = ? ORDER BY visit_date DESC", (client_id,)).fetchall()
    logs = conn.execute("SELECT * FROM audit_logs WHERE client_id = ? ORDER BY created_at DESC", (client_id,)).fetchall()
    conn.close()
    if not client: raise HTTPException(status_code=404)
    return {
        "client": dict(client),
        "visits": [dict(v) for v in visits],
        "logs": [dict(l) for l in logs]
    }

@app.put("/api/clients/{client_id}")
async def update_client(client_id: int, request: Request):
    data = await request.json()
    conn = get_db()
    old = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if not old: return {"error": "not found"}
    
    changes = []
    for key in ['name', 'contact', 'scale', 'stage']:
        if data.get(key) != old[key]:
            changes.append(f"{key}: '{old[key]}' -> '{data.get(key)}'")
    
    if changes:
        conn.execute("UPDATE clients SET name=?, contact=?, scale=?, stage=? WHERE id=?",
                     (data['name'], data['contact'], data['scale'], data['stage'], client_id))
        conn.execute("INSERT INTO audit_logs (client_id, action, details) VALUES (?,?,?)",
                     (client_id, "修改信息", " | ".join(changes)))
        conn.commit()
    conn.close()
    return {"status": "ok"}

@app.delete("/api/clients/{client_id}")
async def delete_client(client_id: int):
    conn = get_db()
    # 处理附件：移动到回收站
    visits = conn.execute("SELECT attachment FROM visit_records WHERE client_id = ?", (client_id,)).fetchall()
    for v in visits:
        if v['attachment'] and os.path.exists(os.path.join(UPLOAD_DIR, v['attachment'])):
            shutil.move(os.path.join(UPLOAD_DIR, v['attachment']), os.path.join(RECYCLE_BIN, v['attachment']))
    
    conn.execute("DELETE FROM visit_records WHERE client_id = ?", (client_id,))
    conn.execute("DELETE FROM audit_logs WHERE client_id = ?", (client_id,))
    conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.post("/api/visits")
async def add_visit(client_id: int = Form(...), visit_date: str = Form(...), note: str = Form(...), file: UploadFile = File(None)):
    filename = None
    if file and file.filename:
        filename = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        with open(os.path.join(UPLOAD_DIR, filename), "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    
    conn = get_db()
    conn.execute("INSERT INTO visit_records (client_id, visit_date, note, attachment) VALUES (?,?,?,?)",
                 (client_id, visit_date, note, filename))
    conn.execute("INSERT INTO audit_logs (client_id, action, details) VALUES (?,?,?)",
                 (client_id, "添加拜访", f"日期: {visit_date}"))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/attachments/{filename}")
async def get_attachment(filename: str):
    path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path)
    return {"error": "file not found"}

# --- 前端代码 (Single File) ---
# 使用原始字符串 r""" 避免 Python 3.12 的转义警告
HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ITO CRM Ultimate - 外包业务专家</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        .funnel-layer:hover { filter: brightness(1.1); cursor: pointer; }
        .timeline-line::before { content: ''; position: absolute; left: 15px; top: 0; bottom: 0; width: 2px; background: #e5e7eb; }
        [v-cloak] { display: none; }
    </style>
</head>
<body class="bg-slate-50 min-h-screen font-sans text-slate-900">
    <div id="app" v-cloak class="flex h-screen overflow-hidden">
        <!-- 侧边栏 -->
        <aside class="w-64 bg-slate-900 text-white flex-shrink-0 flex flex-col">
            <div class="p-6 border-b border-slate-800">
                <h1 class="text-xl font-bold flex items-center gap-2">
                    <i data-lucide="layers" class="text-blue-400"></i> ITO CRM
                </h1>
                <p class="text-xs text-slate-400 mt-1 uppercase tracking-widest">Ultimate Edition</p>
            </div>
            <nav class="flex-1 p-4 space-y-2">
                <button @click="view = 'dashboard'" :class="navClass(view === 'dashboard')" class="w-full text-left px-4 py-2 rounded-lg transition">概览控制台</button>
                <button @click="view = 'clients'" :class="navClass(view === 'clients')" class="w-full text-left px-4 py-2 rounded-lg transition">客户</button>
            </nav>
            <div class="p-4 bg-slate-800 m-4 rounded-xl shadow-inner">
                <h3 class="text-xs font-bold text-slate-400 mb-2 flex items-center gap-1">
                    <i data-lucide="calculator" class="w-3"></i> 费用折算器
                </h3>
                <div class="space-y-2 text-sm">
                    <input v-model.number="calc.price" type="number" placeholder="月单价" class="w-full bg-slate-700 rounded px-2 py-1 border-none text-white">
                    <div class="flex gap-2">
                        <input v-model.number="calc.totalDays" type="number" placeholder="当月天数" class="w-1/2 bg-slate-700 rounded px-2 py-1 border-none text-white text-xs">
                        <input v-model.number="calc.activeDays" type="number" placeholder="实际天数" class="w-1/2 bg-slate-700 rounded px-2 py-1 border-none text-white text-xs">
                    </div>
                    <div class="pt-2 border-t border-slate-600 text-blue-300 font-mono text-center">
                        结果: {{ calculatedCost }} 元
                    </div>
                </div>
            </div>
        </aside>

        <!-- 主内容区 -->
        <main class="flex-1 overflow-y-auto relative p-8">
            <!-- Dashboard View -->
            <div v-if="view === 'dashboard'" class="max-w-6xl mx-auto">
                <div class="flex justify-between items-center mb-8">
                    <div>
                        <h2 class="text-3xl font-bold">外包商机漏斗</h2>
                        <p class="text-slate-500">点击漏斗层级筛选对应阶段的客户</p>
                    </div>
                    <button @click="openAddModal" class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-full shadow-lg flex items-center gap-2 transition">
                        <i data-lucide="plus"></i> 开拓新客户
                    </button>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center bg-white p-12 rounded-3xl shadow-sm border border-slate-100">
                    <!-- SVG Funnel -->
                    <div class="flex justify-center">
                        <svg width="400" height="450" viewBox="0 0 400 450">
                            <!-- 各阶段图形定义 -->
                            <g v-for="(s, idx) in stages" :key="s.name" class="funnel-layer" @click="filterByStage(s.name)">
                                <polygon :points="getFunnelPoints(idx)" :fill="s.color" class="transition-all duration-300 opacity-90 hover:opacity-100" />
                                <text x="200" :y="60 + idx*80" text-anchor="middle" fill="white" class="font-bold pointer-events-none">{{ s.name }} ({{ getCount(s.name) }})</text>
                            </g>
                        </svg>
                    </div>
                    <!-- Stats Card -->
                    <div class="space-y-6">
                        <div class="p-6 bg-slate-50 rounded-2xl border border-slate-100">
                            <h4 class="text-sm font-bold text-slate-400 mb-4">漏斗转化指标</h4>
                            <div class="space-y-4">
                                <div v-for="s in stages" :key="s.name" class="flex items-center gap-4">
                                    <div class="w-24 text-xs font-medium text-slate-600">{{ s.name }}</div>
                                    <div class="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden">
                                        <div class="h-full" :style="{ width: (getCount(s.name)/clients.length*100 || 0) + '%', backgroundColor: s.color }"></div>
                                    </div>
                                    <div class="w-8 text-xs text-right font-mono">{{ getCount(s.name) }}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Clients List View -->
            <div v-if="view === 'clients'" class="max-w-6xl mx-auto">
                <div class="flex items-center gap-4 mb-8">
                    <button @click="filteredStage = null" class="text-sm px-4 py-1 rounded-full border transition" :class="!filteredStage ? 'bg-slate-900 text-white' : 'hover:bg-slate-100'">全部</button>
                    <button v-for="s in stages" @click="filteredStage = s.name" class="text-sm px-4 py-1 rounded-full border transition" :class="filteredStage === s.name ? 'bg-slate-900 text-white' : 'hover:bg-slate-100'">{{ s.name }}</button>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    <div v-for="c in filteredClients" :key="c.id" @click="showDetail(c.id)" class="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 hover:shadow-xl hover:-translate-y-1 transition cursor-pointer">
                        <div class="flex justify-between items-start mb-4">
                            <span class="text-xs px-2 py-1 rounded font-bold" :style="{ backgroundColor: getStageColor(c.stage) + '22', color: getStageColor(c.stage) }">{{ c.stage }}</span>
                            <i data-lucide="external-link" class="w-4 h-4 text-slate-300"></i>
                        </div>
                        <h3 class="text-lg font-bold mb-1">{{ c.name }}</h3>
                        <p class="text-slate-500 text-sm mb-4 flex items-center gap-1"><i data-lucide="users" class="w-3"></i> {{ c.scale || '未备注规模' }}</p>
                        <div class="flex justify-between items-center pt-4 border-t border-slate-50">
                            <span class="text-xs text-slate-400">{{ c.contact }}</span>
                            <button @click.stop="confirmDelete(c)" class="text-red-400 hover:text-red-600 transition"><i data-lucide="trash-2" class="w-4"></i></button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Detail Drawer -->
            <div v-if="detailClient" class="fixed inset-0 bg-black/50 z-40 flex justify-end">
                <div class="w-full max-w-2xl bg-white h-full shadow-2xl overflow-y-auto p-8 animate-slide-left">
                    <div class="flex justify-between items-center mb-8">
                        <h2 class="text-2xl font-bold">客户详情</h2>
                        <button @click="detailClient = null" class="p-2 hover:bg-slate-100 rounded-full"><i data-lucide="x"></i></button>
                    </div>

                    <div class="space-y-8">
                        <!-- Basic Info Form -->
                        <div class="bg-slate-50 p-6 rounded-2xl grid grid-cols-2 gap-4">
                            <div class="col-span-2">
                                <label class="text-xs font-bold text-slate-400 uppercase">客户名称</label>
                                <input v-model="detailClient.client.name" class="w-full bg-transparent border-b border-slate-200 py-1 font-bold text-lg focus:outline-none">
                            </div>
                            <div>
                                <label class="text-xs font-bold text-slate-400 uppercase">联系人</label>
                                <input v-model="detailClient.client.contact" class="w-full bg-transparent border-b border-slate-200 py-1 focus:outline-none">
                            </div>
                            <div>
                                <label class="text-xs font-bold text-slate-400 uppercase">外包规模</label>
                                <input v-model="detailClient.client.scale" class="w-full bg-transparent border-b border-slate-200 py-1 focus:outline-none">
                            </div>
                            <div class="col-span-2">
                                <label class="text-xs font-bold text-slate-400 uppercase">当前阶段</label>
                                <select v-model="detailClient.client.stage" class="w-full bg-transparent border-b border-slate-200 py-1 focus:outline-none">
                                    <option v-for="s in stages" :value="s.name">{{ s.name }}</option>
                                </select>
                            </div>
                            <div class="col-span-2 text-right">
                                <button @click="saveClientUpdate" class="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm">保存基本信息</button>
                            </div>
                        </div>

                        <!-- Visit History -->
                        <div>
                            <div class="flex justify-between items-center mb-4">
                                <h3 class="font-bold flex items-center gap-2"><i data-lucide="message-square"></i> 拜访记录</h3>
                                <button @click="showVisitForm = !showVisitForm" class="text-blue-600 text-sm font-bold">+ 添加记录</button>
                            </div>
                            
                            <!-- Add Visit Form -->
                            <div v-if="showVisitForm" class="mb-6 p-4 border-2 border-dashed border-slate-200 rounded-xl space-y-3">
                                <input type="date" v-model="newVisit.date" class="w-full border p-2 rounded">
                                <textarea v-model="newVisit.note" placeholder="沟通要点..." class="w-full border p-2 rounded h-20"></textarea>
                                <input type="file" @change="handleFileChange" class="text-sm">
                                <button @click="submitVisit" class="w-full bg-blue-600 text-white py-2 rounded font-bold">提交记录</button>
                            </div>

                            <div class="space-y-4">
                                <div v-for="v in detailClient.visits" :key="v.id" class="p-4 border border-slate-100 rounded-xl bg-white">
                                    <div class="flex justify-between text-xs text-slate-400 mb-2">
                                        <span>{{ v.visit_date }}</span>
                                    </div>
                                    <p class="text-sm text-slate-700 mb-3">{{ v.note }}</p>
                                    <div v-if="v.attachment" class="flex items-center gap-2">
                                        <div v-if="isImage(v.attachment)" class="relative group">
                                            <img :src="'/attachments/'+v.attachment" class="w-[60px] h-[60px] object-cover rounded shadow-sm border border-slate-200">
                                            <a :href="'/attachments/'+v.attachment" target="_blank" class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center rounded text-white text-[10px]">查看大图</a>
                                        </div>
                                        <a v-else :href="'/attachments/'+v.attachment" target="_blank" class="text-xs bg-slate-100 px-2 py-1 rounded flex items-center gap-1">
                                            <i data-lucide="file-text" class="w-3"></i> 附件下载
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Audit Logs Timeline -->
                        <div class="pt-8 border-t border-slate-100">
                            <h3 class="font-bold flex items-center gap-2 mb-6"><i data-lucide="history"></i> 数据审计日志</h3>
                            <div class="relative timeline-line ml-4 space-y-6">
                                <div v-for="log in detailClient.logs" :key="log.id" class="relative pl-8">
                                    <div class="absolute left-[-2px] top-1.5 w-3 h-3 rounded-full bg-slate-400 border-2 border-white shadow-sm"></div>
                                    <div class="text-xs text-slate-400 font-mono">{{ log.created_at }}</div>
                                    <div class="text-sm font-bold text-slate-700">{{ log.action }}</div>
                                    <div class="text-xs text-slate-500 mt-1 italic">{{ log.details }}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Modal: Add Client -->
            <div v-if="showAddModal" class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
                <div class="bg-white rounded-3xl w-full max-w-md p-8 shadow-2xl">
                    <h2 class="text-2xl font-bold mb-6">建立新连接</h2>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-xs font-bold text-slate-400 mb-1">客户/企业全称</label>
                            <input v-model="newClient.name" class="w-full border rounded-xl px-4 py-2 focus:ring-2 ring-blue-500 outline-none">
                        </div>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-xs font-bold text-slate-400 mb-1">联系人</label>
                                <input v-model="newClient.contact" class="w-full border rounded-xl px-4 py-2 focus:ring-2 ring-blue-500 outline-none">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-400 mb-1">阶段</label>
                                <select v-model="newClient.stage" class="w-full border rounded-xl px-4 py-2 focus:ring-2 ring-blue-500 outline-none bg-white">
                                    <option v-for="s in stages" :value="s.name">{{ s.name }}</option>
                                </select>
                            </div>
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-400 mb-1">预估规模 (人数/金额)</label>
                            <input v-model="newClient.scale" placeholder="例如: 50人技术外包" class="w-full border rounded-xl px-4 py-2 focus:ring-2 ring-blue-500 outline-none">
                        </div>
                        <div class="flex gap-4 pt-4">
                            <button @click="showAddModal = false" class="flex-1 py-3 font-bold text-slate-500">取消</button>
                            <button @click="submitNewClient" class="flex-1 bg-blue-600 text-white py-3 rounded-xl font-bold shadow-lg shadow-blue-200">录入系统</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Modal: Confirm Delete -->
            <div v-if="deleteConfirm" class="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4">
                <div class="bg-white rounded-2xl w-full max-w-sm p-6 text-center shadow-2xl">
                    <div class="w-16 h-16 bg-red-100 text-red-500 rounded-full flex items-center justify-center mx-auto mb-4">
                        <i data-lucide="alert-triangle" class="w-8 h-8"></i>
                    </div>
                    <h3 class="text-xl font-bold mb-2">确认删除该客户？</h3>
                    <p class="text-slate-500 text-sm mb-6">此操作将移除 {{ deleteConfirm.name }} 的所有拜访记录和附件。附件将在回收站保留30天。</p>
                    <div class="flex gap-3">
                        <button @click="deleteConfirm = null" class="flex-1 py-2 bg-slate-100 rounded-lg font-bold">返回</button>
                        <button @click="doDelete" class="flex-1 py-2 bg-red-500 text-white rounded-lg font-bold">确定删除</button>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <script>
        const { createApp, ref, computed, onMounted, nextTick } = Vue;

        createApp({
            setup() {
                const view = ref('dashboard');
                const clients = ref([]);
                const filteredStage = ref(null);
                const detailClient = ref(null);
                const showAddModal = ref(false);
                const deleteConfirm = ref(null);
                const showVisitForm = ref(false);

                const calc = ref({ price: 25000, totalDays: 22, activeDays: 22 });
                const newClient = ref({ name: '', contact: '', scale: '', stage: '初步接触' });
                const newVisit = ref({ date: new Date().toISOString().split('T')[0], note: '', file: null });

                const stages = [
                    { name: '初步接触', color: '#94a3b8' }, // Slate 400
                    { name: '技术交流', color: '#60a5fa' }, // Blue 400
                    { name: '方案报价', color: '#818cf8' }, // Indigo 400
                    { name: '合同签订', color: '#a78bfa' }, // Violet 400
                    { name: '项目交付', color: '#22c55e' }  // Green 500
                ];

                const calculatedCost = computed(() => {
                    if (!calc.value.totalDays || !calc.value.price) return 0;
                    return Math.round((calc.value.price / calc.value.totalDays) * calc.value.activeDays);
                });

                const filteredClients = computed(() => {
                    if (!filteredStage.value) return clients.value;
                    return clients.value.filter(c => c.stage === filteredStage.value);
                });

                const refreshData = async () => {
                    const res = await fetch('/api/clients');
                    clients.value = await res.json();
                    nextTick(() => lucide.createIcons());
                };

                const filterByStage = (stageName) => {
                    filteredStage.value = stageName;
                    view.value = 'clients';
                };

                const getCount = (stage) => clients.value.filter(c => c.stage === stage).length;

                const getFunnelPoints = (idx) => {
                    const startWidth = 360 - (idx * 60);
                    const endWidth = 360 - ((idx + 1) * 60);
                    const startX = 200 - startWidth / 2;
                    const endX = 200 - endWidth / 2;
                    const startY = 20 + idx * 80;
                    const endY = 100 + idx * 80;
                    return `${startX},${startY} ${startX + startWidth},${startY} ${endX + endWidth},${endY} ${endX},${endY}`;
                };

                const showDetail = async (id) => {
                    const res = await fetch(`/api/clients/${id}`);
                    detailClient.value = await res.json();
                    nextTick(() => lucide.createIcons());
                };

                const openAddModal = () => {
                    newClient.value = { name: '', contact: '', scale: '', stage: '初步接触' };
                    showAddModal.value = true;
                };

                const submitNewClient = async () => {
                    const formData = new FormData();
                    Object.keys(newClient.value).forEach(k => formData.append(k, newClient.value[k]));
                    await fetch('/api/clients', { method: 'POST', body: formData });
                    showAddModal.value = false;
                    refreshData();
                };

                const saveClientUpdate = async () => {
                    await fetch(`/api/clients/${detailClient.value.client.id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(detailClient.value.client)
                    });
                    showDetail(detailClient.value.client.id);
                    refreshData();
                };

                const confirmDelete = (client) => { deleteConfirm.value = client; };
                const doDelete = async () => {
                    await fetch(`/api/clients/${deleteConfirm.value.id}`, { method: 'DELETE' });
                    deleteConfirm.value = null;
                    refreshData();
                };

                const handleFileChange = (e) => { newVisit.value.file = e.target.files[0]; };
                const submitVisit = async () => {
                    const formData = new FormData();
                    formData.append('client_id', detailClient.value.client.id);
                    formData.append('visit_date', newVisit.value.date);
                    formData.append('note', newVisit.value.note);
                    if (newVisit.value.file) formData.append('file', newVisit.value.file);
                    
                    await fetch('/api/visits', { method: 'POST', body: formData });
                    newVisit.value = { date: new Date().toISOString().split('T')[0], note: '', file: null };
                    showVisitForm.value = false;
                    showDetail(detailClient.value.client.id);
                };

                const isImage = (filename) => {
                    return /\.(jpg|jpeg|png|webp|gif)$/i.test(filename);
                };

                const getStageColor = (name) => {
                    return stages.find(s => s.name === name)?.color || '#94a3b8';
                };

                const navClass = (active) => active ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800';

                onMounted(() => {
                    refreshData();
                    lucide.createIcons();
                });

                return {
                    view, clients, filteredStage, detailClient, showAddModal, deleteConfirm, showVisitForm,
                    calc, newClient, newVisit, stages, calculatedCost, filteredClients,
                    filterByStage, getCount, getFunnelPoints, showDetail, openAddModal,
                    submitNewClient, saveClientUpdate, confirmDelete, doDelete, handleFileChange, submitVisit,
                    isImage, getStageColor, navClass
                };
            }
        }).mount('#app');
    </script>
</body>
</html>
"""

# 在当前目录下保存 index.html 供参考（虽然路由中已改为直接返回字符串）
with open("index.html", "w", encoding="utf-8") as f:
    f.write(HTML_CONTENT)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

if __name__ == "__main__":
    local_ip = get_local_ip()
    print("="*50)
    print("  ITO CRM Ultimate 启动成功")
    print(f"  内网访问地址: http://{local_ip}:8000")
    print("  管理账号: 无 (内部单机模式)")
    print("="*50)
    uvicorn.run(app, host="0.0.0.0", port=8000)