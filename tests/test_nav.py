"""Navigation template structure tests."""
from __future__ import annotations

import re
from pathlib import Path

NAV_PATH = Path(__file__).resolve().parent.parent / "templates" / "partials" / "nav.html"


def _nav_html() -> str:
    return NAV_PATH.read_text(encoding="utf-8")


def test_dashboard_nav_moved_under_customers():
    nav = _nav_html()
    assert 'class="nav-trigger" href="/dashboards"' not in nav
    assert 'class="gh-mega-link" href="/dashboards" data-crm-nav-perm="dashboard.read"' in nav
    assert re.search(r'data-crm-nav-any="[^"]*dashboard\.read', nav)
