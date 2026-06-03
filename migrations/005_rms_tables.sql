-- RMS Phase 1: core tables (DDL source of truth for rms_* schema)

CREATE TABLE IF NOT EXISTS rms_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  wechat TEXT NOT NULL DEFAULT '',
  current_company TEXT NOT NULL DEFAULT '',
  current_title TEXT NOT NULL DEFAULT '',
  city TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  created_by_user_id INTEGER NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (created_by_user_id) REFERENCES sys_user(id)
);

CREATE INDEX IF NOT EXISTS idx_rms_candidates_created_by_user_id ON rms_candidates(created_by_user_id);

CREATE INDEX IF NOT EXISTS idx_rms_candidates_name ON rms_candidates(name);

CREATE TABLE IF NOT EXISTS rms_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id INTEGER NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  department TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  headcount INTEGER NOT NULL DEFAULT 1,
  job_description TEXT NOT NULL DEFAULT '',
  requirements TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',
  owner_user_id INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (client_id) REFERENCES clients(id),
  FOREIGN KEY (owner_user_id) REFERENCES sys_user(id)
);

CREATE INDEX IF NOT EXISTS idx_rms_jobs_client_id ON rms_jobs(client_id);

CREATE INDEX IF NOT EXISTS idx_rms_jobs_owner_user_id ON rms_jobs(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_rms_jobs_status ON rms_jobs(status);

CREATE TABLE IF NOT EXISTS rms_resumes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_id INTEGER NOT NULL,
  file_name TEXT NOT NULL DEFAULT '',
  file_path TEXT NOT NULL DEFAULT '',
  file_type TEXT NOT NULL DEFAULT '',
  parsed_text TEXT NOT NULL DEFAULT '',
  parsed_json TEXT NOT NULL DEFAULT '{}',
  uploaded_by INTEGER NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (candidate_id) REFERENCES rms_candidates(id) ON DELETE CASCADE,
  FOREIGN KEY (uploaded_by) REFERENCES sys_user(id)
);

CREATE INDEX IF NOT EXISTS idx_rms_resumes_candidate_id ON rms_resumes(candidate_id);

CREATE TABLE IF NOT EXISTS rms_applications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL,
  candidate_id INTEGER NOT NULL,
  client_id INTEGER NOT NULL,
  resume_id INTEGER NULL,
  status TEXT NOT NULL DEFAULT 'recommended',
  recommended_by INTEGER NULL,
  recommended_at TEXT NOT NULL DEFAULT '',
  current_stage TEXT NOT NULL DEFAULT '',
  last_activity_at TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (job_id) REFERENCES rms_jobs(id),
  FOREIGN KEY (candidate_id) REFERENCES rms_candidates(id),
  FOREIGN KEY (client_id) REFERENCES clients(id),
  FOREIGN KEY (resume_id) REFERENCES rms_resumes(id),
  FOREIGN KEY (recommended_by) REFERENCES sys_user(id),
  UNIQUE (job_id, candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_rms_applications_client_id ON rms_applications(client_id);

CREATE INDEX IF NOT EXISTS idx_rms_applications_job_id ON rms_applications(job_id);

CREATE INDEX IF NOT EXISTS idx_rms_applications_candidate_id ON rms_applications(candidate_id);

CREATE INDEX IF NOT EXISTS idx_rms_applications_status ON rms_applications(status);

CREATE TABLE IF NOT EXISTS rms_application_status_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  application_id INTEGER NOT NULL,
  from_status TEXT NOT NULL DEFAULT '',
  to_status TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  changed_by INTEGER NULL,
  changed_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (application_id) REFERENCES rms_applications(id) ON DELETE CASCADE,
  FOREIGN KEY (changed_by) REFERENCES sys_user(id)
);

CREATE INDEX IF NOT EXISTS idx_rms_app_status_hist_app_id ON rms_application_status_history(application_id);

CREATE INDEX IF NOT EXISTS idx_rms_app_status_hist_changed_at ON rms_application_status_history(changed_at);

CREATE TABLE IF NOT EXISTS rms_interviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  application_id INTEGER NOT NULL,
  interview_time TEXT NOT NULL DEFAULT '',
  interview_round TEXT NOT NULL DEFAULT '',
  interviewer TEXT NOT NULL DEFAULT '',
  result TEXT NOT NULL DEFAULT '',
  feedback TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (application_id) REFERENCES rms_applications(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rms_interviews_application_id ON rms_interviews(application_id);

CREATE TABLE IF NOT EXISTS rms_offers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  application_id INTEGER NOT NULL,
  offer_status TEXT NOT NULL DEFAULT '',
  salary TEXT NOT NULL DEFAULT '',
  expected_onboard_date TEXT NOT NULL DEFAULT '',
  actual_onboard_date TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (application_id) REFERENCES rms_applications(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rms_offers_application_id ON rms_offers(application_id);

CREATE TABLE IF NOT EXISTS rms_match_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  application_id INTEGER NOT NULL,
  job_id INTEGER NOT NULL,
  candidate_id INTEGER NOT NULL,
  resume_id INTEGER NULL,
  score REAL NULL,
  summary TEXT NOT NULL DEFAULT '',
  strengths TEXT NOT NULL DEFAULT '',
  risks TEXT NOT NULL DEFAULT '',
  model_name TEXT NOT NULL DEFAULT '',
  created_by INTEGER NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (application_id) REFERENCES rms_applications(id) ON DELETE CASCADE,
  FOREIGN KEY (job_id) REFERENCES rms_jobs(id),
  FOREIGN KEY (candidate_id) REFERENCES rms_candidates(id),
  FOREIGN KEY (resume_id) REFERENCES rms_resumes(id),
  FOREIGN KEY (created_by) REFERENCES sys_user(id)
);

CREATE INDEX IF NOT EXISTS idx_rms_match_results_application_id ON rms_match_results(application_id);

CREATE INDEX IF NOT EXISTS idx_rms_match_results_job_id ON rms_match_results(job_id);
