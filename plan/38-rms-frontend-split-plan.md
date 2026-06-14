# 38 RMS Frontend Split Plan

## Status

- R1: DONE — core/jobs split
- R2-A: DONE — candidates split
- R2-B: DONE — candidate report overlay split
- R3-A: DONE — applications split
- R3-B: DONE — pipeline split
- R3-C: DONE — delivery review + roster conversion split
- R4: DONE — stabilization and guardrails

## Current Module Map

| File | Responsibility |
| --- | --- |
| rms.js | Vue app boot, permissions, shared display helpers, module composition |
| rms-core.js | Shared request/format/validation helpers |
| rms-application-labels.js | RMS status labels and workflow labels |
| rms-jobs.js | Jobs tab and job modal |
| rms-candidates.js | Candidates tab, candidate drawer, resume links |
| rms-applications.js | Applications/recommendation list |
| rms-pipeline.js | Pipeline filtering and progress transition |
| rms-delivery-review.js | Delivery review tab and review modal state |
| rms-roster-conversion.js | Convert-to-roster modal and GM calculator link |
| rms-candidate-report.js | New candidate report and existing-candidate recommendation overlay |

## Script Load Order

```html
rms-application-labels.js → rms-core.js → rms-candidate-report.js → rms-jobs.js →
rms-candidates.js → rms-applications.js → rms-pipeline.js → rms-delivery-review.js →
rms-roster-conversion.js → rms.js
```

## R4 Decision

Do not split `templates/pages/rms_index.html` in this phase. It is large, but template splitting has higher risk than JS splitting. Only revisit if template edits become a recurring source of regressions.

Do not split RMS dashboard in this plan. `rms-dashboard.js` remains a separate future task.

## Historical Constraints

Original split principles (HC-1 – HC-7, HC-R2-1 – HC-R2-11) remain valid reference for future edits:

- Move code only; do not change API, permissions, or business rules.
- `showValidationPrompt` lives in `rms-core.js`; business overlays (`showCandidateDuplicateDialog`, `crmConfirmActionDialog` flows) stay in shell.
- `EDUCATION_OPTIONS` and shared candidate/report constants stay in shell.
- Domain modules return prefixed modal symbols (`jobModalTitle`, `candidateModalTitle`); shell composes `modalTitle` / `modalShowSave`.
- Permission computed (`canWriteJobs`, etc.) stay in shell.
- Shell spreads module state to the template; internal cross-module references use explicit aliases where needed (HC-R2-11).

## Acceptance

```bash
node --check static/js/pages/rms.js
node --check static/js/pages/rms-core.js
node --check static/js/pages/rms-jobs.js
node --check static/js/pages/rms-candidates.js
node --check static/js/pages/rms-applications.js
node --check static/js/pages/rms-pipeline.js
node --check static/js/pages/rms-delivery-review.js
node --check static/js/pages/rms-roster-conversion.js
node --check static/js/pages/rms-candidate-report.js

./venv/bin/python -m pytest tests/test_rms_frontend_shell.py -q
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```
