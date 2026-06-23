-- Roster: company-wide Throme staff number (索摩工号)

ALTER TABLE roster_entries ADD COLUMN throme_staff_no TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_roster_entries_throme_staff_no
ON roster_entries(throme_staff_no)
WHERE throme_staff_no IS NOT NULL AND throme_staff_no != '';

CREATE TABLE IF NOT EXISTS roster_throme_staff_no_sequence (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_value INTEGER NOT NULL
);

INSERT OR IGNORE INTO roster_throme_staff_no_sequence (id, next_value)
VALUES (1, 1);
