"""Delivery employee file constants."""
from __future__ import annotations

EMPLOYEE_FILE_ALLOWED_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".zip",
    ".rar",
}

EMPLOYEE_FILE_STATUS_SET = frozenset({"draft", "published", "deprecated"})

EMPLOYEE_FILE_DOCUMENT_TYPES = frozenset({
    "劳动合同",
    "入职材料",
    "离职材料",
    "员工证件",
    "其他",
})

LABOR_CONTRACT_DOCUMENT_TYPE = "劳动合同"
