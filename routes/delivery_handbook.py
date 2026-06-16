"""Delivery Handbook API routes — migrated from main.py (Phase 5D).

register_delivery_handbook_routes(app, ...) mounts all handbook endpoints.
"""
from __future__ import annotations

import io
import json
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from fastapi import BackgroundTasks, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, desc, func, or_, text
from sqlalchemy.orm import Session

import security_foundation as sec
from auth.deps import require_permission
from schemas.delivery_handbook import (
    HANDBOOK_ALLOWED_SUFFIXES,
    HANDBOOK_SEARCH_BODY_MAX,
    HANDBOOK_SEARCH_SNIPPET_LIST,
    HANDBOOK_SEARCH_SNIPPET_MODAL,
    HANDBOOK_STATUS_SET,
)
from services.delivery_handbook import (
    handbook_build_fts_query,
    handbook_client_dir_rel,
    handbook_cues_from_json_string,
    handbook_dt_iso,
    handbook_fts_delete_row,
    handbook_fts_upsert_row,
    handbook_labels_to_json_array,
    handbook_locate_media_seconds,
    handbook_locate_pdf_page,
    handbook_manual_search_blob,
    handbook_normalize_media_cues,
    handbook_normalize_status,
    handbook_outline_coerce,
    handbook_parse_json_list,
    handbook_query_terms,
    handbook_row_to_dict,
    handbook_search_snippet,
    handbook_split_comma_labels,
    handbook_suffix_to_media_kind,
    handbook_text_matches,
    make_background_index_manual_meta,
    make_background_index_pdf,
    pdf_bytes_to_outline_tree,
    pdf_plain_text_pages,
    pdf_render_page_png,
    safe_handbook_filename,
)


def register_delivery_handbook_routes(
    app,
    *,
    get_db: Callable,
    Client: Type,
    DeliveryHandbookFile: Type,
    AuditLog: Type,
    engine,
    session_factory: Callable,
    upload_dir: str,
    max_file_size: int,
):
    bg_index_pdf = make_background_index_pdf(session_factory, engine, DeliveryHandbookFile, upload_dir)
    bg_index_manual_meta = make_background_index_manual_meta(session_factory, engine, DeliveryHandbookFile)

    def _row_to_dict(r):
        return handbook_row_to_dict(r, sec.file_access_url)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    @app.get("/api/clients/{client_id}/delivery/handbooks")
    async def list_delivery_handbooks(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handbook.read")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        rows = (
            db.query(DeliveryHandbookFile)
            .filter(DeliveryHandbookFile.client_id == client_id)
            .order_by(desc(DeliveryHandbookFile.created_at))
            .all()
        )
        return [_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Upload (create)
    # ------------------------------------------------------------------

    @app.post("/api/clients/{client_id}/delivery/handbooks")
    async def upload_delivery_handbooks(
        client_id: int,
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(default=[]),
        version_label: str = Form(default=""),
        status: str = Form(default=""),
        tags: str = Form(default=""),
        permission_departments: str = Form(default=""),
        permission_levels: str = Form(default=""),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handbook.write")),
    ):
        if not files:
            raise HTTPException(status_code=400, detail="请选择文件")
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="客户不存在")
        rel_dir = handbook_client_dir_rel(client)
        abs_dir = sec.resolve_upload_path(upload_dir, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        ts_base = int(time.time() * 1000000)
        status_raw = str(status or "").strip().lower()
        if status_raw not in HANDBOOK_STATUS_SET:
            raise HTTPException(status_code=400, detail="请选择状态")
        if not handbook_split_comma_labels(tags):
            raise HTTPException(status_code=400, detail="请填写标签")
        if not handbook_split_comma_labels(permission_departments):
            raise HTTPException(status_code=400, detail="请填写阅读部门")
        level_values = handbook_split_comma_labels(permission_levels)
        if len(level_values) != 1 or level_values[0] not in {"1", "2", "3", "4", "5"}:
            raise HTTPException(status_code=400, detail="请选择阅读级别（1-5）")
        st = handbook_normalize_status(status_raw)
        tags_js = handbook_labels_to_json_array(tags)
        pd_js = handbook_labels_to_json_array(permission_departments)
        pl_js = handbook_labels_to_json_array(permission_levels)
        vlabel = str(version_label or "").strip()
        payloads: List[Tuple[str, bytes, str, str, str]] = []
        for idx, up in enumerate(files):
            raw_name = up.filename or ""
            ext = os.path.splitext(raw_name)[1].lower()
            if ext not in HANDBOOK_ALLOWED_SUFFIXES:
                display_name = raw_name or "\uff08\u672a\u547d\u540d\uff09"
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"\u4e0d\u652f\u6301\u7684\u6587\u4ef6\u7c7b\u578b\uff1a{display_name}\uff0c"
                        "\u5141\u8bb8\uff1aPDF\u3001Word\u3001\u5e38\u89c1\u97f3\u89c6\u9891\uff08mp4/webm/mp3 \u7b49\uff09"
                    ),
                )
            content_bytes = await up.read()
            if len(content_bytes) > max_file_size:
                oversize_name = raw_name or "\u672a\u547d\u540d"
                raise HTTPException(status_code=400, detail=f"\u6587\u4ef6\u8d85\u8fc720MB\u9650\u5236\uff1a{oversize_name}")
            safe = safe_handbook_filename(raw_name)
            if not os.path.splitext(safe)[1]:
                safe = safe + ext
            stored_rel = f"{rel_dir}/{ts_base}_{idx}_{safe}"
            mk = handbook_suffix_to_media_kind(ext)
            payloads.append((stored_rel, content_bytes, raw_name, safe, mk))
        saved: List = []
        now = datetime.now()
        for stored_rel, content_bytes, raw_name, safe, mk in payloads:
            try:
                abs_target = sec.resolve_upload_path(upload_dir, stored_rel)
            except ValueError:
                raise HTTPException(status_code=400, detail="\u975e\u6cd5\u6587\u4ef6\u8def\u5f84")
            with open(abs_target, "wb") as f:
                f.write(content_bytes)
            outline_js = "[]"
            if mk == "pdf":
                tree = pdf_bytes_to_outline_tree(content_bytes)
                outline_js = json.dumps(tree, ensure_ascii=False)
            row = DeliveryHandbookFile(
                client_id=client_id,
                original_filename=raw_name or safe,
                stored_path=stored_rel,
                version_label=vlabel,
                status=st,
                tags_json=tags_js,
                permission_departments_json=pd_js,
                permission_levels_json=pl_js,
                media_kind=mk,
                pdf_outline_json=outline_js,
                media_cues_json="[]",
                search_status=("pending" if mk in ("pdf", "video", "audio", "document") else "skipped"),
                search_method=("none" if mk not in ("pdf", "video", "audio", "document") else ""),
                search_error="",
                search_body="",
                updated_at=now,
            )
            db.add(row)
            saved.append(row)
        db.commit()
        for row in saved:
            db.refresh(row)
            if row.media_kind == "pdf":
                background_tasks.add_task(bg_index_pdf, int(row.id))
            elif row.media_kind in ("video", "audio", "document"):
                background_tasks.add_task(bg_index_manual_meta, int(row.id))
        return [_row_to_dict(r) for r in saved]

    # ------------------------------------------------------------------
    # Patch metadata
    # ------------------------------------------------------------------

    @app.patch("/api/clients/{client_id}/delivery/handbooks/{row_id}")
    async def patch_delivery_handbook(
        client_id: int,
        row_id: int,
        background_tasks: BackgroundTasks,
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handbook.write")),
    ):
        row = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
        if not row or row.client_id != client_id:
            raise HTTPException(status_code=404, detail="\u8bb0\u5f55\u4e0d\u5b58\u5728")
        if not isinstance(body, dict):
            body = {}
        if "version_label" in body:
            row.version_label = str(body.get("version_label") or "").strip()
        if "status" in body:
            row.status = handbook_normalize_status(str(body.get("status") or ""))
        if "tags" in body:
            t = body.get("tags")
            if isinstance(t, list):
                row.tags_json = json.dumps([str(x).strip() for x in t if str(x).strip()], ensure_ascii=False)
            else:
                row.tags_json = handbook_labels_to_json_array(str(t or ""))
        if "permission_departments" in body:
            t = body.get("permission_departments")
            if isinstance(t, list):
                row.permission_departments_json = json.dumps(
                    [str(x).strip() for x in t if str(x).strip()], ensure_ascii=False
                )
            else:
                row.permission_departments_json = handbook_labels_to_json_array(str(t or ""))
        if "permission_levels" in body:
            t = body.get("permission_levels")
            if isinstance(t, list):
                row.permission_levels_json = json.dumps(
                    [str(x).strip() for x in t if str(x).strip()], ensure_ascii=False
                )
            else:
                row.permission_levels_json = handbook_labels_to_json_array(str(t or ""))
        if "media_cues" in body:
            row.media_cues_json = json.dumps(
                handbook_normalize_media_cues(body.get("media_cues")), ensure_ascii=False
            )
        row.updated_at = datetime.now()
        db.commit()
        db.refresh(row)
        mk = (row.media_kind or "").strip() or handbook_suffix_to_media_kind(
            os.path.splitext(row.original_filename or "")[1].lower()
        )
        if mk in ("video", "audio", "document"):
            background_tasks.add_task(bg_index_manual_meta, int(row.id))
        return _row_to_dict(row)

    # ------------------------------------------------------------------
    # Rebuild PDF outline
    # ------------------------------------------------------------------

    @app.post("/api/clients/{client_id}/delivery/handbooks/{row_id}/rebuild-pdf-outline")
    async def rebuild_handbook_pdf_outline(
        client_id: int,
        row_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handbook.write")),
    ):
        row = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
        if not row or row.client_id != client_id:
            raise HTTPException(status_code=404, detail="\u8bb0\u5f55\u4e0d\u5b58\u5728")
        mk = (row.media_kind or "").strip() or handbook_suffix_to_media_kind(
            os.path.splitext(row.original_filename or "")[1].lower()
        )
        if mk != "pdf":
            raise HTTPException(status_code=400, detail="\u4ec5\u652f\u6301 PDF \u91cd\u65b0\u63d0\u53d6\u76ee\u5f55")
        try:
            path = sec.resolve_upload_path(upload_dir, (row.stored_path or "").strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="\u975e\u6cd5\u6587\u4ef6\u8def\u5f84")
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="\u6587\u4ef6\u4e0d\u5b58\u5728")
        with open(path, "rb") as f:
            data = f.read()
        tree = pdf_bytes_to_outline_tree(data)
        row.pdf_outline_json = json.dumps(tree, ensure_ascii=False)
        row.updated_at = datetime.now()
        db.commit()
        db.refresh(row)
        return _row_to_dict(row)

    # ------------------------------------------------------------------
    # PDF text
    # ------------------------------------------------------------------

    @app.get("/api/clients/{client_id}/delivery/handbooks/{row_id}/pdf-text")
    async def get_handbook_pdf_text(
        client_id: int,
        row_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handbook.read")),
    ):
        row = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
        if not row or row.client_id != client_id:
            raise HTTPException(status_code=404, detail="\u8bb0\u5f55\u4e0d\u5b58\u5728")
        mk = (row.media_kind or "").strip() or handbook_suffix_to_media_kind(
            os.path.splitext(row.original_filename or "")[1].lower()
        )
        if mk != "pdf":
            raise HTTPException(status_code=400, detail="\u4ec5\u652f\u6301 PDF \u6b63\u6587\u68c0\u7d22")
        try:
            path = sec.resolve_upload_path(upload_dir, (row.stored_path or "").strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="\u975e\u6cd5\u6587\u4ef6\u8def\u5f84")
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="\u6587\u4ef6\u4e0d\u5b58\u5728")
        with open(path, "rb") as f:
            pages = pdf_plain_text_pages(f.read())
        return {"id": row.id, "pages": pages}

    # ------------------------------------------------------------------
    # PDF page render
    # ------------------------------------------------------------------

    @app.get("/api/clients/{client_id}/delivery/handbooks/{row_id}/pdf-page.png")
    async def get_handbook_pdf_page_png(
        client_id: int,
        row_id: int,
        page: int = 1,
        q: str = "",
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handbook.read")),
    ):
        row = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
        if not row or row.client_id != client_id:
            raise HTTPException(status_code=404, detail="\u8bb0\u5f55\u4e0d\u5b58\u5728")
        mk = (row.media_kind or "").strip() or handbook_suffix_to_media_kind(
            os.path.splitext(row.original_filename or "")[1].lower()
        )
        if mk != "pdf":
            raise HTTPException(status_code=400, detail="\u4ec5\u652f\u6301 PDF \u9875\u9762\u6e32\u67d3")
        try:
            path = sec.resolve_upload_path(upload_dir, (row.stored_path or "").strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="\u975e\u6cd5\u6587\u4ef6\u8def\u5f84")
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="\u6587\u4ef6\u4e0d\u5b58\u5728")
        with open(path, "rb") as f:
            png = pdf_render_page_png(f.read(), page, q)
        return StreamingResponse(io.BytesIO(png), media_type="image/png")

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    @app.delete("/api/clients/{client_id}/delivery/handbooks/{row_id}")
    async def delete_delivery_handbook(
        client_id: int,
        row_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handbook.write")),
    ):
        row = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == row_id).first()
        if not row or row.client_id != client_id:
            raise HTTPException(status_code=404, detail="\u8bb0\u5f55\u4e0d\u5b58\u5728")
        try:
            path = sec.resolve_upload_path(upload_dir, (row.stored_path or "").strip())
        except ValueError:
            path = None
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
        rid = int(row.id)
        db.delete(row)
        db.commit()
        try:
            handbook_fts_delete_row(engine, rid)
        except Exception:
            pass
        return {"status": "ok"}

    # ------------------------------------------------------------------
    # Cross-client search
    # ------------------------------------------------------------------

    @app.get("/api/delivery/handbooks/search")
    async def delivery_handbooks_search_cross_client(
        q: str,
        limit: int = 40,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handbook.read")),
    ):
        q_strip = (q or "").strip()
        if not q_strip:
            raise HTTPException(status_code=400, detail="\u8bf7\u8f93\u5165\u68c0\u7d22\u8bcd")
        lim = max(1, min(int(limit or 40), 100))
        fq = handbook_build_fts_query(q_strip)
        seen: Dict[int, Dict[str, Any]] = {}

        def row_to_hit(hrow) -> Dict[str, Any]:
            c = db.query(Client).filter(Client.id == hrow.client_id).first()
            d = _row_to_dict(hrow)
            d["client_name"] = (c.name if c else "") or ""
            d["snippet"] = handbook_search_snippet(
                hrow.search_body, q_strip, max_len=HANDBOOK_SEARCH_SNIPPET_LIST, collapse_ws=True
            )
            d["excerpt_detail"] = handbook_search_snippet(
                hrow.search_body, q_strip, max_len=HANDBOOK_SEARCH_SNIPPET_MODAL, collapse_ws=False
            )
            return d

        if fq:
            try:
                with engine.connect() as conn:
                    frows = (
                        conn.execute(
                            text(
                                "SELECT handbook_fts.rowid AS id, handbook_fts.client_id AS client_id, "
                                "bm25(handbook_fts) AS rk FROM handbook_fts "
                                "WHERE handbook_fts MATCH :match ORDER BY rk LIMIT :lim"
                            ),
                            {"match": fq, "lim": lim},
                        )
                        .mappings()
                        .all()
                    )
                for m in frows:
                    hid = int(m["id"])
                    if hid in seen or len(seen) >= lim:
                        continue
                    hrow = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == hid).first()
                    if not hrow or hrow.search_status != "indexed":
                        continue
                    seen[hid] = row_to_hit(hrow)
            except Exception:
                pass

        if len(seen) < lim:
            needle = q_strip
            tail = lim - len(seen)
            sub_rows = (
                db.query(DeliveryHandbookFile)
                .filter(
                    DeliveryHandbookFile.media_kind.in_(["pdf", "video", "audio", "document"]),
                    DeliveryHandbookFile.search_status == "indexed",
                    or_(
                        func.instr(DeliveryHandbookFile.search_body, needle) > 0,
                        func.instr(DeliveryHandbookFile.original_filename, needle) > 0,
                    ),
                )
                .order_by(desc(DeliveryHandbookFile.updated_at))
                .limit(max(tail * 4, 8))
                .all()
            )
            for hrow in sub_rows:
                if len(seen) >= lim:
                    break
                if int(hrow.id) in seen:
                    continue
                seen[int(hrow.id)] = row_to_hit(hrow)

        out_list = list(seen.values())[:lim]
        return {"query": q_strip, "results": out_list}

    # ------------------------------------------------------------------
    # Handbook assistant chat
    # ------------------------------------------------------------------

    @app.post("/api/handbook-assistant/chat")
    async def handbook_assistant_chat(
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handbook.read")),
    ):
        q_strip = str((body or {}).get("q") or (body or {}).get("query") or "").strip()
        if not q_strip:
            raise HTTPException(status_code=400, detail="\u8bf7\u8f93\u5165\u95ee\u9898\u6216\u68c0\u7d22\u8bcd")
        lim = max(1, min(int((body or {}).get("limit") or 6), 12))
        fq = handbook_build_fts_query(q_strip)
        terms = handbook_query_terms(q_strip)
        seen: Dict[int, Any] = {}

        if fq:
            try:
                with engine.connect() as conn:
                    frows = (
                        conn.execute(
                            text(
                                "SELECT handbook_fts.rowid AS id, bm25(handbook_fts) AS rk "
                                "FROM handbook_fts WHERE handbook_fts MATCH :match ORDER BY rk LIMIT :lim"
                            ),
                            {"match": fq, "lim": lim},
                        )
                        .mappings()
                        .all()
                    )
                for m in frows:
                    hid = int(m["id"])
                    if hid in seen:
                        continue
                    hrow = db.query(DeliveryHandbookFile).filter(DeliveryHandbookFile.id == hid).first()
                    if (
                        hrow
                        and hrow.search_status == "indexed"
                        and (
                            handbook_text_matches(hrow.search_body, terms)
                            or handbook_text_matches(hrow.original_filename, terms)
                        )
                    ):
                        seen[hid] = hrow
            except Exception:
                pass

        if len(seen) < lim:
            tail = lim - len(seen)
            sub_rows = (
                db.query(DeliveryHandbookFile)
                .filter(
                    DeliveryHandbookFile.media_kind.in_(["pdf", "video", "audio", "document"]),
                    DeliveryHandbookFile.search_status == "indexed",
                    or_(
                        func.instr(DeliveryHandbookFile.search_body, q_strip) > 0,
                        func.instr(DeliveryHandbookFile.original_filename, q_strip) > 0,
                    ),
                )
                .order_by(desc(DeliveryHandbookFile.updated_at))
                .limit(max(tail * 4, 8))
                .all()
            )
            for hrow in sub_rows:
                if len(seen) >= lim:
                    break
                seen.setdefault(int(hrow.id), hrow)

        sources: List[Dict[str, Any]] = []
        for hrow in list(seen.values())[:lim]:
            if not (
                handbook_text_matches(hrow.search_body, terms)
                or handbook_text_matches(hrow.original_filename, terms)
            ):
                continue
            c = db.query(Client).filter(Client.id == hrow.client_id).first()
            mk = (hrow.media_kind or "").strip() or handbook_suffix_to_media_kind(
                os.path.splitext(hrow.original_filename or "")[1].lower()
            )
            summary = handbook_search_snippet(
                hrow.search_body, q_strip, max_len=760, collapse_ws=True
            )
            source: Dict[str, Any] = {
                "client_id": int(hrow.client_id),
                "client_name": (c.name if c else "") or "",
                "handbook_id": int(hrow.id),
                "filename": hrow.original_filename or "",
                "media_kind": mk,
                "snippet": summary,
                "summary": summary,
                "matched_terms": terms,
                "search_method": (hrow.search_method or "").strip(),
            }
            params = f"handbook_id={int(hrow.id)}"
            if mk == "pdf":
                page = handbook_locate_pdf_page(hrow, q_strip, upload_dir)
                source["page"] = page
                params += f"&page={page}"
            elif mk in ("video", "audio"):
                seconds = handbook_locate_media_seconds(hrow, q_strip)
                if seconds is not None:
                    source["seconds"] = seconds
                    params += f"&seconds={seconds:g}"
            source["url"] = f"/delivery/handbook/{int(hrow.client_id)}?{params}"
            sources.append(source)

        if sources:
            client_names = [s.get("client_name") or f"\u5ba2\u6237#{s.get('client_id')}" for s in sources[:3]]
            client_names_text = "\u3001".join(client_names)
            answer = (
                f"\u627e\u5230 {len(sources)} \u6761\u76f8\u5173\u6765\u6e90\uff0c\u4e3b\u8981\u6765\u81ea {client_names_text}\u3002"
                "\u4e0b\u9762\u7684\u6765\u6e90\u53c2\u8003\u53ef\u76f4\u63a5\u6253\u5f00\u5bf9\u5e94\u624b\u518c\u4f4d\u7f6e\u3002"
            )
        else:
            answer = "\u6682\u672a\u627e\u5230\u76f8\u5173\u624b\u518c\u6765\u6e90\u3002\u53ef\u5c1d\u8bd5\u6362\u4e00\u4e2a\u5173\u952e\u8bcd\uff0c\u6216\u5148\u5728\u624b\u518c\u9875\u540c\u6b65 FTS / \u91cd\u6392\u7d22\u5f15\u3002"
        return {"query": q_strip, "answer": answer, "sources": sources, "mode": "retrieval"}

    # ------------------------------------------------------------------
    # Sync FTS from already indexed bodies
    # ------------------------------------------------------------------

    @app.post("/api/delivery/handbooks/sync-fts-indexed")
    async def delivery_handbooks_sync_fts_from_body(
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handbook.write")),
    ):
        rows = (
            db.query(DeliveryHandbookFile)
            .filter(
                DeliveryHandbookFile.media_kind == "pdf",
                DeliveryHandbookFile.search_status == "indexed",
                DeliveryHandbookFile.search_body.isnot(None),
                DeliveryHandbookFile.search_body != "",
            )
            .all()
        )
        synced = 0
        for r in rows:
            try:
                handbook_fts_upsert_row(engine, int(r.id), int(r.client_id), r.original_filename or "", r.search_body or "")
                synced += 1
            except Exception:
                continue
        media_rows = (
            db.query(DeliveryHandbookFile)
            .filter(DeliveryHandbookFile.media_kind.in_(["video", "audio", "document"]))
            .all()
        )
        for r in media_rows:
            blob = handbook_manual_search_blob(r).strip()
            if not blob:
                try:
                    handbook_fts_delete_row(engine, int(r.id))
                except Exception:
                    pass
                continue
            r.search_body = blob[:HANDBOOK_SEARCH_BODY_MAX]
            r.search_method = "meta"
            r.search_status = "indexed"
            r.search_error = ""
            r.updated_at = datetime.now()
            try:
                db.commit()
                handbook_fts_upsert_row(engine, int(r.id), int(r.client_id), r.original_filename or "", r.search_body or "")
                synced += 1
            except Exception:
                db.rollback()
                continue
        return {"synced": synced}

    # ------------------------------------------------------------------
    # Reindex stale
    # ------------------------------------------------------------------

    @app.post("/api/delivery/handbooks/reindex-stale")
    async def delivery_handbooks_reindex_stale(
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.handbook.write")),
    ):
        rows = (
            db.query(DeliveryHandbookFile)
            .filter(
                or_(
                    and_(
                        DeliveryHandbookFile.media_kind == "pdf",
                        DeliveryHandbookFile.search_status.in_(["pending", "failed", "indexing"]),
                    ),
                    and_(
                        DeliveryHandbookFile.media_kind.in_(["video", "audio", "document"]),
                        DeliveryHandbookFile.search_status.in_(["pending", "failed", "indexing"]),
                    ),
                )
            )
            .all()
        )
        for r in rows:
            if r.media_kind == "pdf":
                background_tasks.add_task(bg_index_pdf, int(r.id))
            else:
                background_tasks.add_task(bg_index_manual_meta, int(r.id))
        return {"queued": len(rows)}
