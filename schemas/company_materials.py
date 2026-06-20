"""Company materials library constants and schemas."""
from __future__ import annotations

from typing import Dict, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

MATERIAL_ALLOWED_SUFFIXES: Set[str] = frozenset({
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".zip", ".jpg", ".jpeg", ".png",
})

MATERIAL_CATEGORIES: Dict[str, str] = {
    "business_license": "营业执照",
    "financial_report": "财务资料",
    "certification": "资质认证",
    "contract_template": "合同模板",
    "nda": "保密协议",
    "training": "培训材料",
    "company_profile": "公司介绍",
    "bidding": "投标材料",
    "other": "其他",
}

MATERIAL_CONFIDENTIALITY: Dict[str, str] = {
    "public": "公开",
    "internal": "内部",
    "confidential": "机密",
}

MATERIAL_STATUS: Dict[str, str] = {
    "active": "有效",
    "archived": "已归档",
}

MATERIAL_CATEGORY_SET = frozenset(MATERIAL_CATEGORIES.keys())
MATERIAL_CONFIDENTIALITY_SET = frozenset(MATERIAL_CONFIDENTIALITY.keys())
MATERIAL_STATUS_SET = frozenset(MATERIAL_STATUS.keys())


def category_label(code: str) -> str:
    return MATERIAL_CATEGORIES.get(str(code or "").strip(), str(code or ""))


def confidentiality_label(code: str) -> str:
    return MATERIAL_CONFIDENTIALITY.get(str(code or "").strip(), str(code or ""))


def status_label(code: str) -> str:
    return MATERIAL_STATUS.get(str(code or "").strip(), str(code or ""))


def normalize_category(raw: str) -> str:
    v = str(raw or "").strip()
    if v not in MATERIAL_CATEGORY_SET:
        raise ValueError("无效分类")
    return v


def normalize_confidentiality(raw: str) -> str:
    v = str(raw or "").strip()
    if v not in MATERIAL_CONFIDENTIALITY_SET:
        raise ValueError("无效保密等级")
    return v


def normalize_status(raw: str, *, default: str = "active") -> str:
    v = str(raw or "").strip().lower()
    if not v:
        return default
    if v not in MATERIAL_STATUS_SET:
        raise ValueError("无效状态")
    return v


class MaterialUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    confidentiality: Optional[str] = None
    owner_dept_id: Optional[int] = Field(default=None)
    expires_at: Optional[str] = None
