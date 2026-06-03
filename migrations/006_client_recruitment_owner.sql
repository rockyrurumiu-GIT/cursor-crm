-- CRM clients: recruitment owner/dept (multi-role visibility)

ALTER TABLE clients ADD COLUMN recruitment_owner_user_id INTEGER NULL;
ALTER TABLE clients ADD COLUMN recruitment_dept_id INTEGER NULL;

CREATE INDEX IF NOT EXISTS idx_clients_recruitment_owner_user_id ON clients(recruitment_owner_user_id);
CREATE INDEX IF NOT EXISTS idx_clients_recruitment_dept_id ON clients(recruitment_dept_id);
