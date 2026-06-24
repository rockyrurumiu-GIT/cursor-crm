from __future__ import annotations

from typing import Any, Dict, List, Set

from auth.permissions import ALL_PERMISSION_CODES

# Display matrix: maps UI columns to underlying permission codes.
_MATRIX_ROWS: List[Dict[str, Any]] = [
    {
        "module": "customers",
        "module_label": "客户",
        "label": "客户管理",
        "read": ["crm.clients.read"],
        "write": ["crm.clients.write"],
        "delete": ["crm.clients.delete"],
        "import_export": ["crm.clients.write"],
        "approve": [],
    },
    {
        "module": "opportunity",
        "module_label": "商机",
        "label": "商机管理",
        "read": ["crm.opportunities.read"],
        "write": ["crm.opportunities.write"],
        "delete": ["crm.opportunities.delete"],
        "import_export": ["crm.opportunities.write"],
        "approve": [],
    },
    {
        "module": "contracts",
        "module_label": "合同",
        "label": "合同管理",
        "read": ["crm.contracts.read"],
        "write": ["crm.contracts.write"],
        "delete": ["crm.contracts.delete"],
        "import_export": ["crm.contracts.download"],
        "approve": [],
    },
    {
        "module": "customers",
        "module_label": "客户",
        "label": "联系人",
        "read": ["crm.contacts.read"],
        "write": ["crm.contacts.write"],
        "delete": ["crm.contacts.delete"],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "customers",
        "module_label": "客户",
        "label": "客户拜访",
        "read": ["crm.visits.read"],
        "write": ["crm.visits.write"],
        "delete": ["crm.visits.delete"],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "delivery",
        "module_label": "交付",
        "label": "花名册",
        "read": ["delivery.roster.read"],
        "write": ["delivery.roster.write"],
        "delete": ["delivery.roster.delete"],
        "import_export": ["delivery.roster.write"],
        "approve": [],
    },
    {
        "module": "handbook",
        "module_label": "手册",
        "label": "交付手册",
        "read": ["delivery.handbook.read"],
        "write": ["delivery.handbook.write"],
        "delete": ["delivery.handbook.delete"],
        "import_export": ["delivery.handbook.write"],
        "approve": [],
    },
    {
        "module": "delivery",
        "module_label": "交付",
        "label": "员工文件",
        "read": ["delivery.employee_files.read"],
        "write": ["delivery.employee_files.write"],
        "delete": ["delivery.employee_files.delete"],
        "import_export": ["delivery.employee_files.write"],
        "approve": [],
    },
    {
        "module": "delivery",
        "module_label": "交付",
        "label": "访谈记录",
        "read": ["delivery.interviews.read"],
        "write": ["delivery.interviews.write"],
        "delete": ["delivery.interviews.delete"],
        "import_export": ["delivery.interviews.write"],
        "approve": [],
    },
    {
        "module": "delivery",
        "module_label": "交付",
        "label": "结算台账",
        "read": ["delivery.settlement.read"],
        "write": ["delivery.settlement.write"],
        "delete": ["delivery.settlement.delete"],
        "import_export": ["delivery.settlement.write"],
        "approve": [],
    },
    {
        "module": "delivery",
        "module_label": "交付",
        "label": "项目交接",
        "read": ["delivery.handoff.read"],
        "write": ["delivery.handoff.write"],
        "delete": [],
        "import_export": [],
        "approve": ["delivery.handoff.review"],
    },
    {
        "module": "rms",
        "module_label": "招聘",
        "label": "招聘岗位",
        "read": ["rms.jobs.read"],
        "write": ["rms.jobs.write"],
        "delete": ["rms.jobs.delete"],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "rms",
        "module_label": "招聘",
        "label": "候选人",
        "read": ["rms.candidates.read"],
        "write": ["rms.candidates.write"],
        "delete": ["rms.candidates.delete"],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "rms",
        "module_label": "招聘",
        "label": "候选人联系方式",
        "read": ["rms.contacts.view"],
        "write": [],
        "delete": [],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "rms",
        "module_label": "招聘",
        "label": "简历",
        "read": ["rms.resumes.read"],
        "write": [],
        "delete": [],
        "import_export": ["rms.resumes.download"],
        "approve": [],
    },
    {
        "module": "rms",
        "module_label": "招聘",
        "label": "推荐记录",
        "read": ["rms.applications.read"],
        "write": ["rms.applications.write"],
        "delete": ["rms.applications.delete"],
        "import_export": [],
        "approve": ["rms.offer_approval.submit"],
    },
    {
        "module": "rms",
        "module_label": "招聘",
        "label": "AI 智能匹配",
        "read": [],
        "write": [],
        "delete": [],
        "import_export": [],
        "approve": ["rms.matching.run"],
    },
    {
        "module": "rms",
        "module_label": "招聘",
        "label": "招聘分析",
        "read": ["rms.analytics.read"],
        "write": [],
        "delete": [],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "dashboards",
        "module_label": "仪表盘",
        "label": "仪表盘搭建",
        "read": ["dashboard.read"],
        "write": ["dashboard.write"],
        "delete": ["dashboard.delete"],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "tools",
        "module_label": "工具",
        "label": "毛利测算器",
        "read": ["tools.gm_calc.read"],
        "write": [],
        "delete": [],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "materials",
        "module_label": "数字资产",
        "label": "公司资料库-全部资料",
        "read": ["materials.read"],
        "write": ["materials.write"],
        "delete": ["materials.delete"],
        "import_export": ["materials.download"],
        "approve": [],
    },
    {
        "module": "materials",
        "module_label": "数字资产",
        "label": "公司资料库-公开资料查看",
        "read": ["materials.public.read"],
        "write": [],
        "delete": [],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "materials",
        "module_label": "数字资产",
        "label": "公司资料库-公开资料预览",
        "read": ["materials.public.preview"],
        "write": [],
        "delete": [],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "materials",
        "module_label": "数字资产",
        "label": "公司资料库-公开资料下载",
        "read": [],
        "write": [],
        "delete": [],
        "import_export": ["materials.public.download"],
        "approve": [],
    },
    {
        "module": "materials",
        "module_label": "数字资产",
        "label": "公司资料库-内部资料查看",
        "read": ["materials.internal.read"],
        "write": [],
        "delete": [],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "materials",
        "module_label": "数字资产",
        "label": "公司资料库-内部资料预览",
        "read": ["materials.internal.preview"],
        "write": [],
        "delete": [],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "materials",
        "module_label": "数字资产",
        "label": "公司资料库-内部资料下载",
        "read": [],
        "write": [],
        "delete": [],
        "import_export": ["materials.internal.download"],
        "approve": [],
    },
    {
        "module": "system",
        "module_label": "系统",
        "label": "用户管理",
        "read": ["system.users.manage"],
        "write": ["system.users.manage"],
        "delete": ["system.users.delete"],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "system",
        "module_label": "系统",
        "label": "角色与权限",
        "read": ["system.roles.manage"],
        "write": ["system.roles.manage"],
        "delete": ["system.roles.delete"],
        "import_export": [],
        "approve": [],
    },
    {
        "module": "system",
        "module_label": "系统",
        "label": "审计日志",
        "read": ["system.audit.read"],
        "write": [],
        "delete": [],
        "import_export": [],
        "approve": [],
    },
]

_COLUMN_KEYS = ("read", "write", "delete", "import_export", "approve")
_COLUMN_LABELS = {
    "read": "查看",
    "write": "新增/编辑",
    "delete": "删除",
    "import_export": "导入导出",
    "approve": "审批",
}


def _codes_for_row(row: dict) -> Set[str]:
    codes: Set[str] = set()
    for col in _COLUMN_KEYS:
        for c in row.get(col) or []:
            if c in ALL_PERMISSION_CODES:
                codes.add(c)
    return codes


def permission_codes_from_matrix_selection(selected: Dict[str, Dict[str, bool]]) -> List[str]:
    """selected[row_key][column] -> bool; returns deduped permission codes."""
    out: Set[str] = set()
    for row in _MATRIX_ROWS:
        key = row["label"]
        cols = selected.get(key) or {}
        for col in _COLUMN_KEYS:
            if cols.get(col):
                for code in row.get(col) or []:
                    out.add(code)
    return sorted(out)


def build_matrix_for_role(granted: Set[str]) -> dict:
    modules: Dict[str, dict] = {}
    for row in _MATRIX_ROWS:
        mod_key = row["module"]
        if mod_key not in modules:
            modules[mod_key] = {
                "key": mod_key,
                "label": row["module_label"],
                "rows": [],
            }
        cells = {}
        col_codes_map: Dict[str, List[str]] = {}
        codes: List[str] = []
        for col in _COLUMN_KEYS:
            col_codes = [c for c in (row.get(col) or []) if c in ALL_PERMISSION_CODES]
            col_codes_map[col] = col_codes
            cells[col] = any(c in granted for c in col_codes) if col_codes else False
            codes.extend(col_codes)
        modules[mod_key]["rows"].append({
            "key": row["label"],
            "label": row["label"],
            "cells": cells,
            "col_codes": col_codes_map,
            "codes": sorted(set(codes)),
        })
    return {
        "columns": [{"key": k, "label": _COLUMN_LABELS[k]} for k in _COLUMN_KEYS],
        "modules": list(modules.values()),
    }


def matrix_template() -> dict:
    return build_matrix_for_role(set())
