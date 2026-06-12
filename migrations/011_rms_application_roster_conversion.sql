-- RMS applications: track manual conversion to delivery roster

ALTER TABLE rms_applications ADD COLUMN converted_to_roster_entry_id INTEGER NULL;
ALTER TABLE rms_applications ADD COLUMN converted_to_roster_at TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_applications ADD COLUMN converted_to_roster_by INTEGER NULL;

CREATE INDEX IF NOT EXISTS idx_rms_applications_converted_roster
ON rms_applications(converted_to_roster_entry_id);
