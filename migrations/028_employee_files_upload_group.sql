-- Employee files: batch upload grouping and remarks

ALTER TABLE delivery_employee_files ADD COLUMN upload_group_id TEXT NOT NULL DEFAULT '';
ALTER TABLE delivery_employee_files ADD COLUMN remarks TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_delivery_employee_files_upload_group
ON delivery_employee_files(client_id, upload_group_id)
WHERE upload_group_id != '';
