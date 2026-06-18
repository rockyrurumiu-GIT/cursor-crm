from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Literal, Mapping, Optional, Tuple

from auth.permissions import ALL_PERMISSION_CODES

# --- Scope types (02.5 + 03 aligned) ---

SCOPE_NONE = "none"
SCOPE_SELF = "self"
SCOPE_ASSIGNED = "assigned"
SCOPE_DEPT = "dept"
SCOPE_DEPT_AND_CHILD = "dept_and_child"
SCOPE_ALL = "all"
SCOPE_SHARED = "shared"

SCOPE_TYPES: Tuple[str, ...] = (
    SCOPE_NONE,
    SCOPE_SELF,
    SCOPE_ASSIGNED,
    SCOPE_DEPT,
    SCOPE_DEPT_AND_CHILD,
    SCOPE_ALL,
    SCOPE_SHARED,
)

# Merge priority for multi-role resolution (02.5). shared is handled in phase 03.
SCOPE_MERGE_ORDER: Tuple[str, ...] = (
    SCOPE_NONE,
    SCOPE_SELF,
    SCOPE_ASSIGNED,
    SCOPE_DEPT,
    SCOPE_DEPT_AND_CHILD,
    SCOPE_ALL,
)

# Phase 03 enum names for the subset implemented in 02.5.
SCOPE_PHASE03_ALIASES: Dict[str, str] = {
    SCOPE_SELF: "SELF",
    SCOPE_DEPT_AND_CHILD: "DEPT_AND_CHILD",
    SCOPE_ALL: "ALL",
    SCOPE_SHARED: "SHARED",
}

ScopeMode = Literal["sales", "delivery", "inherit_parent"]

CLIENT_TABLE = "clients"
CLIENT_SALES_OWNER_COL = "owner_user_id"
CLIENT_SALES_DEPT_COL = "owner_dept_id"
CLIENT_SALES_ASSIGNED_COL = "assigned_user_id"
CLIENT_DELIVERY_OWNER_COL = "delivery_owner_user_id"
CLIENT_DELIVERY_DEPT_COL = "delivery_dept_id"
CLIENT_RECRUITMENT_OWNER_COL = "recruitment_owner_user_id"
CLIENT_RECRUITMENT_DEPT_COL = "recruitment_dept_id"
CLIENT_FK = "client_id"

# CRM client list: dept scope matches if any role dept column is in range.
CLIENT_DEPT_COLS_FOR_LIST = (
    CLIENT_SALES_DEPT_COL,
    CLIENT_DELIVERY_DEPT_COL,
    CLIENT_RECRUITMENT_DEPT_COL,
)


@dataclass(frozen=True)
class ResourceScopeAnchor:
    """How to apply row-level scope for a resource at query time."""

    resource_code: str
    primary_table: str
    scope_mode: ScopeMode
    inherit_via_client: bool = False
    client_fk: Optional[str] = None
    owner_user_col: Optional[str] = None
    owner_dept_col: Optional[str] = None
    assigned_user_col: Optional[str] = None
    entity_owner_col: Optional[str] = None
    fallback_inherit_client: bool = False


# --- Resource codes ---

RESOURCE_CRM_CLIENT = "crm.client"
RESOURCE_CRM_OPPORTUNITY = "crm.opportunity"
RESOURCE_CRM_CONTACT = "crm.contact"
RESOURCE_CRM_VISIT = "crm.visit"
RESOURCE_DELIVERY_ROSTER = "delivery.roster"
RESOURCE_DELIVERY_PIPELINE = "delivery.pipeline"
RESOURCE_DELIVERY_INTERVIEWS = "delivery.interviews"
RESOURCE_DELIVERY_HANDBOOK = "delivery.handbook"
RESOURCE_DELIVERY_HANDOFF = "delivery.handoff"
RESOURCE_DELIVERY_SETTLEMENT = "delivery.settlement"
RESOURCE_RMS_JOB = "rms.job"
RESOURCE_RMS_APPLICATION = "rms.application"
RESOURCE_RMS_CANDIDATE = "rms.candidate"
RESOURCE_RMS_RESUME = "rms.resume"
RESOURCE_FILE = "file"

RESOURCE_CODES: Tuple[str, ...] = (
    RESOURCE_CRM_CLIENT,
    RESOURCE_CRM_OPPORTUNITY,
    RESOURCE_CRM_CONTACT,
    RESOURCE_CRM_VISIT,
    RESOURCE_DELIVERY_ROSTER,
    RESOURCE_DELIVERY_PIPELINE,
    RESOURCE_DELIVERY_INTERVIEWS,
    RESOURCE_DELIVERY_HANDBOOK,
    RESOURCE_DELIVERY_HANDOFF,
    RESOURCE_DELIVERY_SETTLEMENT,
    RESOURCE_RMS_JOB,
    RESOURCE_RMS_APPLICATION,
    RESOURCE_RMS_CANDIDATE,
    RESOURCE_RMS_RESUME,
    RESOURCE_FILE,
)

DELIVERY_RESOURCE_CODES: FrozenSet[str] = frozenset(
    code for code in RESOURCE_CODES if code.startswith("delivery.")
)

SYSTEM_PERMISSIONS: FrozenSet[str] = frozenset({
    "system.users.manage",
    "system.users.delete",
    "system.roles.manage",
    "system.roles.delete",
    "system.audit.read",
    "dashboard.read",
    "dashboard.write",
    "dashboard.delete",
    "tools.gm_calc.read",
})

BUSINESS_PERMISSIONS: FrozenSet[str] = frozenset(
    code for code in ALL_PERMISSION_CODES if code not in SYSTEM_PERMISSIONS
)

DATA_SCOPE_ACTIONS: Tuple[str, ...] = ("read", "write", "export", "delete")

# Function permission code -> data-scope resource code
PERMISSION_TO_RESOURCE: Dict[str, str] = {
    "crm.clients.read": RESOURCE_CRM_CLIENT,
    "crm.clients.write": RESOURCE_CRM_CLIENT,
    "crm.clients.delete": RESOURCE_CRM_CLIENT,
    "crm.opportunities.read": RESOURCE_CRM_OPPORTUNITY,
    "crm.opportunities.write": RESOURCE_CRM_OPPORTUNITY,
    "crm.opportunities.delete": RESOURCE_CRM_OPPORTUNITY,
    "crm.contacts.read": RESOURCE_CRM_CONTACT,
    "crm.contacts.write": RESOURCE_CRM_CONTACT,
    "crm.contacts.delete": RESOURCE_CRM_CONTACT,
    "crm.visits.read": RESOURCE_CRM_VISIT,
    "crm.visits.write": RESOURCE_CRM_VISIT,
    "crm.visits.delete": RESOURCE_CRM_VISIT,
    "delivery.roster.read": RESOURCE_DELIVERY_ROSTER,
    "delivery.roster.write": RESOURCE_DELIVERY_ROSTER,
    "delivery.roster.delete": RESOURCE_DELIVERY_ROSTER,
    "delivery.pipeline.read": RESOURCE_DELIVERY_PIPELINE,
    "delivery.pipeline.write": RESOURCE_DELIVERY_PIPELINE,
    "delivery.pipeline.delete": RESOURCE_DELIVERY_PIPELINE,
    "delivery.handbook.read": RESOURCE_DELIVERY_HANDBOOK,
    "delivery.handbook.write": RESOURCE_DELIVERY_HANDBOOK,
    "delivery.handbook.delete": RESOURCE_DELIVERY_HANDBOOK,
    "delivery.handoff.read": RESOURCE_DELIVERY_HANDOFF,
    "delivery.handoff.write": RESOURCE_DELIVERY_HANDOFF,
    "delivery.handoff.review": RESOURCE_DELIVERY_HANDOFF,
    "delivery.interviews.read": RESOURCE_DELIVERY_INTERVIEWS,
    "delivery.interviews.write": RESOURCE_DELIVERY_INTERVIEWS,
    "delivery.interviews.delete": RESOURCE_DELIVERY_INTERVIEWS,
    "delivery.settlement.read": RESOURCE_DELIVERY_SETTLEMENT,
    "delivery.settlement.write": RESOURCE_DELIVERY_SETTLEMENT,
    "delivery.settlement.delete": RESOURCE_DELIVERY_SETTLEMENT,
    "rms.jobs.read": RESOURCE_RMS_JOB,
    "rms.jobs.write": RESOURCE_RMS_JOB,
    "rms.jobs.delete": RESOURCE_RMS_JOB,
    "rms.candidates.read": RESOURCE_RMS_CANDIDATE,
    "rms.candidates.write": RESOURCE_RMS_CANDIDATE,
    "rms.candidates.delete": RESOURCE_RMS_CANDIDATE,
    "rms.resumes.read": RESOURCE_RMS_RESUME,
    "rms.resumes.download": RESOURCE_RMS_RESUME,
    "rms.contacts.view": RESOURCE_RMS_CANDIDATE,
    "rms.applications.read": RESOURCE_RMS_APPLICATION,
    "rms.applications.write": RESOURCE_RMS_APPLICATION,
    "rms.applications.delete": RESOURCE_RMS_APPLICATION,
    "rms.offer_approval.submit": RESOURCE_RMS_APPLICATION,
    "rms.matching.run": RESOURCE_RMS_JOB,
    "rms.analytics.read": RESOURCE_RMS_JOB,
}

RESOURCE_SCOPE_ANCHOR: Mapping[str, ResourceScopeAnchor] = {
    RESOURCE_CRM_CLIENT: ResourceScopeAnchor(
        resource_code=RESOURCE_CRM_CLIENT,
        primary_table=CLIENT_TABLE,
        scope_mode="sales",
        owner_user_col=CLIENT_SALES_OWNER_COL,
        owner_dept_col=CLIENT_SALES_DEPT_COL,
        assigned_user_col=CLIENT_SALES_ASSIGNED_COL,
    ),
    RESOURCE_CRM_OPPORTUNITY: ResourceScopeAnchor(
        resource_code=RESOURCE_CRM_OPPORTUNITY,
        primary_table="opportunities",
        scope_mode="sales",
        client_fk=CLIENT_FK,
        owner_user_col="owner_user_id",
        owner_dept_col="owner_dept_id",
        fallback_inherit_client=True,
    ),
    RESOURCE_CRM_CONTACT: ResourceScopeAnchor(
        resource_code=RESOURCE_CRM_CONTACT,
        primary_table="contacts",
        scope_mode="sales",
        inherit_via_client=True,
        client_fk=CLIENT_FK,
    ),
    RESOURCE_CRM_VISIT: ResourceScopeAnchor(
        resource_code=RESOURCE_CRM_VISIT,
        primary_table="visits",
        scope_mode="sales",
        inherit_via_client=True,
        client_fk=CLIENT_FK,
        owner_user_col="owner_user_id",
        owner_dept_col="owner_dept_id",
    ),
    RESOURCE_DELIVERY_ROSTER: ResourceScopeAnchor(
        resource_code=RESOURCE_DELIVERY_ROSTER,
        primary_table="roster_entries",
        scope_mode="delivery",
        inherit_via_client=True,
        client_fk=CLIENT_FK,
    ),
    RESOURCE_DELIVERY_PIPELINE: ResourceScopeAnchor(
        resource_code=RESOURCE_DELIVERY_PIPELINE,
        primary_table="delivery_pipeline_entries",
        scope_mode="delivery",
        inherit_via_client=True,
        client_fk=CLIENT_FK,
        entity_owner_col="recruiter_user_id",
        fallback_inherit_client=True,
    ),
    RESOURCE_DELIVERY_INTERVIEWS: ResourceScopeAnchor(
        resource_code=RESOURCE_DELIVERY_INTERVIEWS,
        primary_table="delivery_interview_entries",
        scope_mode="delivery",
        inherit_via_client=True,
        client_fk=CLIENT_FK,
    ),
    RESOURCE_DELIVERY_HANDBOOK: ResourceScopeAnchor(
        resource_code=RESOURCE_DELIVERY_HANDBOOK,
        primary_table="delivery_handbook_files",
        scope_mode="delivery",
        inherit_via_client=True,
        client_fk=CLIENT_FK,
    ),
    RESOURCE_DELIVERY_HANDOFF: ResourceScopeAnchor(
        resource_code=RESOURCE_DELIVERY_HANDOFF,
        primary_table="handoff_requests",
        scope_mode="delivery",
        inherit_via_client=True,
        client_fk=CLIENT_FK,
        entity_owner_col="delivery_owner_user_id",
        fallback_inherit_client=True,
    ),
    RESOURCE_DELIVERY_SETTLEMENT: ResourceScopeAnchor(
        resource_code=RESOURCE_DELIVERY_SETTLEMENT,
        primary_table="delivery_settlement_entries",
        scope_mode="delivery",
        inherit_via_client=True,
        client_fk=CLIENT_FK,
    ),
    RESOURCE_RMS_JOB: ResourceScopeAnchor(
        resource_code=RESOURCE_RMS_JOB,
        primary_table="rms_jobs",
        scope_mode="delivery",
        inherit_via_client=True,
        client_fk=CLIENT_FK,
        entity_owner_col="owner_user_id",
    ),
    RESOURCE_RMS_APPLICATION: ResourceScopeAnchor(
        resource_code=RESOURCE_RMS_APPLICATION,
        primary_table="rms_applications",
        scope_mode="delivery",
        inherit_via_client=True,
        client_fk=CLIENT_FK,
    ),
    RESOURCE_RMS_CANDIDATE: ResourceScopeAnchor(
        resource_code=RESOURCE_RMS_CANDIDATE,
        primary_table="rms_candidates",
        scope_mode="delivery",
        inherit_via_client=False,
    ),
    RESOURCE_RMS_RESUME: ResourceScopeAnchor(
        resource_code=RESOURCE_RMS_RESUME,
        primary_table="rms_resumes",
        scope_mode="delivery",
        inherit_via_client=False,
    ),
    RESOURCE_FILE: ResourceScopeAnchor(
        resource_code=RESOURCE_FILE,
        primary_table="",
        scope_mode="inherit_parent",
        inherit_via_client=True,
    ),
}


def merge_scope_types(*scopes: str) -> str:
    """Return the broadest scope among the given scope type codes."""
    best = SCOPE_NONE
    best_rank = -1
    order = {code: idx for idx, code in enumerate(SCOPE_MERGE_ORDER)}
    for scope in scopes:
        rank = order.get(scope, -1)
        if rank > best_rank:
            best = scope
            best_rank = rank
    return best


def permission_to_resource(permission_code: str) -> Optional[str]:
    return PERMISSION_TO_RESOURCE.get(permission_code)


def is_system_permission(permission_code: str) -> bool:
    return permission_code in SYSTEM_PERMISSIONS


def is_business_permission(permission_code: str) -> bool:
    return permission_code in BUSINESS_PERMISSIONS


def client_scope_columns(scope_mode: ScopeMode) -> Tuple[str, str, Optional[str]]:
    """Return (owner_user_col, owner_dept_col, assigned_user_col) on clients for a scope mode."""
    if scope_mode == "delivery":
        return CLIENT_DELIVERY_OWNER_COL, CLIENT_DELIVERY_DEPT_COL, None
    if scope_mode == "sales":
        return CLIENT_SALES_OWNER_COL, CLIENT_SALES_DEPT_COL, CLIENT_SALES_ASSIGNED_COL
    raise ValueError(f"no client scope columns for mode {scope_mode!r}")
