-- Contract upload: remarks field (idempotent via auth/migrate.py ledger)
ALTER TABLE contracts ADD COLUMN remarks TEXT NOT NULL DEFAULT '';
