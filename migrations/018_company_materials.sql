-- Company materials library (Phase 1)

CREATE TABLE IF NOT EXISTS company_materials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  confidentiality TEXT NOT NULL DEFAULT 'internal',
  owner_dept_id INTEGER NULL,
  file_name TEXT NOT NULL DEFAULT '',
  stored_path TEXT NOT NULL DEFAULT '',
  mime_type TEXT NOT NULL DEFAULT '',
  file_size INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  expires_at TEXT NULL,
  uploaded_by INTEGER NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  archived_at TEXT NULL,
  archived_by INTEGER NULL,
  FOREIGN KEY (owner_dept_id) REFERENCES sys_dept(id),
  FOREIGN KEY (uploaded_by) REFERENCES sys_user(id),
  FOREIGN KEY (archived_by) REFERENCES sys_user(id)
);

CREATE INDEX IF NOT EXISTS idx_company_materials_status ON company_materials(status);
CREATE INDEX IF NOT EXISTS idx_company_materials_category ON company_materials(category);
CREATE INDEX IF NOT EXISTS idx_company_materials_owner_dept_id ON company_materials(owner_dept_id);
