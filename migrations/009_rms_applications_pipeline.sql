-- RMS applications: receive/delivery review/hired_at for pipeline dashboard

ALTER TABLE rms_applications ADD COLUMN receive_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE rms_applications ADD COLUMN delivery_review_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE rms_applications ADD COLUMN hired_at TEXT NOT NULL DEFAULT '';
