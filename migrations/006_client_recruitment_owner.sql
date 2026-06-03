-- CRM clients: recruitment indexes (columns via ORM create_all + main._ensure_clients_schema_compat)

CREATE INDEX IF NOT EXISTS idx_clients_recruitment_owner_user_id ON clients(recruitment_owner_user_id);
CREATE INDEX IF NOT EXISTS idx_clients_recruitment_dept_id ON clients(recruitment_dept_id);
