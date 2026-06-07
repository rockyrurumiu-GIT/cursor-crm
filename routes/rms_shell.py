"""RMS shell: /rms page (jobs/candidates/applications tabs) and /api/rms/health.

Business UI lives in templates/pages/rms_index.html + static/js/pages/rms.js (Phase 2.5 MVP).
"""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse

from auth.deps import require_permission


def register_rms_shell_routes(app, *, page_renderer: Callable):
    @app.get("/rms", response_class=HTMLResponse)
    async def page_rms(
        request: Request,
        _user: str = Depends(require_permission("rms.jobs.read")),
    ):
        return page_renderer("pages/rms_index.html", request)

    @app.get("/rms/dashboard", response_class=HTMLResponse)
    async def page_rms_dashboard(
        request: Request,
        _user: str = Depends(require_permission("rms.analytics.read")),
    ):
        return page_renderer("pages/rms_dashboard.html", request)

    @app.get("/api/rms/health")
    async def api_rms_health(_user: str = Depends(require_permission("rms.jobs.read"))):
        return {"status": "ok", "phase": 2}
