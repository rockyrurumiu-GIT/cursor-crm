# RMS Phase 6B: Offer approval

Brief execution plan — see `.cursor/plans/rms_offer_approval_bf351f43.plan.md` for full spec.

## Status mapping

| Application | Offer record |
|-------------|--------------|
| `offer_approval_pending` | `pending` |
| `onboarding` | `approved` |
| `offer_dropped` | `offer_dropped` |
| `onboarding_lost` | `onboarding_lost` |
| `pending_offer` (rejected) | `rejected` (not in Offer Tab) |

## Approvers

All from server-local `data/rms_offer_approvers.json` (gitignored). Repository ships `data/rms_offer_approvers.json.example` only.

Phase 6C: org leader / WeCom sync.

## Notifications

`GET /api/notifications` — any logged-in user; filtered by `username == current user`. Returns `application_id`, `offer_record_id`, `link_url`.

## Constraints

- `offer_approval_pending` cannot be corrected to `onboarding` (service guard).
- `pending_offer → onboarding` removed from transitions; must use approval API.
- Approve/reject: current step approver only (super admin override); no `rms.applications.write` required.
