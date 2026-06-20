"""Company materials library: permissions, API, file safety."""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

import security_foundation as sec
from auth.data_scope_catalog import PERMISSION_TO_RESOURCE, SYSTEM_PERMISSIONS
from auth.permissions import ALL_PERMISSION_CODES, ROLE_DEFAULT_PERMISSIONS, ROLE_DELIVERY, ROLE_SALES, ROLE_VIEWER
from tests.helpers import auth_header

MATERIALS_PERMISSION_CODES = frozenset({
    "materials.read",
    "materials.write",
    "materials.download",
    "materials.delete",
    "materials.public.read",
    "materials.public.preview",
    "materials.public.download",
    "materials.internal.read",
    "materials.internal.preview",
    "materials.internal.download",
})

SALES_MATERIALS_PERMISSIONS = frozenset({
    "materials.public.read",
    "materials.public.preview",
    "materials.public.download",
})

DELIVERY_MATERIALS_PERMISSIONS = frozenset({
    "materials.public.read",
    "materials.public.preview",
    "materials.internal.read",
    "materials.internal.preview",
})

_MIN_PDF = b"%PDF-1.4\n% materials test\n"
_NEW_PDF = _MIN_PDF + b"\nreplaced\n"


@pytest.fixture(scope="module")
def client_rbac(_test_env):
    os.environ["CRM_AUTH_MODE"] = "rbac"
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


@pytest.fixture(scope="module")
def engine(_test_env):
    import main as crm_main

    return crm_main.engine


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _create_user_with_perms(client, engine, admin_auth, suffix: str, perms, *, role_prefix: str = "MAT_PERMS") -> tuple[TestClient, object]:
    from auth.password import hash_password

    role_code = f"{role_prefix}_{suffix}"
    username = f"mat_user_{suffix}"
    password = "mat_user1"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT OR IGNORE INTO sys_role (code, name, description, is_builtin, created_at) "
                "VALUES (:code, :name, '', 0, datetime('now'))"
            ),
            {"code": role_code, "name": role_code},
        )
        rid = int(conn.execute(text("SELECT id FROM sys_role WHERE code = :c"), {"c": role_code}).fetchone()[0])
        conn.execute(text("DELETE FROM sys_role_permission WHERE role_id = :rid"), {"rid": rid})
        for perm in perms:
            pid = conn.execute(text("SELECT id FROM sys_permission WHERE code = :p"), {"p": perm}).scalar()
            if pid:
                conn.execute(
                    text("INSERT INTO sys_role_permission (role_id, permission_id) VALUES (:r, :p)"),
                    {"r": rid, "p": pid},
                )
        salt_b64, hash_b64, iters = hash_password(password)
        row = conn.execute(text("SELECT id FROM sys_user WHERE username = :u"), {"u": username}).fetchone()
        if row:
            uid = int(row[0])
            conn.execute(
                text(
                    "UPDATE sys_user SET password_hash = :h, password_salt = :s, "
                    "password_iters = :i, status = 'active', updated_at = datetime('now') "
                    "WHERE id = :uid"
                ),
                {"h": hash_b64, "s": salt_b64, "i": iters, "uid": uid},
            )
            conn.execute(text("DELETE FROM sys_user_role WHERE user_id = :uid"), {"uid": uid})
        else:
            conn.execute(
                text(
                    "INSERT INTO sys_user (username, display_name, password_hash, password_salt, "
                    "password_iters, status, session_version, created_at, updated_at) "
                    "VALUES (:u, :dn, :h, :s, :i, 'active', 0, datetime('now'), datetime('now'))"
                ),
                {"u": username, "dn": username, "h": hash_b64, "s": salt_b64, "i": iters},
            )
            uid = int(conn.execute(text("SELECT id FROM sys_user WHERE username = :u"), {"u": username}).fetchone()[0])
        conn.execute(
            text("INSERT OR IGNORE INTO sys_user_role (user_id, role_id) VALUES (:uid, :rid)"),
            {"uid": uid, "rid": rid},
        )
    login = _login(client, username, password)
    assert login.status_code == 200, login.text
    return client, login.cookies


def _create_materials_only_user(client, engine, admin_auth, suffix: str) -> tuple[TestClient, object]:
    return _create_user_with_perms(
        client,
        engine,
        admin_auth,
        suffix,
        ("materials.read",),
        role_prefix="MATERIALS_ONLY",
    )


def _admin_upload(
    client,
    cookies,
    title: str = "测试资料",
    *,
    confidentiality: str = "internal",
    filename: str = "license.pdf",
    content: bytes = _MIN_PDF,
) -> dict:
    r = client.post(
        "/api/materials",
        cookies=cookies,
        data={
            "title": title,
            "category": "business_license",
            "confidentiality": confidentiality,
            "description": "desc",
        },
        files={"file": (filename, content, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _mock_office_convert_write_pdf(**kwargs) -> str:
    import main as crm_main
    from services.material_preview_conversion import preview_cache_rel_path

    rel = preview_cache_rel_path(kwargs["material_id"], kwargs["updated_at"])
    abs_path = sec.resolve_upload_path(crm_main.UPLOAD_DIR, rel)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(_MIN_PDF)
    return abs_path


def test_materials_permissions_in_catalog():
    assert MATERIALS_PERMISSION_CODES <= ALL_PERMISSION_CODES
    assert MATERIALS_PERMISSION_CODES <= SYSTEM_PERMISSIONS
    for code in MATERIALS_PERMISSION_CODES:
        assert code not in PERMISSION_TO_RESOURCE


def test_materials_not_in_default_roles():
    assert SALES_MATERIALS_PERMISSIONS <= ROLE_DEFAULT_PERMISSIONS[ROLE_SALES]
    assert DELIVERY_MATERIALS_PERMISSIONS <= ROLE_DEFAULT_PERMISSIONS[ROLE_DELIVERY]
    assert not MATERIALS_PERMISSION_CODES.intersection(ROLE_DEFAULT_PERMISSIONS[ROLE_VIEWER])


def test_page_materials_requires_read(client_rbac, admin_auth):
    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    assert login.status_code == 200
    r = client_rbac.get("/materials", cookies=login.cookies)
    assert r.status_code == 200


def test_page_materials_forbidden_without_read(client_rbac, admin_auth):
    from tests.test_rbac_api_modules import _create_restricted

    user, pwd = admin_auth
    rsuffix = f"no_mat_{os.getpid()}"
    _create_restricted(client_rbac, user, pwd, rsuffix)
    login = _login(client_rbac, f"rbac_mod_{rsuffix}", "restricted1")
    assert login.status_code == 200
    r = client_rbac.get("/materials", cookies=login.cookies)
    assert r.status_code == 403


def test_materials_only_user_matrix(client_rbac, engine, admin_auth):
    suffix = f"only_{os.getpid()}"
    client, cookies = _create_materials_only_user(client_rbac, engine, admin_auth, suffix)

    r_page = client.get("/materials", cookies=cookies)
    assert r_page.status_code == 200

    r_list = client.get("/api/materials", cookies=cookies)
    assert r_list.status_code == 200
    for item in r_list.json().get("items", []):
        assert item["can_download"] is False
        assert item["can_preview"] is True
        assert item["can_write"] is False
        assert item["can_delete"] is False
        assert "stored_path" not in item

    r_post = client.post(
        "/api/materials",
        cookies=cookies,
        data={"title": "x", "category": "other", "confidentiality": "internal"},
        files={"file": ("a.pdf", _MIN_PDF, "application/pdf")},
    )
    assert r_post.status_code == 403

    admin_login = _login(client, *admin_auth)
    created = _admin_upload(client, admin_login.cookies, title=f"RO_{suffix}")
    mid = created["id"]

    r_patch = client.patch(
        f"/api/materials/{mid}",
        cookies=cookies,
        json={"title": "hack"},
    )
    assert r_patch.status_code == 403

    r_dl = client.get(f"/api/materials/{mid}/download", cookies=cookies)
    assert r_dl.status_code == 403

    r_arch = client.post(f"/api/materials/{mid}/archive", cookies=cookies)
    assert r_arch.status_code == 403


def test_admin_upload_list_download_archive(client_rbac, admin_auth, engine):
    import main as crm_main

    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    assert login.status_code == 200
    cookies = login.cookies

    created = _admin_upload(client_rbac, cookies, title=f"AdminMat_{os.getpid()}")
    mid = created["id"]
    assert created["can_download"] is True
    assert created["can_preview"] is True
    assert created["can_write"] is True
    assert created["can_delete"] is True
    assert "stored_path" not in created

    with crm_main.engine.connect() as conn:
        sp = conn.execute(
            text("SELECT stored_path FROM company_materials WHERE id = :id"),
            {"id": mid},
        ).scalar()
    assert sp
    assert sp.startswith("materials/")
    assert ".." not in sp
    assert not sp.startswith("/")
    assert not sp.startswith("uploads/")

    r_dl = client_rbac.get(f"/api/materials/{mid}/download", cookies=cookies)
    assert r_dl.status_code == 200
    assert r_dl.content == _MIN_PDF

    r_patch = client_rbac.patch(
        f"/api/materials/{mid}",
        cookies=cookies,
        json={"description": "updated"},
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["description"] == "updated"

    r_arch = client_rbac.post(f"/api/materials/{mid}/archive", cookies=cookies)
    assert r_arch.status_code == 200
    assert r_arch.json()["status"] == "archived"

    abs_path = sec.resolve_upload_path(crm_main.UPLOAD_DIR, sp)
    assert os.path.isfile(abs_path)

    r_list = client_rbac.get("/api/materials", cookies=cookies)
    ids = [x["id"] for x in r_list.json()["items"]]
    assert mid not in ids

    r_arch_list = client_rbac.get("/api/materials?status=archived", cookies=cookies)
    arch_ids = [x["id"] for x in r_arch_list.json()["items"]]
    assert mid in arch_ids


def test_patch_partial_does_not_clear_fields(client_rbac, admin_auth):
    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    cookies = login.cookies
    created = _admin_upload(client_rbac, cookies, title="PatchPartial")
    mid = created["id"]

    client_rbac.patch(
        f"/api/materials/{mid}",
        cookies=cookies,
        json={"owner_dept_id": None, "expires_at": "2030-01-01"},
    )
    detail = client_rbac.get(f"/api/materials/{mid}", cookies=cookies).json()
    assert detail["expires_at"] == "2030-01-01"

    client_rbac.patch(
        f"/api/materials/{mid}",
        cookies=cookies,
        json={"title": "OnlyTitle"},
    )
    detail2 = client_rbac.get(f"/api/materials/{mid}", cookies=cookies).json()
    assert detail2["title"] == "OnlyTitle"
    assert detail2["expires_at"] == "2030-01-01"


def test_download_path_traversal_blocked(client_rbac, admin_auth, engine):
    import main as crm_main

    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    created = _admin_upload(client_rbac, login.cookies)
    mid = created["id"]
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE company_materials SET stored_path = :sp WHERE id = :id"),
            {"sp": "../main.py", "id": mid},
        )
    r = client_rbac.get(f"/api/materials/{mid}/download", cookies=login.cookies)
    assert r.status_code in (400, 404)


def test_upload_rejects_bad_extension(client_rbac, admin_auth):
    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    r = client_rbac.post(
        "/api/materials",
        cookies=login.cookies,
        data={"title": "bad", "category": "other", "confidentiality": "internal"},
        files={"file": ("evil.exe", b"MZ", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_write_upload_chunked_rejects_oversize(tmp_path):
    import asyncio
    from io import BytesIO

    from fastapi import UploadFile

    from schemas.company_materials import MATERIAL_ALLOWED_SUFFIXES
    from services.company_materials import _write_upload_chunked

    target = tmp_path / "t.pdf"
    data = b"x" * 3000
    upload = UploadFile(filename="t.pdf", file=BytesIO(data))

    async def _run():
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await _write_upload_chunked(
                upload,
                str(target),
                max_file_size=1024,
                allowed_suffixes=MATERIAL_ALLOWED_SUFFIXES,
            )
        assert exc.value.status_code in (400, 413)

    asyncio.run(_run())
    assert not target.is_file()


def test_materials_replace_file_updates_metadata_and_download(client_rbac, admin_auth):
    import main as crm_main

    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    cookies = login.cookies
    created = _admin_upload(client_rbac, cookies, title=f"ReplaceMat_{os.getpid()}")
    mid = created["id"]

    with crm_main.engine.connect() as conn:
        old_sp = conn.execute(
            text("SELECT stored_path FROM company_materials WHERE id = :id"),
            {"id": mid},
        ).scalar()
    old_abs = sec.resolve_upload_path(crm_main.UPLOAD_DIR, old_sp)
    assert os.path.isfile(old_abs)

    r = client_rbac.post(
        f"/api/materials/{mid}/replace-file",
        cookies=cookies,
        files={"file": ("new.pdf", _NEW_PDF, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == mid
    assert body["file_name"] == "new.pdf"
    assert body["file_size"] == len(_NEW_PDF)

    r_dl = client_rbac.get(f"/api/materials/{mid}/download", cookies=cookies)
    assert r_dl.status_code == 200
    assert r_dl.content == _NEW_PDF
    assert not os.path.isfile(old_abs)


def test_materials_replace_file_requires_write(client_rbac, engine, admin_auth):
    suffix = f"replace_ro_{os.getpid()}"
    client, cookies = _create_materials_only_user(client_rbac, engine, admin_auth, suffix)
    admin_login = _login(client_rbac, *admin_auth)
    created = _admin_upload(client_rbac, admin_login.cookies, title=f"ReplaceRO_{suffix}")
    mid = created["id"]

    r = client.post(
        f"/api/materials/{mid}/replace-file",
        cookies=cookies,
        files={"file": ("new.pdf", _NEW_PDF, "application/pdf")},
    )
    assert r.status_code == 403


def test_materials_replace_file_rejects_archived_material(client_rbac, admin_auth):
    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    cookies = login.cookies
    created = _admin_upload(client_rbac, cookies, title=f"ReplaceArch_{os.getpid()}")
    mid = created["id"]

    r_arch = client_rbac.post(f"/api/materials/{mid}/archive", cookies=cookies)
    assert r_arch.status_code == 200

    r = client_rbac.post(
        f"/api/materials/{mid}/replace-file",
        cookies=cookies,
        files={"file": ("new.pdf", _NEW_PDF, "application/pdf")},
    )
    assert r.status_code == 400
    assert "已删除资料不可替换文件" in str(r.json().get("detail", ""))


def test_sales_sees_only_public_materials(client_rbac, engine, admin_auth):
    suffix = f"sales_{os.getpid()}"
    client, cookies = _create_user_with_perms(
        client_rbac, engine, admin_auth, suffix, sorted(SALES_MATERIALS_PERMISSIONS), role_prefix="MAT_SALES"
    )
    admin_login = _login(client_rbac, *admin_auth)
    admin_cookies = admin_login.cookies
    public_row = _admin_upload(
        client_rbac, admin_cookies, title=f"Pub_{suffix}", confidentiality="public",
    )
    internal_row = _admin_upload(
        client_rbac, admin_cookies, title=f"Int_{suffix}", confidentiality="internal",
    )
    confidential_row = _admin_upload(
        client_rbac, admin_cookies, title=f"Conf_{suffix}", confidentiality="confidential",
    )

    r_page = client.get("/materials", cookies=cookies)
    assert r_page.status_code == 200

    r_list = client.get("/api/materials", cookies=cookies)
    assert r_list.status_code == 200
    ids = {x["id"] for x in r_list.json()["items"]}
    assert public_row["id"] in ids
    assert internal_row["id"] not in ids
    assert confidential_row["id"] not in ids

    pub = next(x for x in r_list.json()["items"] if x["id"] == public_row["id"])
    assert pub["can_download"] is True
    assert pub["can_preview"] is True

    r_internal_detail = client.get(f"/api/materials/{internal_row['id']}", cookies=cookies)
    assert r_internal_detail.status_code == 404

    r_dl_public = client.get(f"/api/materials/{public_row['id']}/download", cookies=cookies)
    assert r_dl_public.status_code == 200

    r_dl_internal = client.get(f"/api/materials/{internal_row['id']}/download", cookies=cookies)
    assert r_dl_internal.status_code in (403, 404)


def test_delivery_internal_preview_without_download(client_rbac, engine, admin_auth):
    suffix = f"delivery_{os.getpid()}"
    client, cookies = _create_user_with_perms(
        client_rbac, engine, admin_auth, suffix, sorted(DELIVERY_MATERIALS_PERMISSIONS), role_prefix="MAT_DELIVERY"
    )
    admin_login = _login(client_rbac, *admin_auth)
    admin_cookies = admin_login.cookies
    public_row = _admin_upload(
        client_rbac, admin_cookies, title=f"DPub_{suffix}", confidentiality="public",
    )
    internal_row = _admin_upload(
        client_rbac, admin_cookies, title=f"DInt_{suffix}", confidentiality="internal",
    )

    r_list = client.get("/api/materials", cookies=cookies)
    assert r_list.status_code == 200
    by_id = {x["id"]: x for x in r_list.json()["items"]}
    assert public_row["id"] in by_id
    assert internal_row["id"] in by_id
    assert by_id[internal_row["id"]]["can_preview"] is True
    assert by_id[internal_row["id"]]["can_download"] is False

    r_preview = client.get(f"/api/materials/{internal_row['id']}/preview", cookies=cookies)
    assert r_preview.status_code == 200
    assert r_preview.content == _MIN_PDF
    assert "inline" in (r_preview.headers.get("content-disposition") or "").lower()

    r_dl = client.get(f"/api/materials/{internal_row['id']}/download", cookies=cookies)
    assert r_dl.status_code == 403


def test_confidential_hidden_from_sales_and_delivery(client_rbac, engine, admin_auth):
    suffix = f"conf_{os.getpid()}"
    admin_login = _login(client_rbac, *admin_auth)
    admin_cookies = admin_login.cookies
    confidential_row = _admin_upload(
        client_rbac, admin_cookies, title=f"Secret_{suffix}", confidentiality="confidential",
    )

    for perms, prefix in (
        (sorted(SALES_MATERIALS_PERMISSIONS), "MAT_SALES_CONF"),
        (sorted(DELIVERY_MATERIALS_PERMISSIONS), "MAT_DELIVERY_CONF"),
    ):
        _, cookies = _create_user_with_perms(
            client_rbac, engine, admin_auth, f"{suffix}_{prefix}", perms, role_prefix=prefix
        )
        r_list = client_rbac.get("/api/materials", cookies=cookies)
        ids = {x["id"] for x in r_list.json()["items"]}
        assert confidential_row["id"] not in ids
        r_detail = client_rbac.get(f"/api/materials/{confidential_row['id']}", cookies=cookies)
        assert r_detail.status_code == 404


def test_preview_zip_returns_400(client_rbac, engine, admin_auth):
    suffix = f"zip_{os.getpid()}"
    client, cookies = _create_user_with_perms(
        client_rbac, engine, admin_auth, suffix, sorted(SALES_MATERIALS_PERMISSIONS), role_prefix="MAT_ZIP"
    )
    admin_login = _login(client_rbac, *admin_auth)
    created = _admin_upload(
        client_rbac,
        admin_login.cookies,
        title=f"Zip_{suffix}",
        confidentiality="public",
        filename="bundle.zip",
        content=b"PK\x03\x04",
    )
    r = client.get(f"/api/materials/{created['id']}/preview", cookies=cookies)
    assert r.status_code == 400
    assert "暂不支持在线预览" in str(r.json().get("detail", ""))


def test_office_preview_returns_pdf(client_rbac, engine, admin_auth, monkeypatch):
    monkeypatch.setattr(
        "services.company_materials.convert_office_to_preview_pdf",
        _mock_office_convert_write_pdf,
    )
    suffix = f"office_ok_{os.getpid()}"
    client, cookies = _create_user_with_perms(
        client_rbac, engine, admin_auth, suffix, sorted(SALES_MATERIALS_PERMISSIONS), role_prefix="MAT_OFF_OK"
    )
    admin_login = _login(client_rbac, *admin_auth)
    for fname in ("brief.docx", "slides.pptx", "sheet.xlsx"):
        created = _admin_upload(
            client_rbac,
            admin_login.cookies,
            title=f"Office_{fname}_{suffix}",
            confidentiality="public",
            filename=fname,
            content=b"PK fake office",
        )
        r = client.get(f"/api/materials/{created['id']}/preview", cookies=cookies)
        assert r.status_code == 200, r.text
        assert r.content == _MIN_PDF
        assert "application/pdf" in (r.headers.get("content-type") or "")
        assert "inline" in (r.headers.get("content-disposition") or "").lower()


def test_office_preview_conversion_failure(client_rbac, engine, admin_auth, monkeypatch):
    from services.material_preview_conversion import MaterialPreviewConversionError

    def _fail(**kwargs):
        raise MaterialPreviewConversionError("mock failure")

    monkeypatch.setattr("services.company_materials.convert_office_to_preview_pdf", _fail)
    suffix = f"office_fail_{os.getpid()}"
    client, cookies = _create_user_with_perms(
        client_rbac, engine, admin_auth, suffix, sorted(SALES_MATERIALS_PERMISSIONS), role_prefix="MAT_OFF_FAIL"
    )
    admin_login = _login(client_rbac, *admin_auth)
    created = _admin_upload(
        client_rbac,
        admin_login.cookies,
        title=f"Fail_{suffix}",
        confidentiality="public",
        filename="brief.docx",
        content=b"PK docx",
    )
    r = client.get(f"/api/materials/{created['id']}/preview", cookies=cookies)
    assert r.status_code == 400
    assert "暂无法生成预览" in str(r.json().get("detail", ""))


def test_office_preview_forbidden_without_permission(client_rbac, engine, admin_auth, monkeypatch):
    monkeypatch.setattr(
        "services.company_materials.convert_office_to_preview_pdf",
        _mock_office_convert_write_pdf,
    )
    suffix = f"office_forbid_{os.getpid()}"
    client, cookies = _create_user_with_perms(
        client_rbac,
        engine,
        admin_auth,
        suffix,
        ("materials.public.read",),
        role_prefix="MAT_OFF_RO",
    )
    admin_login = _login(client_rbac, *admin_auth)
    created = _admin_upload(
        client_rbac,
        admin_login.cookies,
        title=f"RO_{suffix}",
        confidentiality="public",
        filename="brief.docx",
        content=b"PK docx",
    )
    r = client.get(f"/api/materials/{created['id']}/preview", cookies=cookies)
    assert r.status_code == 403


def test_delivery_office_internal_preview_no_download(client_rbac, engine, admin_auth, monkeypatch):
    monkeypatch.setattr(
        "services.company_materials.convert_office_to_preview_pdf",
        _mock_office_convert_write_pdf,
    )
    suffix = f"del_off_{os.getpid()}"
    client, cookies = _create_user_with_perms(
        client_rbac, engine, admin_auth, suffix, sorted(DELIVERY_MATERIALS_PERMISSIONS), role_prefix="MAT_DEL_OFF"
    )
    admin_login = _login(client_rbac, *admin_auth)
    created = _admin_upload(
        client_rbac,
        admin_login.cookies,
        title=f"DIntDoc_{suffix}",
        confidentiality="internal",
        filename="internal.docx",
        content=b"PK docx",
    )
    detail = client.get(f"/api/materials/{created['id']}", cookies=cookies).json()
    assert detail["can_preview"] is True
    assert detail["can_download"] is False

    r_preview = client.get(f"/api/materials/{created['id']}/preview", cookies=cookies)
    assert r_preview.status_code == 200
    assert "application/pdf" in (r_preview.headers.get("content-type") or "")

    r_dl = client.get(f"/api/materials/{created['id']}/download", cookies=cookies)
    assert r_dl.status_code == 403


def test_materials_preview_route_registered(client_rbac, admin_auth):
    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    created = _admin_upload(client_rbac, login.cookies, title=f"PreviewRoute_{os.getpid()}", confidentiality="public")
    r = client_rbac.get(f"/api/materials/{created['id']}/preview", cookies=login.cookies)
    assert r.status_code == 200
    assert "inline" in (r.headers.get("content-disposition") or "").lower()


def test_crm_api_exposes_patch():
    root = Path(__file__).resolve().parent.parent
    api_src = (root / "static/js/core/crm-api.js").read_text(encoding="utf-8")
    js = (root / "static/js/pages/materials.js").read_text(encoding="utf-8")
    assert "function patch(" in api_src
    assert "patch: patch" in api_src
    assert "crmApi.patch" in js


def test_materials_delete_button_text():
    root = Path(__file__).resolve().parent.parent
    html = (root / "templates/pages/materials.html").read_text(encoding="utf-8")
    assert '@click="archiveMaterial(row)">删除</button>' in html
    assert '@click="archiveMaterial(row)">归档</button>' not in html
    assert ">归档</button>" not in html


def test_materials_frontend_permission_refresh():
    root = Path(__file__).resolve().parent.parent
    js = (root / "static/js/pages/materials.js").read_text(encoding="utf-8")
    html = (root / "templates/pages/materials.html").read_text(encoding="utf-8")
    assert "crm-shell-ready" in js
    assert "refreshMaterialPermissions" in js
    assert "canWriteMaterials = ref(" in js
    assert "onUnmounted" in js
    assert "removeEventListener('crm-shell-ready', refreshMaterialPermissions)" in js
    assert 'v-if="canWriteMaterials"' in html
    assert "上传资料" in html
    assert "max-w-5xl" in html
    assert "点击或拖拽文件到此处" in html
    assert "选择新文件替换当前文件" in html
    assert "replace-file" in js
    assert "previewMaterial" in js
    assert "showPreviewModal" in js
    assert '@click="closeForm">&times;</button>' in html
    assert "crm-form-control" in html
    assert "materials-upload-dropzone" in html
    assert "@drop.prevent=\"onDrop\"" in html
    assert "crm-name-link" in html
    assert "selectedFileName" in js
    assert "editFileName" in js
    assert "function onDrop(" in js
    assert "function clearSelectedFile(" in js
    assert "function confidentialityBadge(" in js
    assert "function statusBadge(" in js
    assert "materials-status-badge" in html
    assert "confidentialityBadge(row.confidentiality)" in html
    assert "materials-table-frame" in html
    assert ">预览</button>" in html
