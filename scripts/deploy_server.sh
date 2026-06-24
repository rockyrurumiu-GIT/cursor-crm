#!/usr/bin/env bash
# Run on server after rsync sync. Does not touch DB, uploads, or admin credentials.
set -euo pipefail

cd /home/rocky/BMS

set -a
. /etc/bms/bms.env
set +a

./venv/bin/pip install -r requirements.txt
./venv/bin/python scripts/run_migrations.py
./venv/bin/python -c "import main; print('main import ok')"
sudo systemctl restart bms
sudo systemctl status bms --no-pager
