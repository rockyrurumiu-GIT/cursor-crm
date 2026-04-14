# Import And Rollback Standard

This project uses a unified safety standard for any page/module with CSV import.

## Required baseline (default for new import pages)

1. Confirm token before destructive import
- UI must require user input `CONFIRM` before import request is sent.
- Backend must verify `confirm=CONFIRM` and reject otherwise.

2. Backup before clear-and-import
- Before clearing old data, backend must export current data to CSV in `backups/`.
- Backup filename should include module identifier and timestamp.

3. One-click rollback endpoint
- Every import module must provide a `restore/latest` backend endpoint.
- Restore action must clear current data and recover from the latest backup CSV.
- UI placement rule: rollback button must be the rightmost action button in that page/module.

4. Audit log
- Import summary and skip details must be written into audit logs.
- Rollback action must be logged with backup filename and row counts.

## Existing modules that already follow this

- Roster import (`/api/clients/{client_id}/roster/import`) + rollback (`/api/clients/{client_id}/roster/restore/latest`)
- Settlement import (`/api/delivery/settlement/import`) + rollback (`/api/delivery/settlement/restore/latest`)
