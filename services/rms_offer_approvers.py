"""Offer approval chain constants (Phase 6B / 6B-0)."""
from __future__ import annotations

from services.rms_offer_approval_config import (
    OFFER_APPROVAL_CONFIG_INCOMPLETE,
    STEP_DEPT_SUPERIOR,
    STEP_GM,
    STEP_OPS_HEAD,
    STEP_TYPE_LABELS,
    ApprovalStepSpec,
    approval_node_label,
)

__all__ = [
    "OFFER_APPROVAL_CONFIG_INCOMPLETE",
    "STEP_DEPT_SUPERIOR",
    "STEP_OPS_HEAD",
    "STEP_GM",
    "STEP_TYPE_LABELS",
    "ApprovalStepSpec",
    "approval_node_label",
]
