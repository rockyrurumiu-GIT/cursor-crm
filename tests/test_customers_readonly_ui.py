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
    assert "const canWriteVisits = computed" in html
    assert "!!me.value.is_super" in html
    assert "(me.value.roles || []).includes('SUPER_ADMIN')" in html
    assert "hasPermission('crm.clients.write')" in html
    assert "hasPermission('crm.visits.write')" in html

    assert 'v-if="canWriteClients" href="/customers/new"' in html
    assert 'v-if="canWriteClients" :href="`/customers/${c.id}/edit`"' in html
    assert 'v-if="canWriteClients" type="button" @click="confirmDelete(c)"' in html
    assert 'v-if="canWriteClients" :href="`/customers/${selectedClient.id}/edit`"' in html
    assert ':disabled="!canWriteClients"' in html
    assert 'v-if="canWriteClients" type="button" @click="updateClient(selectedClient)"' in html


def test_customers_list_guards_visit_write_controls():
    html = _read(CUSTOMERS_HTML)

    assert 'v-if="canWriteVisits" type="button" @click="openAddVisit"' in html
    assert "const requireClientWrite = () =>" in html
    assert "const requireVisitWrite = () =>" in html
    assert "const openAddVisit = () =>" in html
    assert "if (!requireVisitWrite()) return;" in html
    assert "@click=\"showAddVisit=true\"" not in html

    returned = html[html.index("return {") :]
    assert "canWriteClients" in returned
    assert "canWriteVisits" in returned
    assert "openAddVisit" in returned
    assert "requireClientWrite" in returned
    assert "requireVisitWrite" in returned


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
