"""Dashboard builder API routes."""
from __future__ import annotations

from typing import Any, Callable, Dict

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from schemas.dashboards import build_metadata
from services import dashboards as dash_svc


class DashboardBody(BaseModel):
    name: str = ""
    description: str = ""
    layout_json: dict = Field(default_factory=dict)


class TabBody(BaseModel):
    name: str = ""
    sort_order: int = 0


class WidgetBody(BaseModel):
    title: str = ""
    widget_type: str = ""
    source_key: str = ""
    config: dict = Field(default_factory=dict)
    x: int = 0
    y: int = 0
    w: int = 4
    h: int = 3
    sort_order: int = 0


def register_dashboard_routes(
    app,
    *,
    get_db: Callable,
    page_renderer: Callable,
    DashboardDashboard,
    DashboardTab,
    DashboardWidget,
    Client,
    Contact,
    Opportunity,
    VisitRecord,
    HandoffRequest,
    DeliveryPipelineEntry,
    RosterEntry,
    DeliverySettlementEntry,
    DeliveryInterviewEntry,
):
    models: Dict[str, Any] = {
        "Client": Client,
        "Contact": Contact,
        "Opportunity": Opportunity,
        "VisitRecord": VisitRecord,
        "HandoffRequest": HandoffRequest,
        "DeliveryPipelineEntry": DeliveryPipelineEntry,
        "RosterEntry": RosterEntry,
        "DeliverySettlementEntry": DeliverySettlementEntry,
        "DeliveryInterviewEntry": DeliveryInterviewEntry,
    }

    @app.get("/dashboards", response_class=HTMLResponse)
    async def page_dashboards(request: Request):
        return page_renderer("pages/dashboards.html", request)

    @app.get("/api/dashboards")
    async def api_list_dashboards(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.read")),
    ):
        return dash_svc.list_dashboards(db, DashboardDashboard, DashboardTab, DashboardWidget)

    @app.get("/api/dashboards/{dashboard_id}")
    async def api_get_dashboard(
        dashboard_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.read")),
    ):
        return dash_svc.get_dashboard(db, dashboard_id, DashboardDashboard, DashboardTab, DashboardWidget)

    @app.post("/api/dashboards")
    async def api_create_dashboard(
        body: DashboardBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.write")),
    ):
        return dash_svc.create_dashboard(db, body.model_dump(), ctx, DashboardDashboard)

    @app.put("/api/dashboards/{dashboard_id}")
    async def api_update_dashboard(
        dashboard_id: int,
        body: DashboardBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.write")),
    ):
        return dash_svc.update_dashboard(
            db, dashboard_id, body.model_dump(), DashboardDashboard, DashboardTab, DashboardWidget
        )

    @app.delete("/api/dashboards/{dashboard_id}")
    async def api_delete_dashboard(
        dashboard_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.write")),
    ):
        return dash_svc.delete_dashboard(db, dashboard_id, DashboardDashboard, DashboardTab, DashboardWidget)

    @app.post("/api/dashboards/{dashboard_id}/tabs")
    async def api_create_tab(
        dashboard_id: int,
        body: TabBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.write")),
    ):
        return dash_svc.create_tab(db, dashboard_id, body.model_dump(), DashboardDashboard, DashboardTab)

    @app.put("/api/dashboard-tabs/{tab_id}")
    async def api_update_tab(
        tab_id: int,
        body: TabBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.write")),
    ):
        return dash_svc.update_tab(db, tab_id, body.model_dump(), DashboardTab)

    @app.delete("/api/dashboard-tabs/{tab_id}")
    async def api_delete_tab(
        tab_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.write")),
    ):
        return dash_svc.delete_tab(db, tab_id, DashboardTab, DashboardWidget)

    @app.post("/api/dashboard-tabs/{tab_id}/widgets")
    async def api_create_widget(
        tab_id: int,
        body: WidgetBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.write")),
    ):
        return dash_svc.create_widget(db, tab_id, body.model_dump(), DashboardTab, DashboardWidget)

    @app.put("/api/dashboard-widgets/{widget_id}")
    async def api_update_widget(
        widget_id: int,
        body: WidgetBody,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.write")),
    ):
        return dash_svc.update_widget(db, widget_id, body.model_dump(), DashboardWidget)

    @app.delete("/api/dashboard-widgets/{widget_id}")
    async def api_delete_widget(
        widget_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.write")),
    ):
        return dash_svc.delete_widget(db, widget_id, DashboardWidget)

    @app.get("/api/dashboard-widgets/{widget_id}/data")
    async def api_widget_data(
        widget_id: int,
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.read")),
    ):
        return dash_svc.get_widget_data(db, ctx, widget_id, models, DashboardWidget)

    @app.get("/api/dashboard-metadata")
    async def api_dashboard_metadata(
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.read")),
    ):
        return build_metadata()

    @app.get("/api/dashboard/roster-clients")
    async def api_dashboard_roster_clients(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("dashboard.read")),
    ):
        return dash_svc.list_roster_clients(db, ctx, models)
