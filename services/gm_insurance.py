"""GM calculator: social insurance location rates (seed + helpers)."""
from __future__ import annotations

import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def ensure_social_insurance_schema(engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS social_insurance_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL UNIQUE,
                social_insurance REAL NOT NULL DEFAULT 0,
                housing_fund REAL NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT
            )
            """
        )


def row_to_dict(row) -> Dict[str, Any]:
    return {
        "id": row.id,
        "location": row.location,
        "social_insurance": float(row.social_insurance or 0),
        "housing_fund": float(row.housing_fund or 0),
        "sort_order": int(row.sort_order or 0),
        "is_active": bool(row.is_active),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _load_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out = []
    for si in root.findall("m:si", _NS):
        parts = []
        for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"):
            if t.text:
                parts.append(t.text)
        out.append("".join(parts))
    return out


def _cell_value(c, sst: List[str]):
    t = c.get("t")
    v = c.find("m:v", _NS)
    if v is None or v.text is None:
        return None
    if t == "s":
        return sst[int(v.text)]
    try:
        return float(v.text)
    except ValueError:
        return v.text


def parse_insurance_rows_from_xlsx(xlsx_path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with zipfile.ZipFile(xlsx_path) as zf:
        sst = _load_shared_strings(zf)
        root = ET.fromstring(zf.read("xl/worksheets/sheet2.xml"))
        order = 0
        for row_el in root.findall(".//m:sheetData/m:row", _NS):
            rnum = int(row_el.get("r", 0))
            if rnum < 2:
                continue
            loc = soc = hf = None
            for c in row_el.findall("m:c", _NS):
                ref = c.get("r", "")
                if ref.startswith("A"):
                    loc = _cell_value(c, sst)
                elif ref.startswith("C"):
                    soc = _cell_value(c, sst)
                elif ref.startswith("D"):
                    hf = _cell_value(c, sst)
            if not loc or not isinstance(loc, str):
                continue
            loc = loc.strip()
            if not loc or loc.startswith("社保") or loc.startswith("（"):
                continue
            order += 1
            try:
                social = float(soc or 0)
            except (TypeError, ValueError):
                social = 0.0
            try:
                housing = float(hf or 0)
            except (TypeError, ValueError):
                housing = 0.0
            rows.append({
                "location": loc,
                "social_insurance": social,
                "housing_fund": housing,
                "sort_order": order,
                "is_active": True,
            })
    return rows


def seed_social_insurance_locations(
    db: Session,
    model,
    *,
    xlsx_path: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> int:
    if db.query(model).count() > 0:
        return 0
    base = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = xlsx_path or os.path.join(base, "毛利测算表2026.xlsx")
    if not os.path.isfile(path):
        return 0
    payload = parse_insurance_rows_from_xlsx(path)
    now = datetime.now()
    for item in payload:
        db.add(
            model(
                location=item["location"],
                social_insurance=item["social_insurance"],
                housing_fund=item["housing_fund"],
                sort_order=item["sort_order"],
                is_active=True,
                updated_at=now,
            )
        )
    db.commit()
    return len(payload)
