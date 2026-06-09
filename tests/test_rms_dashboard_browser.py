"""Browser smoke test: RMS dashboard must mount and show key labels."""
from __future__ import annotations

import importlib
import socket
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import sync_playwright

from tests.test_rms_phase2_mvp import _enable_delivery_rms_mvp, _enable_sales_rms_jobs_write


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def rms_dashboard_live_url(_test_env):
    mp = pytest.MonkeyPatch()
    mp.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    _enable_sales_rms_jobs_write(crm_main.engine)
    _enable_delivery_rms_mvp(crm_main.engine)

    port = _free_port()
    import uvicorn

    config = uvicorn.Config(
        crm_main.app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                break
        except OSError:
            time.sleep(0.05)
    else:
        mp.undo()
        pytest.fail("uvicorn did not start in time")

    url = f"http://127.0.0.1:{port}"
    yield url

    server.should_exit = True
    thread.join(timeout=5)
    mp.undo()


def _login_admin(page, base_url: str) -> None:
    page.goto(base_url + "/rms/dashboard", wait_until="domcontentloaded")
    if page.locator("#login-user").is_visible():
        page.fill("#login-user", "admin")
        page.fill("#login-pwd", "admin123")
        page.click("#login-btn")
    page.locator("#main-shell:not(.hidden)").wait_for(state="attached", timeout=15000)


def _chromium_launchable() -> bool:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception as exc:
        if "Executable doesn't exist" in str(exc):
            return False
        raise


def test_rms_dashboard_browser_smoke(rms_dashboard_live_url):
    """Real browser: Vue mount + dashboard API; must not be a blank page."""
    if not _chromium_launchable():
        pytest.skip("playwright chromium not installed; run: playwright install")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            _login_admin(page, rms_dashboard_live_url)

            page.locator("#rms-dashboard-app.dash-root").wait_for(state="visible", timeout=15000)
            page.get_by_role("button", name="招聘Dashboard").wait_for(state="visible", timeout=10000)
            page.get_by_role("button", name="总览").wait_for(state="visible", timeout=10000)
            page.get_by_text("需求总数", exact=True).wait_for(state="visible", timeout=15000)

            html = page.locator("#rms-dashboard-app").inner_html() or ""
            assert "crm-table" not in html
            assert page.get_by_text("open 岗位", exact=False).count() == 0
        finally:
            browser.close()
