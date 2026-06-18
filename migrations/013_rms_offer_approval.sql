-- RMS Phase 6B: Offer approval records, steps, and notification deep links

CREATE TABLE IF NOT EXISTS rms_offer_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  application_id INTEGER NOT NULL REFERENCES rms_applications(id),
  candidate_id INTEGER,
  job_id INTEGER,
  client_id INTEGER,
  status TEXT NOT NULL DEFAULT '',
  current_approval_node TEXT NOT NULL DEFAULT '',
  gm_pct TEXT NOT NULL DEFAULT '',
  gm_amount TEXT NOT NULL DEFAULT '',
  monthly_quote_tax TEXT NOT NULL DEFAULT '',
  pre_tax_salary TEXT NOT NULL DEFAULT '',
  salary_months TEXT NOT NULL DEFAULT '',
  planned_onboard_date TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  form_json TEXT NOT NULL DEFAULT '{}',
  created_by INTEGER,
  created_at TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS rms_offer_approval_steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_record_id INTEGER NOT NULL REFERENCES rms_offer_records(id) ON DELETE CASCADE,
  step_order INTEGER NOT NULL,
  step_type TEXT NOT NULL DEFAULT '',
  approver_user_id INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',
  comment TEXT NOT NULL DEFAULT '',
  acted_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_rms_offer_records_application_id ON rms_offer_records(application_id);
CREATE INDEX IF NOT EXISTS idx_rms_offer_records_status ON rms_offer_records(status);
CREATE INDEX IF NOT EXISTS idx_rms_offer_steps_record ON rms_offer_approval_steps(offer_record_id);
CREATE INDEX IF NOT EXISTS idx_rms_offer_steps_approver ON rms_offer_approval_steps(approver_user_id, status);

ALTER TABLE crm_notifications ADD COLUMN application_id INTEGER NULL;
ALTER TABLE crm_notifications ADD COLUMN offer_record_id INTEGER NULL;
ALTER TABLE crm_notifications ADD COLUMN link_url TEXT NOT NULL DEFAULT '';
