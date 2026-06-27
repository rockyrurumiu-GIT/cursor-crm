# 同步服务器 DB 到本地测试环境

将生产/服务器上的 SQLite 数据库与 RMS 简历附件同步到本地，用于复现线上数据、调试或验收。与 [`docs/ops-production.md`](ops-production.md) 中的「本地 → 服务器」代码部署方向相反。

## 适用场景

- 本地需要与线上一致的业务数据（客户、岗位、推荐、Offer 等）
- 排查仅在线上出现的 RMS / 看板 / 权限问题
- 在真实数据量下做本地功能验证

## 前置条件

- 本机已 clone 项目，且存在 `venv/` 与 `crm_v8.db`（或首次同步后会生成）
- 可通过 SSH / SCP / rsync 访问服务器（与生产部署相同账号，见 [`docs/ops-production.md`](ops-production.md)）
- 服务器已安装 `sqlite3` CLI（生产备份脚本同样依赖）

## 路径与变量

下文命令默认：

| 项 | 本地 | 服务器 |
|----|------|--------|
| 项目根目录 | `/Users/rocky/Documents/cursor-crm` | `/home/rocky/BMS` |
| 数据库 | `crm_v8.db` | `/home/rocky/BMS/crm_v8.db` |
| RMS 附件 | `uploads/rms/` | `/home/rocky/BMS/uploads/rms/` |

将 `<server>` 替换为实际 SSH 主机（与 `rsync` 部署时相同，例如 `rocky@your-host`）。

---

## 操作步骤

### 1. 停掉本地 BMS / uvicorn

同步前必须停止本地应用，避免覆盖数据库时仍有进程读写 `crm_v8.db`。

```bash
# 若本地有 uvicorn 在跑，先停掉（Ctrl+C 或结束对应终端进程）
# 服务器端，用 sudo systemctl stop bms 停止服务，避免数据库写入
```

### 2. 备份本地库

覆盖前保留一份带时间戳的本地备份，便于回滚。

```bash
cd /Users/rocky/Documents/cursor-crm

cp crm_v8.db "crm_v8.local-backup.$(date +%Y%m%d-%H%M%S).db"
```

备份文件命名示例：`crm_v8.local-backup.20260627-113153.db`。请勿将此类本地备份提交到 Git。

### 3. 在服务器上生成一致性备份

使用 SQLite 的 `.backup` 命令做在线热备，避免直接 `scp` 正在写入的库文件导致损坏。

```bash
ssh rocky@<server> 'sqlite3 /home/rocky/BMS/crm_v8.db ".backup /tmp/crm_v8.server-sync.db"'
```

### 4. 拉到本地

```bash
scp rocky@<server>:/tmp/crm_v8.server-sync.db /tmp/crm_v8.server-sync.db
```

### 5. 覆盖本地库

```bash
cp /tmp/crm_v8.server-sync.db /Users/rocky/Documents/cursor-crm/crm_v8.db
```

### 6. 同步 RMS 简历文件

数据库中的简历路径指向 `uploads/rms/` 下的文件；仅同步 DB 而不拉附件会导致简历预览/下载失败。

```bash
rsync -av rocky@<server>:/home/rocky/BMS/uploads/rms/ /Users/rocky/Documents/cursor-crm/uploads/rms/
```

### 7. 启动本地应用并补齐 schema

本地代码版本若比服务器新，启动后需执行迁移，使 schema 与当前代码一致。

**方式 A — 先迁移再启动（推荐）：**

```bash
cd /Users/rocky/Documents/cursor-crm
CRM_DB_URL=sqlite:///./crm_v8.db ./venv/bin/python scripts/run_migrations.py
CRM_DB_URL=sqlite:///./crm_v8.db ./venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

**方式 B — 直接启动：**

应用启动流程也会触发迁移逻辑；若本地分支与服务器差异较大，仍建议先显式跑 `run_migrations.py`。

```bash
cd /Users/rocky/Documents/cursor-crm
CRM_DB_URL=sqlite:///./crm_v8.db ./venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

浏览器访问：<http://127.0.0.1:8001>

---

## 一键脚本（可选）

将 `<server>` 换成实际主机后，可整段复制执行（仍须先确认本地 uvicorn 已停止）：

```bash
set -e
cd /Users/rocky/Documents/cursor-crm
SERVER="rocky@<server>"

cp crm_v8.db "crm_v8.local-backup.$(date +%Y%m%d-%H%M%S).db"
ssh "$SERVER" 'sqlite3 /home/rocky/BMS/crm_v8.db ".backup /tmp/crm_v8.server-sync.db"'
scp "$SERVER:/tmp/crm_v8.server-sync.db" /tmp/crm_v8.server-sync.db
cp /tmp/crm_v8.server-sync.db ./crm_v8.db
rsync -av "$SERVER:/home/rocky/BMS/uploads/rms/" ./uploads/rms/
CRM_DB_URL=sqlite:///./crm_v8.db ./venv/bin/python scripts/run_migrations.py
echo "同步完成。启动: CRM_DB_URL=sqlite:///./crm_v8.db ./venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001"
```

---

## 注意事项

- **只读测试**：同步的是生产数据副本，本地请勿对敏感客户数据做对外分享或误操作写回服务器。
- **勿反向覆盖**：不要用本地 `crm_v8.db` rsync 到服务器；生产数据更新见 [`docs/ops-production.md`](ops-production.md) 部署流程。
- **凭据文件**：`.crm_admin_credentials.json` 等本地凭据不会随 DB 同步；登录账号以同步后的 `sys_users` 等表为准。
- **服务器临时文件**：`/tmp/crm_v8.server-sync.db` 可在确认本地拉取成功后于服务器上删除，避免占磁盘。

## 验收

同步完成后建议快速检查：

```bash
curl -sS http://127.0.0.1:8001/api/me   # 需先登录
# 或打开 RMS 看板 / 简历列表，确认数据与附件可正常访问
```
