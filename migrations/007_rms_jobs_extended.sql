-- RMS jobs: extended job posting fields (Phase 2.5 form)

ALTER TABLE rms_jobs ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium';
ALTER TABLE rms_jobs ADD COLUMN salary_cap TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_jobs ADD COLUMN years_required TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_jobs ADD COLUMN education TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_jobs ADD COLUMN overtime_travel TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_jobs ADD COLUMN interviewer TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_jobs ADD COLUMN note TEXT NOT NULL DEFAULT '';
