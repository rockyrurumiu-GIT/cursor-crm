"""Navigation template structure tests."""
from __future__ import annotations

import re
from pathlib import Path

NAV_PATH = Path(__file__).resolve().parent.parent / "templates" / "partials" / "nav.html"


def _nav_html() -> str:
    return NAV_PATH.read_text(encoding="utf-8")


def test_dashboard_nav_under_company():
    nav = _nav_html()
    assert 'class="nav-trigger" href="/dashboards"' not in nav
    home_section = nav.split("<!-- 首页 -->", 1)[1].split("<!-- 客户（含费用折算器子项） -->", 1)[0]
    assert 'class="gh-mega-link" href="/dashboards" data-crm-nav-perm="dashboard.read"' in home_section
    assert re.search(r'data-crm-nav-any="[^"]*dashboard\.read', nav)
    customer_section = nav.split("<!-- 客户（含费用折算器子项） -->", 1)[1].split("<!-- 商机", 1)[0]
    assert 'href="/dashboards"' not in customer_section


def test_gm_calc_nav_under_help_center():
    nav = _nav_html()
    help_section = nav.split('class="nav-trigger cursor-default">帮助中心', 1)[1]
    assert re.search(r'data-crm-nav-any="[^"]*tools\.gm_calc\.read', nav)
    assert 'href="/tools/calc" data-crm-nav-perm="tools.gm_calc.read">GM测算器' in help_section
    customer_section = nav.split("<!-- 客户（含费用折算器子项） -->", 1)[1].split("<!-- 商机", 1)[0]
    assert 'href="/tools/calc"' not in customer_section


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
    rms_section = nav.split('class="nav-trigger cursor-default">招聘', 1)[1].split('class="nav-trigger cursor-default">权限中心', 1)[0]
    assert "帮助文件" not in rms_section
    help_section = nav.split('class="nav-trigger cursor-default">帮助中心', 1)[1]
    assert 'href="/home/trash" data-crm-nav-perm="crm.clients.read">回收站与空间' in help_section
    assert 'href="/rms/import-help"' in help_section
    assert 'data-crm-nav-perm="rms.candidates.read">帮助文件-如何批量导入候选人' in help_section
    assert 'data-crm-nav-perm="rms.applications.write">帮助文件-如何分配非本人需求' in help_section
    assert 'data-crm-nav-perm="tools.gm_calc.read">GM测算器' in help_section
    gm_idx = help_section.index('href="/tools/calc"')
    trash_idx = help_section.index('href="/home/trash"')
    assert gm_idx < trash_idx
    system_section = nav.split('class="nav-trigger cursor-default">权限中心', 1)[1].split('class="nav-trigger cursor-default">帮助中心', 1)[0]
    assert 'href="/system/users"' in system_section
    assert 'href="/home/trash"' not in system_section


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
    assert 'data-crm-nav-any="crm.clients.read,materials.read,materials.public.read,materials.internal.read,dashboard.read"' in nav
    assert "数字资产" in nav
    assert 'href="/materials" data-crm-nav-any="materials.read,materials.public.read,materials.internal.read">公司资料库' in nav
    assert 'href="/contracts">合同管理' in nav
    assert 'href="/dashboards" data-crm-nav-perm="dashboard.read">仪表盘' in nav
    customer_section = nav.split("<!-- 客户（含费用折算器子项） -->", 1)[1].split("<!-- 商机", 1)[0]
    assert 'gh-mega-col-h">合同管理' not in customer_section
    home_section = nav.split("<!-- 首页 -->", 1)[1].split("<!-- 客户（含费用折算器子项） -->", 1)[0]
    assert 'href="/home/funnel"' not in home_section
    assert 'href="/home/trash"' not in home_section
    system_section = nav.split('class="nav-trigger cursor-default">权限中心', 1)[1].split('class="nav-trigger cursor-default">帮助中心', 1)[0]
    assert 'href="/home/trash"' not in system_section
    assert 'href="/home" data-crm-nav-perm="crm.clients.read"' not in nav
    assert '首页总览' not in nav
    materials_idx = nav.index('href="/materials"')
    contracts_idx = nav.index('href="/contracts"')
    assert contracts_idx > materials_idx


def test_funnel_nav_under_customers_last():
    nav = _nav_html()
    assert 'href="/home/funnel" data-crm-nav-perm="crm.clients.read">销售漏斗看板' in nav
    customer_section = nav.split("<!-- 客户（含费用折算器子项） -->", 1)[1].split("<!-- 商机", 1)[0]
    assert 'href="/tools/calc"' not in customer_section
    assert 'href="/dashboards"' not in customer_section
