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


def test_gm_calc_nav_requires_tools_permission():
    nav = _nav_html()
    assert re.search(r'data-crm-nav-any="[^"]*tools\.gm_calc\.read', nav)
    assert 'href="/tools/calc" data-crm-nav-perm="tools.gm_calc.read">毛利测算器' in nav


def test_customer_nav_child_permissions():
    nav = _nav_html()
    assert re.search(r'data-crm-nav-any="[^"]*crm\.contacts\.read', nav)
    assert 'href="/customers" data-crm-nav-perm="crm.clients.read"' in nav
    assert 'href="/contacts/all" data-crm-nav-perm="crm.contacts.read"' in nav
    assert 'href="/customers/visits" data-crm-nav-perm="crm.visits.read"' in nav


def test_rms_nav_entry():
    nav = _nav_html()
    assert 'href="/rms"' in nav
    assert 'data-crm-nav-any="rms.jobs.read,rms.analytics.read,rms.candidates.read"' in nav
    assert 'class="nav-trigger cursor-default">招聘' in nav
    assert 'href="/rms" data-crm-nav-perm="rms.jobs.read">需求&amp;人才库' in nav
    assert "帮助文件" in nav
    assert 'href="/rms/import-help"' in nav
    assert 'data-crm-nav-perm="rms.candidates.read">批量导入帮助' in nav


def test_delivery_nav_structure():
    nav = _nav_html()
    assert "综合管理" in nav
    assert "需求管理" not in nav
    roster_idx = nav.index('href="/customers/roster"')
    requirements_idx = nav.index('href="/delivery/requirements"')
    pipeline_idx = nav.index('href="/delivery/pipeline"')
    assert roster_idx < requirements_idx < pipeline_idx
    employee_files_idx = nav.index('href="/delivery/employee_files"')
    interviews_idx = nav.index('href="/delivery/interviews"')
    turnover_idx = nav.index('href="/delivery/turnover"')
    assert employee_files_idx < interviews_idx < turnover_idx
    assert "员工文件" in nav


def test_home_digital_assets_nav():
    nav = _nav_html()
    assert 'data-crm-nav-any="crm.clients.read,materials.read"' in nav
    assert "数字资产" in nav
    assert 'href="/materials" data-crm-nav-perm="materials.read">公司资料库' in nav
    assert 'href="/home/funnel" data-crm-nav-perm="crm.clients.read"' in nav
    assert 'href="/home/trash" data-crm-nav-perm="crm.clients.read"' in nav
    assert 'href="/home" data-crm-nav-perm="crm.clients.read"' in nav
    materials_idx = nav.index('href="/materials"')
    funnel_idx = nav.index('href="/home/funnel"')
    assert materials_idx > funnel_idx
