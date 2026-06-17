"""RMS dashboard API routes."""
from __future__ import annotations

from typing import Any, Callable, Optional, Type

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from schemas.dashboards import RMS_ALLOWED_SOURCE_KEYS, build_rms_metadata
from services import dashboards as board_svc
from services import rms_dashboard as dash_svc


class RmsDashboardBody(BaseModel):
    name: str = ""
    description: str = ""
    layout_json: dict = Field(default_factory=dict)


class RmsTabBody(BaseModel):
    name: str = ""
    sort_order: int = 0
    layout_json: dict = Field(default_factory=dict)
    rms_template: Optional[str] = None


class RmsWidgetBody(BaseModel):
    title: str = ""
    widget_type: str = ""
    source_key: str = ""
    config: dict = Field(default_factory=dict)
    x: int = 0
    y: int = 0
    w: int = 4
    h: int = 3
    sort_order: int = 0


def register_rms_dashboard_routes(
    app,
    *,
    get_db: Callable,
    Client: Type[Any],
    Contact: Type[Any],
    Opportunity: Type[Any],
    VisitRecord: Type[Any],
    HandoffRequest: Type[Any],
    DeliveryPipelineEntry: Type[Any],
    RosterEntry: Type[Any],
    DeliverySettlementEntry: Type[Any],
    DeliveryInterviewEntry: Type[Any],
    RmsJob: Type[Any],
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    DashboardDashboard: Type[Any],
    DashboardTab: Type[Any],
    DashboardWidget: Type[Any],
):
    widget_models = {
        "Client": Client,
        "Contact": Contact,
        "Opportunity": Opportunity,
        "VisitRecord": VisitRecord,
        "HandoffRequest": HandoffRequest,
        "DeliveryPipelineEntry": DeliveryPipelineEntry,
        "RosterEntry": RosterEntry,
        "DeliverySettlementEntry": DeliverySettlementEntry,
        "DeliveryInterviewEntry": DeliveryInterviewEntry,
        "RmsJob": RmsJob,
        "RmsCandidate": RmsCandidate,
        "RmsApplication": RmsApplication,
    }
    def _assert_rms_tab(db: Session, tab_id: int) -> Any:
        tab = db.query(DashboardTab).filter(DashboardTab.id == tab_id).first()
        if not tab:
            raise HTTPException(status_code=404, detail="Tab 不存在")
        _assert_rms_board(db, tab.dashboard_id)
        return tab

    def _assert_rms_widget(db: Session, widget_id: int) -> Any:
        w = db.query(DashboardWidget).filter(DashboardWidget.id == widget_id).first()
        if not w:
            raise HTTPException(status_code=404, detail="Widget 不存在")
        _assert_rms_tab(db, w.tab_id)
        return w

    def _assert_rms_board(db: Session, dashboard_id: int) -> Any:
        d = db.query(DashboardDashboard).filter(DashboardDashboard.id == dashboard_id).first()
        if not d or (getattr(d, "scope", None) or "crm") != "rms":
            raise HTTPException(status_code=404, detail="RMS Dashboard 不存在")
        return d

    @app.get("/api/rms/dashboard-metadata")
    async def api_rms_dashboard_metadata(
        _user: str = Depends(require_permission("rms.analytics.read")),
    ):
        return build_rms_metadata()

    @app.get("/api/rms/dashboard")
    async def api_rms_dashboard(
        client_id: Optional[int] = None,
        job_id: Optional[int] = None,
        job_ids: Optional[str] = None,
        priority: Optional[str] = None,
        city: Optional[str] = None,
        sales_user_id: Optional[int] = None,
        delivery_user_id: Optional[int] = None,
        recruiter_user_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.analytics.read")),
    ):
        parsed_job_ids = None
        if job_ids is not None and str(job_ids).strip():
            try:
                parsed_job_ids = dash_svc.parse_job_ids(job_ids)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return dash_svc.compute_rms_dashboard(
            db,
            ctx,
            RmsApplication,
            RmsApplicationStatusHistory,
            RmsJob,
            Client,
            client_id=client_id,
            job_id=job_id,
            job_ids=parsed_job_ids,
            priority=priority,
            city=city,
            sales_user_id=sales_user_id,
            delivery_user_id=delivery_user_id,
            recruiter_user_id=recruiter_user_id,
            date_from=date_from,
            date_to=date_to,
        )

    @app.get("/api/rms/dashboard-boards")
    async def api_list_rms_boards(
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("rms.analytics.read")),
    ):
        return board_svc.list_dashboards(
            db, DashboardDashboard, DashboardTab, DashboardWidget, scope="rms"
        )

    @app.post("/api/rms/dashboard-boards")
    async def api_create_rms_board(
        body: RmsDashboardBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("dashboard.write")),
    ):
        payload = body.model_dump()
        payload["scope"] = "rms"
        return board_svc.create_dashboard(
            db,
            payload,
            ctx,
            DashboardDashboard,
            scope="rms",
            seed_rms_tabs=True,
            DashboardTab=DashboardTab,
            DashboardWidget=DashboardWidget,
        )

    @app.put("/api/rms/dashboard-boards/{dashboard_id}")
    async def api_update_rms_board(
        dashboard_id: int,
        body: RmsDashboardBody,
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("dashboard.write")),
    ):
        _assert_rms_board(db, dashboard_id)
        return board_svc.update_dashboard(
            db,
            dashboard_id,
            body.model_dump(),
            DashboardDashboard,
            DashboardTab,
            DashboardWidget,
        )

    @app.delete("/api/rms/dashboard-boards/{dashboard_id}")
    async def api_delete_rms_board(
        dashboard_id: int,
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("dashboard.delete")),
    ):
        _assert_rms_board(db, dashboard_id)
        return board_svc.delete_dashboard(
            db, dashboard_id, DashboardDashboard, DashboardTab, DashboardWidget
        )

    @app.post("/api/rms/dashboard-boards/{dashboard_id}/tabs")
    async def api_create_rms_tab(
        dashboard_id: int,
        body: RmsTabBody,
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("dashboard.write")),
    ):
        _assert_rms_board(db, dashboard_id)
        payload = body.model_dump()
        layout = dict(payload.get("layout_json") or {})
        if body.rms_template:
            layout["rms_template"] = body.rms_template
        payload["layout_json"] = layout
        tab = board_svc.create_tab(
            db, dashboard_id, payload, DashboardDashboard, DashboardTab
        )
        template = (body.rms_template or "").strip()
        if template and template != "empty":
            board_svc.seed_rms_tab_widgets(db, tab["id"], template, DashboardWidget)
            tab = board_svc.get_dashboard(
                db, dashboard_id, DashboardDashboard, DashboardTab, DashboardWidget
            )["tabs"][-1]
        return tab

    @app.get("/api/rms/dashboard-widgets/{widget_id}/data")
    async def api_rms_widget_data(
        widget_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.analytics.read")),
    ):
        _assert_rms_widget(db, widget_id)
        return board_svc.get_widget_data(db, ctx, widget_id, widget_models, DashboardWidget)

    @app.get("/api/rms/dashboard/roster-clients")
    async def api_rms_roster_clients(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        _user: str = Depends(require_permission("rms.analytics.read")),
    ):
        return board_svc.list_roster_clients(db, ctx, widget_models)

    @app.post("/api/rms/dashboard-tabs/{tab_id}/widgets")
    async def api_create_rms_widget(
        tab_id: int,
        body: RmsWidgetBody,
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("dashboard.write")),
    ):
        _assert_rms_tab(db, tab_id)
        result = board_svc.create_widget(
            db, tab_id, body.model_dump(), DashboardTab, DashboardWidget,
            allowed_source_keys=RMS_ALLOWED_SOURCE_KEYS,
        )
        board_svc.lock_rms_tab_widgets(db, tab_id, DashboardTab)
        return result

    @app.put("/api/rms/dashboard-widgets/{widget_id}")
    async def api_update_rms_widget(
        widget_id: int,
        body: RmsWidgetBody,
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("dashboard.write")),
    ):
        w = _assert_rms_widget(db, widget_id)
        result = board_svc.update_widget(
            db, widget_id, body.model_dump(), DashboardWidget,
            allowed_source_keys=RMS_ALLOWED_SOURCE_KEYS,
        )
        board_svc.lock_rms_tab_widgets(db, w.tab_id, DashboardTab)
        return result

    @app.delete("/api/rms/dashboard-widgets/{widget_id}")
    async def api_delete_rms_widget(
        widget_id: int,
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("dashboard.delete")),
    ):
        w = _assert_rms_widget(db, widget_id)
        tab_id = w.tab_id
        result = board_svc.delete_widget(db, widget_id, DashboardWidget)
        board_svc.lock_rms_tab_widgets(db, tab_id, DashboardTab)
        return result

    @app.delete("/api/rms/dashboard-tabs/{tab_id}")
    async def api_delete_rms_tab(
        tab_id: int,
        db: Session = Depends(get_db),
        _user: str = Depends(require_permission("dashboard.delete")),
    ):
        tab = db.query(DashboardTab).filter(DashboardTab.id == tab_id).first()
        if not tab:
            raise HTTPException(status_code=404, detail="Tab 不存在")
        _assert_rms_board(db, tab.dashboard_id)
        return board_svc.delete_tab(db, tab_id, DashboardTab, DashboardWidget)
