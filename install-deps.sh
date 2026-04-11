#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/venv/bin/pip" ]]; then
  echo "找不到 venv/bin/pip。请先执行: python3 -m venv venv" >&2
  exit 1
fi
# 绕过失效的系统代理（pip 报 ProxyError / Errno 61 Connection refused 时）
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  "$ROOT/venv/bin/pip" install -r "$ROOT/requirements.txt"
echo "依赖已安装。启动: source venv/bin/activate && python ito_crm_ultimate.py"
