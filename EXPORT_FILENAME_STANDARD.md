# Export Filename Standard

Use this standard for all current and future export features.

## Backend response header (required)

- Always set `Content-Disposition` with both:
  - ASCII fallback: `filename="xxx.csv"`
  - UTF-8 name: `filename*=UTF-8''<urlencoded-name>`
- Prefer readable datetime suffix: `YYYYMMDD_HHMMSS`
- Example Chinese name: `结算回款_20260414_153025.csv`
- MUST use shared helper in `main.py`: `_set_csv_download_headers(response, chinese_filename, ascii_base)`

## Frontend download behavior (required)

- Do not hardcode export filename.
- Always read `Content-Disposition` first, and use backend-provided filename.
- Use a fallback filename only when header parsing fails.
- Reuse shared helper in `templates/base.html`:
  - `window.crmFilenameFromDisposition(...)`
  - `window.crmDownloadBlob(...)`

## Guardrail check (required before release)

- Run:
  - `python3 scripts/check_export_filename_standard.py`
- Any new `/export` route not using `_set_csv_download_headers(...)` should fail the check.

## Rationale

- Keeps Chinese filenames stable and consistent.
- Avoids naming drift between backend and frontend.
- Makes future export pages follow one implementation path by default.
