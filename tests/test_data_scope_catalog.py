from __future__ import annotations

import auth.data_scope_catalog as catalog
from auth.permissions import ALL_PERMISSION_CODES


def test_scope_types_align_with_phase03_subset():
    assert catalog.SCOPE_SELF in catalog.SCOPE_PHASE03_ALIASES
    assert catalog.SCOPE_PHASE03_ALIASES[catalog.SCOPE_SELF] == "SELF"
    assert catalog.SCOPE_PHASE03_ALIASES[catalog.SCOPE_DEPT_AND_CHILD] == "DEPT_AND_CHILD"
    assert catalog.SCOPE_PHASE03_ALIASES[catalog.SCOPE_ALL] == "ALL"
    assert catalog.SCOPE_PHASE03_ALIASES[catalog.SCOPE_SHARED] == "SHARED"
    assert catalog.SCOPE_SHARED in catalog.SCOPE_TYPES
    assert catalog.SCOPE_SHARED not in catalog.SCOPE_MERGE_ORDER


def test_scope_merge_order():
    assert catalog.merge_scope_types("none", "self") == "self"
    assert catalog.merge_scope_types("self", "assigned") == "assigned"
    assert catalog.merge_scope_types("dept", "dept_and_child") == "dept_and_child"
    assert catalog.merge_scope_types("dept_and_child", "all") == "all"


def test_no_delivery_project_resource():
    assert "delivery.project" not in catalog.RESOURCE_CODES
    assert "delivery.project" not in catalog.PERMISSION_TO_RESOURCE.values()
    assert "delivery.project" not in catalog.RESOURCE_SCOPE_ANCHOR


def test_every_business_permission_maps_to_resource():
    unmapped = [
        code
        for code in catalog.BUSINESS_PERMISSIONS
        if catalog.permission_to_resource(code) is None
    ]
    assert unmapped == []


def test_system_permissions_have_no_data_scope_resource():
    for code in catalog.SYSTEM_PERMISSIONS:
        assert code in ALL_PERMISSION_CODES
        assert catalog.permission_to_resource(code) is None
        assert catalog.is_system_permission(code)


def test_permission_mapping_targets_known_resources():
    for perm, resource in catalog.PERMISSION_TO_RESOURCE.items():
        assert perm in ALL_PERMISSION_CODES
        assert resource in catalog.RESOURCE_CODES
        assert resource in catalog.RESOURCE_SCOPE_ANCHOR


def test_every_resource_has_anchor():
    for code in catalog.RESOURCE_CODES:
        assert code in catalog.RESOURCE_SCOPE_ANCHOR


def test_delivery_resources_use_client_anchor():
    for code in catalog.DELIVERY_RESOURCE_CODES:
        anchor = catalog.RESOURCE_SCOPE_ANCHOR[code]
        assert anchor.inherit_via_client is True
        assert anchor.client_fk == catalog.CLIENT_FK
        assert anchor.scope_mode == "delivery"
        owner_col, dept_col, assigned_col = catalog.client_scope_columns("delivery")
        assert owner_col == catalog.CLIENT_DELIVERY_OWNER_COL
        assert dept_col == catalog.CLIENT_DELIVERY_DEPT_COL
        assert assigned_col is None


def test_crm_client_anchor_is_direct_on_clients_table():
    anchor = catalog.RESOURCE_SCOPE_ANCHOR[catalog.RESOURCE_CRM_CLIENT]
    assert anchor.primary_table == catalog.CLIENT_TABLE
    assert anchor.inherit_via_client is False
    assert anchor.scope_mode == "sales"
    assert anchor.owner_user_col == catalog.CLIENT_SALES_OWNER_COL


def test_handoff_review_maps_to_handoff_resource():
    assert catalog.permission_to_resource("delivery.handoff.review") == catalog.RESOURCE_DELIVERY_HANDOFF


def test_file_resource_inherits_parent():
    anchor = catalog.RESOURCE_SCOPE_ANCHOR[catalog.RESOURCE_FILE]
    assert anchor.scope_mode == "inherit_parent"
    assert anchor.inherit_via_client is True
