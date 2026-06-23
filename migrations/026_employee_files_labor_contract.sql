-- Employee files: labor contract metadata and auto-numbering

ALTER TABLE delivery_employee_files ADD COLUMN document_type TEXT NOT NULL DEFAULT '';
ALTER TABLE delivery_employee_files ADD COLUMN employee_full_name TEXT NOT NULL DEFAULT '';
ALTER TABLE delivery_employee_files ADD COLUMN employee_contact_info TEXT NOT NULL DEFAULT '';
ALTER TABLE delivery_employee_files ADD COLUMN roster_entry_id INTEGER;
ALTER TABLE delivery_employee_files ADD COLUMN throme_staff_no TEXT NOT NULL DEFAULT '';
ALTER TABLE delivery_employee_files ADD COLUMN labor_contract_no TEXT NOT NULL DEFAULT '';
ALTER TABLE delivery_employee_files ADD COLUMN contract_sign_date TEXT NOT NULL DEFAULT '';
ALTER TABLE delivery_employee_files ADD COLUMN contract_valid_until TEXT NOT NULL DEFAULT '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_delivery_employee_files_labor_contract_no
ON delivery_employee_files(labor_contract_no)
WHERE labor_contract_no IS NOT NULL AND labor_contract_no != '';
