#!/usr/bin/env bash
# Daily backup: SQLite DB + uploads/ tarball. Installed to /usr/local/bin/bms_backup.sh
set -euo pipefail

BMS_ROOT="${BMS_ROOT:-/home/rocky/BMS}"
BACKUP_ROOT="${BACKUP_ROOT:-/home/rocky/bms_backups}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
DB_PATH="${BMS_ROOT}/crm_v8.db"
LOG_FILE="${BACKUP_ROOT}/backup.log"

timestamp="$(date +%Y%m%d_%H%M%S)"
dest_dir="${BACKUP_ROOT}/${timestamp}"

log() {
    echo "[$(date -Iseconds)] $*" | tee -a "${LOG_FILE}"
}

mkdir -p "${dest_dir}"

if [[ ! -f "${DB_PATH}" ]]; then
    log "ERROR: database not found: ${DB_PATH}"
    exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
    log "ERROR: sqlite3 not found (install: sudo yum install -y sqlite)"
    exit 1
fi

backup_db="${dest_dir}/crm_v8.db"
sqlite3 "${DB_PATH}" ".backup '${backup_db}'"
log "SQLite backup: ${backup_db}"

if [[ -d "${BMS_ROOT}/uploads" ]]; then
    tar czf "${dest_dir}/uploads.tar.gz" -C "${BMS_ROOT}" uploads/
    log "Uploads archive: ${dest_dir}/uploads.tar.gz"
else
    log "WARN: uploads directory missing, skipped"
fi

find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime +"${RETAIN_DAYS}" -exec rm -rf {} +
log "Backup complete: ${dest_dir}"
