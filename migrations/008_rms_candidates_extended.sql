-- RMS candidates: extended profile fields (Phase 2.5+)

ALTER TABLE rms_candidates ADD COLUMN age TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_candidates ADD COLUMN work_years TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_candidates ADD COLUMN email_wechat TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_candidates ADD COLUMN target_job_id INTEGER NULL;
ALTER TABLE rms_candidates ADD COLUMN target_client_id INTEGER NULL;
ALTER TABLE rms_candidates ADD COLUMN current_salary TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_candidates ADD COLUMN expected_salary TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_candidates ADD COLUMN available_date TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_candidates ADD COLUMN education_level TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_candidates ADD COLUMN school TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_candidates ADD COLUMN major TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_candidates ADD COLUMN gender TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_candidates ADD COLUMN marital_status TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_rms_candidates_target_job_id ON rms_candidates(target_job_id);
CREATE INDEX IF NOT EXISTS idx_rms_candidates_target_client_id ON rms_candidates(target_client_id);
