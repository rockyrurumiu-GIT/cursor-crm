# BMS 生产运维手册（Phase 8）

轻量生产部署：systemd + Nginx HTTPS + 环境变量密钥 + 自动备份。不含 Docker、CI/CD、certbot。

## 架构

```
浏览器 → HTTPS :443 (Nginx bms.throme.com.cn) → 127.0.0.1:8001 (uvicorn) → SQLite + uploads/
```

公网仅开放 **22 / 80 / 443**；**8001 只监听本机**。

**禁止** 在生产环境使用 `python main.py`（会绑定 `0.0.0.0:8001`）。应使用 systemd 启动 uvicorn。

---

## 一次性服务器安装

### Step 0 — 系统依赖

```bash
sudo yum install -y sqlite
# 或：sudo dnf install -y sqlite
```

`bms_backup.sh` 的 SQLite `.backup` 命令依赖 `sqlite3` CLI。

### Step 1 — 目录与 Python 3.11 venv

阿里云默认 `python3` 为 3.6.8，**不得**使用 `python3 -m venv`。

```bash
mkdir -p /home/rocky/BMS /home/rocky/bms_backups
sudo mkdir -p /etc/bms
```

本地同步代码（见下方 rsync），然后：

```bash
# 若无 python3.11，先安装（按实际 OS 调整）
# sudo yum install -y python3.11 python3.11-pip

python3.11 -m venv /home/rocky/BMS/venv
/home/rocky/BMS/venv/bin/python --version   # 必须是 3.11.x
/home/rocky/BMS/venv/bin/pip install -r /home/rocky/BMS/requirements.txt
```

### Step 2 — 环境变量与密钥

```bash
sudo cp /home/rocky/BMS/deploy/bms.env.example /etc/bms/bms.env
sudo nano /etc/bms/bms.env
```

必填：

```bash
CRM_DB_URL=sqlite:////home/rocky/BMS/crm_v8.db
CRM_SESSION_SECRET=<python3.11 -c "import secrets; print(secrets.token_urlsafe(64))">
CRM_COOKIE_SECURE=1
```

`CRM_ALLOW_DEFAULT_ADMIN=0` 须在 **真实 RBAC 管理员确认可登录后** 再设置。更换 `CRM_SESSION_SECRET` 会使所有人登出。

```bash
sudo chmod 600 /etc/bms/bms.env
sudo chown root:root /etc/bms/bms.env
```

### Step 3 — systemd 服务

```bash
sudo cp /home/rocky/BMS/deploy/systemd/bms.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bms
```

日常启停：

```bash
/home/rocky/BMS/scripts/bmsctl.sh start|stop|restart|status|logs
```

### Step 4 — Nginx HTTPS

确认证书已在：

- `/etc/nginx/certs/bms.throme.com.cn/fullchain.pem`
- `/etc/nginx/certs/bms.throme.com.cn/privkey.pem`

```bash
sudo cp /home/rocky/BMS/deploy/nginx/bms.throme.com.cn.conf /etc/nginx/conf.d/
sudo nginx -t
sudo systemctl reload nginx
```

配置含 HTTP 80 → HTTPS 301 跳转。

### Step 5 — 防火墙 / 安全组

阿里云安全组入站：允许 **22、80、443**；**禁止 8001**。

```bash
sudo ss -lntp | grep -E ':80|:443|:8001'
```

期望：

- `0.0.0.0:80`、`0.0.0.0:443` → nginx
- `127.0.0.1:8001` → python/uvicorn

若出现 `0.0.0.0:8001`，检查是否误跑了 `python main.py`。

### Step 6 — 备份 timer

```bash
sudo cp /home/rocky/BMS/scripts/bms_backup.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/bms_backup.sh
sudo cp /home/rocky/BMS/deploy/systemd/bms-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bms-backup.timer
```

手动试跑：`sudo systemctl start bms-backup.service`

备份目录：`~/bms_backups/<YYYYMMDD_HHMMSS>/`（保留 14 天）。

---

## 日常部署（rsync + deploy）

### 本地同步代码

```bash
rsync -avz \
  --exclude venv \
  --exclude crm_v8.db \
  --exclude uploads \
  --exclude .crm_admin_credentials.json \
  --exclude .cursor \
  ./ rocky@<server>:/home/rocky/BMS/
```

**勿同步** `.crm_admin_credentials.json`（本地管理员凭据）。

### 服务器更新

```bash
/home/rocky/BMS/scripts/deploy_server.sh
```

脚本会：`pip install` → `run_migrations.py` → import 校验 → `systemctl restart bms`。失败时 `set -e` 停止，不会 restart。

不自动覆盖：`crm_v8.db`、`uploads/`、`.crm_admin_credentials.json`。

---

## 上线验收清单（每次部署后）

```bash
sudo systemctl status bms --no-pager
curl -sS -L http://127.0.0.1:8001 | head    # 勿用 curl -I：HEAD 会 405
curl -I https://bms.throme.com.cn
curl -I http://bms.throme.com.cn             # 期望 301 → https
sudo nginx -t
sudo ss -lntp | grep -E ':80|:443|:8001'
```

功能抽检：

1. HTTPS 登录 → `/api/me` 200
2. 退出后 session cookie 已清除（`CRM_COOKIE_SECURE=1` 时 logout 的 Set-Cookie 也含 Secure）
3. 上传/下载文件正常
4. 未登录访问 `/api/files/access` 返回 401

### 备份恢复演练（首次）

```bash
# 示例：恢复到 staging 路径验证
cp ~/bms_backups/<timestamp>/crm_v8.db /tmp/crm_v8_restore.db
tar xzf ~/bms_backups/<timestamp>/uploads.tar.gz -C /tmp/
```

---

## 日志与排错

| 命令 | 用途 |
|------|------|
| `journalctl -u bms -f` | 应用日志 |
| `journalctl -u bms-backup.service` | 备份日志 |
| `tail -f ~/bms_backups/backup.log` | 备份脚本日志 |
| `sudo nginx -t` | Nginx 配置语法 |

## 明确不做（本阶段）

Docker、Kubernetes、CI/CD、certbot、自动轮换 session secret、企微 SSO、多机部署。
