from __future__ import annotations

from typing import FrozenSet

ROLE_SUPER_ADMIN = "SUPER_ADMIN"
ROLE_SALES = "SALES"
ROLE_DELIVERY = "DELIVERY"
ROLE_VIEWER = "VIEWER"

ALL_PERMISSION_CODES: FrozenSet[str] = frozenset({
    "crm.clients.read",
    "crm.clients.write",
    "crm.opportunities.read",
    "crm.opportunities.write",
    "crm.contacts.read",
    "crm.contacts.write",
    "crm.visits.read",
    "crm.visits.write",
    "delivery.roster.read",
    "delivery.roster.write",
    "delivery.pipeline.read",
    "delivery.pipeline.write",
    "delivery.handbook.read",
    "delivery.handbook.write",
    "delivery.handoff.read",
    "delivery.handoff.write",
    "delivery.handoff.review",
    "delivery.interviews.read",
    "delivery.interviews.write",
    "delivery.settlement.read",
    "delivery.settlement.write",
    "rms.jobs.read",
    "rms.jobs.write",
    "rms.candidates.read",
    "rms.candidates.write",
    "rms.resumes.read",
    "rms.resumes.download",
    "rms.contacts.view",
    "rms.applications.read",
    "rms.applications.write",
    "rms.matching.run",
    "rms.analytics.read",
    "system.users.manage",
    "system.roles.manage",
    "system.audit.read",
    "dashboard.read",
    "dashboard.write",
    "tools.gm_calc.read",
})

ROLE_DEFAULT_PERMISSIONS: dict[str, FrozenSet[str]] = {
    ROLE_SUPER_ADMIN: ALL_PERMISSION_CODES,
    ROLE_SALES: frozenset({
        "crm.clients.read",
        "crm.clients.write",
        "crm.opportunities.read",
        "crm.opportunities.write",
        "crm.contacts.read",
        "crm.contacts.write",
        "crm.visits.read",
        "crm.visits.write",
        "dashboard.read",
    }),
    ROLE_DELIVERY: frozenset({
        "crm.clients.read",
        "delivery.roster.read",
        "delivery.roster.write",
        "delivery.pipeline.read",
        "delivery.pipeline.write",
        "delivery.handbook.read",
        "delivery.handbook.write",
        "delivery.handoff.read",
        "delivery.handoff.write",
        "delivery.handoff.review",
        "delivery.interviews.read",
        "delivery.interviews.write",
        "delivery.settlement.read",
        "delivery.settlement.write",
        "rms.jobs.read",
        "rms.applications.read",
        "rms.analytics.read",
        "dashboard.read",
    }),
    ROLE_VIEWER: frozenset({
        "crm.clients.read",
        "crm.opportunities.read",
        "crm.contacts.read",
        "crm.visits.read",
        "delivery.roster.read",
        "delivery.pipeline.read",
        "delivery.handbook.read",
        "delivery.handoff.read",
        "delivery.interviews.read",
        "delivery.settlement.read",
        "dashboard.read",
    }),
}

# Nav/menu visibility: permission required to show section (any perm in set grants section)
NAV_SECTION_PERMISSIONS: dict[str, str] = {
    "home": "crm.clients.read",
    "customers": "crm.clients.read",
    "opportunity": "crm.opportunities.read",
    "goals": "crm.opportunities.read",
    "delivery": "delivery.roster.read",
    "rms": "rms.jobs.read",
    "dashboards": "dashboard.read",
    "system": "system.users.manage",
}
