-- RMS Phase 6B-0: Offer approval chain configuration (DB-backed)

CREATE TABLE IF NOT EXISTS rms_offer_approval_configs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scope_key TEXT NOT NULL UNIQUE,
  dept_id INTEGER NULL,
  dept_superior_user_id INTEGER NULL,
  ops_head_user_id INTEGER NULL,
  gm_user_id INTEGER NULL,
  updated_by INTEGER NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rms_offer_approval_configs_dept_id
ON rms_offer_approval_configs(dept_id);
