-- 02.5 data scope: departments and role scope configuration

CREATE TABLE IF NOT EXISTS sys_dept (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  code TEXT NOT NULL UNIQUE,
  parent_id INTEGER NULL,
  path TEXT NOT NULL,
  dept_type TEXT NOT NULL DEFAULT 'general',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(parent_id) REFERENCES sys_dept(id)
);

CREATE TABLE IF NOT EXISTS sys_user_dept (
  user_id INTEGER NOT NULL,
  dept_id INTEGER NOT NULL,
  is_primary INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, dept_id),
  FOREIGN KEY(user_id) REFERENCES sys_user(id),
  FOREIGN KEY(dept_id) REFERENCES sys_dept(id)
);

CREATE TABLE IF NOT EXISTS sys_role_data_scope (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role_id INTEGER NOT NULL,
  resource_code TEXT NOT NULL,
  action TEXT NOT NULL,
  scope_type TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(role_id, resource_code, action),
  FOREIGN KEY(role_id) REFERENCES sys_role(id)
);
