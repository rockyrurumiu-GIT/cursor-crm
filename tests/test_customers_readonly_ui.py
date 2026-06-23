"""Customer readonly UI permission guard structure tests."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CUSTOMERS_HTML = ROOT / "templates" / "pages" / "customers.html"
CUSTOMERS_NEW_HTML = ROOT / "templates" / "pages" / "customers_new.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_customers_list_hides_client_write_controls():
    html = _read(CUSTOMERS_HTML)

    assert "const meLoaded = ref(false);" in html
    assert "if (!meLoaded.value) return false;" in html
    assert "const canWriteClients = computed" in html
    assert "const canDeleteClients = computed" in html
    assert "const canReadContacts = computed" in html
    assert "const canReadVisits = computed" in html
    assert "const canWriteVisits = computed" in html
    assert "const canExportClients = computed" in html
    assert "const canOpenHandoff = computed" in html
    assert "const canReviewHandoff = computed" in html
    assert "!!me.value.is_super" in html
    assert "(me.value.roles || []).includes('SUPER_ADMIN')" in html
    assert "hasPermission('crm.clients.write')" in html
    assert "hasPermission('crm.clients.delete')" in html
    assert "hasPermission('crm.contacts.read')" in html
    assert "hasPermission('crm.visits.read')" in html
    assert "hasPermission('crm.visits.write')" in html
    assert "hasPermission('delivery.handoff.read')" in html
    assert "hasPermission('delivery.handoff.review')" in html

    assert 'v-if="canWriteClients"' in html
    assert '@click="openCreateClient"' in html
    assert 'aria-label="新增客户"' in html
    assert 'v-if="canReviewHandoff"' in html
    assert 'href="/customers/reviews"' in html
    assert 'v-if="canExportClients"' in html
    assert '@click="exportCSV"' in html
    assert 'v-if="canWriteClients"' in html
    assert '@click="openEditClient(c)"' in html
    assert 'v-if="canDeleteClients"' in html
    assert '@click="confirmDelete(c)"' in html
    assert '@click="openEditClient(selectedClient)"' in html
    assert ':disabled="!canWriteClients"' in html
    assert 'v-if="canWriteClients" type="button" @click="updateClient(selectedClient)"' in html
    assert 'v-if="canReadContacts" href="/contacts/all"' in html


def test_customers_list_handoff_badge_is_conditionally_clickable():
    html = _read(CUSTOMERS_HTML)

    assert 'v-if="canOpenHandoff"' in html
    assert "<span v-else" in html
    assert ':class="handoffBadge(resolveHandoffStatus(c.id))"' in html
    assert "const requireHandoffAccess = () =>" in html


def test_customers_list_guards_visit_write_controls():
    html = _read(CUSTOMERS_HTML)

    assert 'v-if="canReadVisits" class="min-h-0' in html
    assert "无客户拜访查看权限" in html
    assert 'v-if="canWriteVisits" type="button" @click="openAddVisit"' in html
    assert "const requireClientWrite = () =>" in html
    assert "const requireVisitWrite = () =>" in html
    assert "const requireClientExport = () =>" in html
    assert "const openAddVisit = () =>" in html
    assert "if (!requireVisitWrite()) return;" in html
    assert "@click=\"showAddVisit=true\"" not in html

    returned = html[html.index("return {") :]
    assert "canWriteClients" in returned
    assert "canReadContacts" in returned
    assert "canReadVisits" in returned
    assert "canWriteVisits" in returned
    assert "canExportClients" in returned
    assert "canOpenHandoff" in returned
    assert "canReviewHandoff" in returned
    assert "openAddVisit" in returned
    assert "requireClientWrite" in returned
    assert "requireVisitWrite" in returned
    assert "requireClientExport" in returned
    assert "requireHandoffAccess" in returned


def test_customers_new_has_frontend_write_fallback_guard():
    html = _read(CUSTOMERS_NEW_HTML)

    assert "async function ensureCanWriteClient()" in html
    assert "fetch('/api/me'" in html
    assert "window.location.href = '/customers';" in html
    assert "无客户写入权限" in html
    assert "disableFormForNoWrite();" in html
    assert "Array.from(form.elements).forEach" in html
    assert "if (!(await ensureCanWriteClient())) return;" in html
    assert "await loadClient();" in html
