"""GM calculator config: insurance locations API."""
from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.deps import require_permission
from services.gm_insurance import row_to_dict


class InsuranceLocationBody(BaseModel):
    location: str = Field(..., min_length=1, max_length=64)
    social_insurance: float = Field(..., ge=0)
    housing_fund: float = Field(..., ge=0)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True


class InsuranceLocationUpdateBody(BaseModel):
    location: Optional[str] = Field(default=None, min_length=1, max_length=64)
    social_insurance: Optional[float] = Field(default=None, ge=0)
    housing_fund: Optional[float] = Field(default=None, ge=0)
    sort_order: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


def register_gm_config_routes(app, *, get_db: Callable, SocialInsuranceLocation):
    @app.get("/api/gm/insurance-locations")
    async def api_gm_insurance_locations(
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("tools.gm_calc.read")),
    ):
        rows = (
            db.query(SocialInsuranceLocation)
            .filter(SocialInsuranceLocation.is_active.is_(True))
            .order_by(SocialInsuranceLocation.sort_order, SocialInsuranceLocation.id)
            .all()
        )
        return [row_to_dict(r) for r in rows]

    @app.get("/api/system/insurance-locations")
    async def api_system_insurance_locations_list(
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("system.users.manage")),
    ):
        rows = (
            db.query(SocialInsuranceLocation)
            .order_by(SocialInsuranceLocation.sort_order, SocialInsuranceLocation.id)
            .all()
        )
        return [row_to_dict(r) for r in rows]

    @app.post("/api/system/insurance-locations")
    async def api_system_insurance_locations_create(
        body: InsuranceLocationBody,
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("system.users.manage")),
    ):
        loc = body.location.strip()
        if db.query(SocialInsuranceLocation).filter(SocialInsuranceLocation.location == loc).first():
            raise HTTPException(status_code=400, detail="参保地已存在")
        row = SocialInsuranceLocation(
            location=loc,
            social_insurance=body.social_insurance,
            housing_fund=body.housing_fund,
            sort_order=body.sort_order,
            is_active=body.is_active,
            updated_at=datetime.now(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row_to_dict(row)

    @app.put("/api/system/insurance-locations/{row_id}")
    async def api_system_insurance_locations_update(
        row_id: int,
        body: InsuranceLocationUpdateBody,
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("system.users.manage")),
    ):
        row = db.query(SocialInsuranceLocation).filter(SocialInsuranceLocation.id == row_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        if body.location is not None:
            loc = body.location.strip()
            dup = (
                db.query(SocialInsuranceLocation)
                .filter(SocialInsuranceLocation.location == loc, SocialInsuranceLocation.id != row_id)
                .first()
            )
            if dup:
                raise HTTPException(status_code=400, detail="参保地已存在")
            row.location = loc
        if body.social_insurance is not None:
            row.social_insurance = body.social_insurance
        if body.housing_fund is not None:
            row.housing_fund = body.housing_fund
        if body.sort_order is not None:
            row.sort_order = body.sort_order
        if body.is_active is not None:
            row.is_active = body.is_active
        row.updated_at = datetime.now()
        db.commit()
        db.refresh(row)
        return row_to_dict(row)

    @app.delete("/api/system/insurance-locations/{row_id}")
    async def api_system_insurance_locations_delete(
        row_id: int,
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("system.users.delete")),
    ):
        row = db.query(SocialInsuranceLocation).filter(SocialInsuranceLocation.id == row_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        row.is_active = False
        row.updated_at = datetime.now()
        db.commit()
        return {"ok": True, "id": row_id}
