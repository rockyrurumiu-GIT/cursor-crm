"""Delivery Roster API routes — migrated from main.py (Phase 5A)."""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Type

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth.deps import get_current_context, require_permission
from auth.service import AuthContext
from schemas.delivery_roster import (
    CHINESE_ROSTER_HEADER_MAP,
    ROSTER_CREATE_REQUIRED_FIELDS,
    ROSTER_EXPORT_HEADERS,
    ROSTER_REQUIRED_LABELS,
    ZNTX_ROSTER_EXPORT_HEADERS,
)
from services.delivery_roster import (
    apply_roster_salary_quote_ratio,
    assert_roster_contact_unique,
    assert_roster_contact_unique_global,
    analyze_roster_csv_headers,
    compute_turnover_dashboard,
    contact_dedup_key,
    decode_roster_upload_bytes,
    ensure_merged_turnover_employment,
    iter_roster_csv_data_rows,
    normalize_roster_payload,
    resequence_roster_serial_no,
    resequence_roster_serial_no_all_clients,
    resolve_roster_customer_client,
    roster_entries_turnover_pool,
    roster_entries_union_of_all_clients,
    roster_entry_to_dict,
    sql_roster_employment_active_pool,
    sql_roster_employment_left,
    validate_roster_business_fields,
    write_roster_backup_csv,
    write_roster_backup_csv_all,
    write_roster_backup_turnover_csv_all,
)


def register_delivery_roster_routes(
    app,
    *,
    get_db: Callable,
    Client: Type,
    RosterEntry: Type,
    AuditLog: Type,
    backup_dir: str,
    max_file_size: int,
    strip_excel_sep: Callable[[str], str],
    pick_latest_backup: Callable,
    set_csv_download_headers: Callable,
    interview_mark_left_fn: Callable,
    normalize_interview_name_fn: Callable,
):
    # --- List / Read ---

    @app.get("/api/roster")
    async def roster_list_all(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("delivery.roster.read")),
    ):
        rows = roster_entries_union_of_all_clients(db, ctx, RosterEntry, Client)
        return [roster_entry_to_dict(r) for r in rows]

    @app.get("/api/roster/turnover")
    async def roster_turnover_list(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("delivery.roster.read")),
    ):
        rows = roster_entries_turnover_pool(db, RosterEntry, Client, ctx)
        return [roster_entry_to_dict(r) for r in rows]

    @app.get("/api/roster/turnover/dashboard")
    async def roster_turnover_dashboard(
        scope: str = "department",
        business_key: str = "",
        trend_months: int = 12,
        period_start: str = "",
        period_end: str = "",
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.read")),
    ):
        return compute_turnover_dashboard(
            db, scope, business_key, trend_months, period_start, period_end,
            RosterEntry, Client,
        )

    @app.get("/api/roster/export")
    async def roster_export_csv_all(
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.read")),
    ):
        rows = roster_entries_union_of_all_clients(db, None, RosterEntry, Client)
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(ROSTER_EXPORT_HEADERS)
        for row_index, e in enumerate(rows, start=1):
            d = roster_entry_to_dict(e)
            line = []
            for zh in ROSTER_EXPORT_HEADERS:
                fn = CHINESE_ROSTER_HEADER_MAP[zh]
                if zh == "序号":
                    line.append(str(row_index))
                else:
                    line.append(d.get(fn, ""))
            writer.writerow(line)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
        set_csv_download_headers(response, chinese_filename=f"整体花名册_{ts}.csv", ascii_base=f"roster_all_{ts}")
        return response

    @app.get("/api/roster/turnover/export")
    async def roster_turnover_export_csv_all(
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.read")),
    ):
        rows = roster_entries_turnover_pool(db, RosterEntry, Client)
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(ROSTER_EXPORT_HEADERS)
        for e in rows:
            d = roster_entry_to_dict(e)
            line = []
            for zh in ROSTER_EXPORT_HEADERS:
                fn = CHINESE_ROSTER_HEADER_MAP[zh]
                line.append(d.get(fn, ""))
            writer.writerow(line)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
        set_csv_download_headers(response, chinese_filename=f"离职率分析_离职档案_{ts}.csv", ascii_base=f"roster_turnover_{ts}")
        return response

    @app.get("/api/roster/logs")
    async def roster_logs_all(
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.read")),
    ):
        logs = db.query(AuditLog).filter(AuditLog.action.like("%花名册%")).order_by(desc(AuditLog.created_at)).limit(300).all()
        return logs

    @app.get("/api/clients/{client_id}/roster")
    async def roster_list(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.read")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        rows = (
            db.query(RosterEntry)
            .filter(RosterEntry.client_id == client_id, sql_roster_employment_active_pool(RosterEntry))
            .order_by(RosterEntry.id)
            .all()
        )
        return [roster_entry_to_dict(r) for r in rows]

    @app.get("/api/clients/{client_id}/roster/export")
    async def roster_export_csv(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.read")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        rows = (
            db.query(RosterEntry)
            .filter(RosterEntry.client_id == client_id, sql_roster_employment_active_pool(RosterEntry))
            .order_by(RosterEntry.id)
            .all()
        )
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        export_headers = ZNTX_ROSTER_EXPORT_HEADERS if c.name == "中诺通讯" else ROSTER_EXPORT_HEADERS
        writer.writerow(export_headers)
        for e in rows:
            d = roster_entry_to_dict(e)
            line = []
            for zh in export_headers:
                fn = CHINESE_ROSTER_HEADER_MAP[zh]
                line.append(d.get(fn, ""))
            writer.writerow(line)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        chinese_name = f"{c.name}_花名册_{ts}.csv"
        response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
        set_csv_download_headers(response, chinese_filename=chinese_name, ascii_base=f"client_{client_id}_roster_{ts}")
        return response

    # --- Write / Mutate ---

    @app.post("/api/roster")
    async def roster_create_row_all(
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.write")),
    ):
        data = normalize_roster_payload(body if isinstance(body, dict) else {})
        missing = [k for k in ROSTER_CREATE_REQUIRED_FIELDS if not str(data.get(k, "")).strip()]
        if missing:
            labels = [ROSTER_REQUIRED_LABELS.get(k, k) for k in missing]
            raise HTTPException(status_code=400, detail=f"新增失败，以下必填项未填写：{'、'.join(labels)}")
        validate_roster_business_fields(data)
        apply_roster_salary_quote_ratio(data)
        assert_roster_contact_unique_global(db, data.get("contact_info", ""), RosterEntry)
        mc, normalized_cn = resolve_roster_customer_client(db, data.get("customer_name", ""), Client)
        if not mc:
            raise HTTPException(
                status_code=400,
                detail="整体花名册仅汇总各客户花名册：「客户」须能匹配到系统中的客户，或请到对应客户下的花名册中新增。",
            )
        data["customer_name"] = normalized_cn
        entry = RosterEntry(client_id=mc.id, **data)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        resequence_roster_serial_no(db, int(mc.id), RosterEntry)
        db.add(AuditLog(client_id=0, operator=user, action=f"整体花名册新增一行: {data.get('full_name') or ('#' + str(entry.id))}"))
        db.commit()
        db.refresh(entry)
        return roster_entry_to_dict(entry)

    @app.post("/api/clients/{client_id}/roster")
    async def roster_create_row(
        client_id: int,
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.write")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        data = normalize_roster_payload(body if isinstance(body, dict) else {})
        missing = [k for k in ROSTER_CREATE_REQUIRED_FIELDS if not str(data.get(k, "")).strip()]
        if missing:
            labels = [ROSTER_REQUIRED_LABELS.get(k, k) for k in missing]
            raise HTTPException(status_code=400, detail=f"新增失败，以下必填项未填写：{'、'.join(labels)}")
        validate_roster_business_fields(data)
        apply_roster_salary_quote_ratio(data)
        assert_roster_contact_unique(db, client_id, data.get("contact_info", ""), RosterEntry)
        mc, normalized_cn = resolve_roster_customer_client(db, data.get("customer_name", ""), Client)
        if mc:
            data["customer_name"] = normalized_cn
        entry = RosterEntry(client_id=client_id, **data)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        resequence_roster_serial_no(db, client_id, RosterEntry)
        log = AuditLog(client_id=client_id, operator=user, action=f"花名册新增一行: {data.get('full_name') or ('#' + str(entry.id))}")
        db.add(log)
        db.commit()
        db.refresh(entry)
        return roster_entry_to_dict(entry)

    @app.put("/api/roster/{row_id}")
    async def roster_update_row(
        row_id: int,
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.write")),
    ):
        entry = db.query(RosterEntry).filter(RosterEntry.id == row_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="记录不存在")
        old_cid = int(entry.client_id) if entry.client_id is not None else 0
        raw_body = body if isinstance(body, dict) else {}
        data = normalize_roster_payload(raw_body)
        for k in list(data.keys()):
            if k not in raw_body:
                data[k] = getattr(entry, k) or ""
        validate_roster_business_fields(data)
        apply_roster_salary_quote_ratio(data)
        mc, normalized_cn = resolve_roster_customer_client(db, data.get("customer_name", ""), Client)
        if mc:
            entry.client_id = mc.id
            data["customer_name"] = normalized_cn
        cid = int(entry.client_id) if entry.client_id is not None else 0
        interview_sync_n = 0
        if cid > 0 and "离职" in str(data.get("employment_status") or ""):
            sync_keys: Set[str] = {
                normalize_interview_name_fn(entry.full_name),
                normalize_interview_name_fn(data.get("full_name", "")),
            }
            sync_keys.discard("")
            if sync_keys:
                interview_sync_n = interview_mark_left_fn(db, cid, sync_keys)
        for k, v in data.items():
            setattr(entry, k, v)
        db.commit()
        db.refresh(entry)
        new_cid = int(entry.client_id) if entry.client_id is not None else 0
        for cid in {old_cid, new_cid}:
            resequence_roster_serial_no(db, cid, RosterEntry)
        action_msg = f"花名册修改行 id={row_id}"
        if interview_sync_n:
            action_msg += f"，同步员工访谈标离职 {interview_sync_n} 条（免校验）"
        log = AuditLog(client_id=entry.client_id, operator=user, action=action_msg)
        db.add(log)
        db.commit()
        db.refresh(entry)
        return roster_entry_to_dict(entry)

    @app.delete("/api/roster/{row_id}")
    async def roster_delete_row(
        row_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.delete")),
    ):
        entry = db.query(RosterEntry).filter(RosterEntry.id == row_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="记录不存在")
        cid = int(entry.client_id) if entry.client_id is not None else 0
        db.delete(entry)
        db.flush()
        resequence_roster_serial_no(db, cid, RosterEntry)
        db.commit()
        log = AuditLog(client_id=0, operator=user, action=f"整体花名册删除行 id={row_id}")
        db.add(log)
        db.commit()
        return {"status": "deleted"}

    # --- Import ---

    @app.post("/api/roster/import")
    async def roster_import_csv_all(
        file: UploadFile = File(...),
        confirm: str = Form(""),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.write")),
    ):
        def _skip_serial_hint(merged_row: Dict[str, str], csv_line_no: int) -> str:
            serial = (merged_row.get("serial_no") or "").strip()
            return serial if serial else f"CSV第{csv_line_no}行"

        raw = await file.read()
        if len(raw) > max_file_size:
            raise HTTPException(status_code=400, detail="文件超过大小限制")
        if str(confirm).strip().upper() != "CONFIRM":
            raise HTTPException(status_code=400, detail="导入前请确认覆盖操作（confirm=CONFIRM）")
        text = strip_excel_sep(decode_roster_upload_bytes(raw))
        header_info = analyze_roster_csv_headers(text)
        existing_rows = db.query(RosterEntry).order_by(RosterEntry.id).all()
        bk_file = write_roster_backup_csv_all(existing_rows, backup_dir) if existing_rows else ""
        active_cleared = (
            db.query(RosterEntry)
            .filter(sql_roster_employment_active_pool(RosterEntry))
            .delete(synchronize_session=False)
        )
        db.commit()
        cleared_existing = int(active_cleared or 0)

        imported = 0
        skipped_duplicates = 0
        skipped_empty = 0
        skipped_details: List[Dict[str, str]] = []
        seen_contact_keys: set = set()
        for row_index, mapped in enumerate(iter_roster_csv_data_rows(text), start=2):
            merged = normalize_roster_payload(mapped)
            if not any(merged.values()):
                skipped_empty += 1
                skipped_details.append({"serial_no": _skip_serial_hint(merged, row_index), "reason": "空行或全部字段为空"})
                continue
            ck = contact_dedup_key(merged.get("contact_info", ""))
            if ck:
                if ck in seen_contact_keys:
                    skipped_duplicates += 1
                    skipped_details.append({"serial_no": _skip_serial_hint(merged, row_index), "reason": "联系方式重复（文件内去重）", "contact_info": merged.get("contact_info", "")})
                    continue
                seen_contact_keys.add(ck)
            mc, normalized_cn = resolve_roster_customer_client(db, merged.get("customer_name", ""), Client)
            if mc:
                merged["customer_name"] = normalized_cn
            mapped_client_id = mc.id if mc else 0
            apply_roster_salary_quote_ratio(merged)
            db.add(RosterEntry(client_id=mapped_client_id, **merged))
            imported += 1
        resequence_roster_serial_no_all_clients(db, RosterEntry)
        db.commit()
        skip_total = skipped_duplicates + skipped_empty
        skip_brief = ""
        if skip_total:
            preview = "；".join([f"{x['serial_no']}({x['reason']})" for x in skipped_details[:8]])
            skip_brief = f"；跳过 {skip_total} 行：{preview}"
            if len(skipped_details) > 8:
                skip_brief += f"；其余 {len(skipped_details) - 8} 行见导入提示"
        db.add(AuditLog(client_id=0, operator=user, action=(
            f"整体花名册 CSV 导入前全量备份 {len(existing_rows)} 行到 {bk_file or '无备份'}，"
            f"清空在职池 {cleared_existing} 行（已离职档案未删），导入新增 {imported} 行"
            f"（文件内去重跳过 {skipped_duplicates} 行，空行跳过 {skipped_empty} 行）"
            f"{skip_brief}"
        )))
        db.commit()
        return {"cleared_existing": cleared_existing, "backup_file": bk_file, "imported": imported, "skipped_duplicates": skipped_duplicates, "skipped_empty": skipped_empty, "skipped_total": skip_total, "skipped_details": skipped_details, "matched_headers_count": len(header_info["matched_headers"]), "unmatched_headers": header_info["unmatched_headers"]}

    @app.post("/api/roster/turnover/import")
    async def roster_turnover_import_csv(
        file: UploadFile = File(...),
        confirm: str = Form(""),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.write")),
    ):
        def _skip_serial_hint(merged_row: Dict[str, str], csv_line_no: int) -> str:
            serial = (merged_row.get("serial_no") or "").strip()
            return serial if serial else f"CSV第{csv_line_no}行"

        raw = await file.read()
        if len(raw) > max_file_size:
            raise HTTPException(status_code=400, detail="文件超过大小限制")
        if str(confirm).strip().upper() != "CONFIRM":
            raise HTTPException(status_code=400, detail="导入前请确认覆盖操作（confirm=CONFIRM）")
        text = strip_excel_sep(decode_roster_upload_bytes(raw))
        header_info = analyze_roster_csv_headers(text)
        left_rows = roster_entries_turnover_pool(db, RosterEntry, Client)
        bk_file = write_roster_backup_turnover_csv_all(left_rows, backup_dir) if left_rows else ""
        left_cleared = db.query(RosterEntry).filter(sql_roster_employment_left(RosterEntry)).delete(synchronize_session=False)
        db.commit()
        cleared_existing = int(left_cleared or 0)

        imported = 0
        skipped_duplicates = 0
        skipped_empty = 0
        skipped_details: List[Dict[str, str]] = []
        seen_contact_keys: set = set()
        for row_index, mapped in enumerate(iter_roster_csv_data_rows(text), start=2):
            merged = normalize_roster_payload(mapped)
            if not any(merged.values()):
                skipped_empty += 1
                skipped_details.append({"serial_no": _skip_serial_hint(merged, row_index), "reason": "空行或全部字段为空"})
                continue
            ck = contact_dedup_key(merged.get("contact_info", ""))
            if ck:
                if ck in seen_contact_keys:
                    skipped_duplicates += 1
                    skipped_details.append({"serial_no": _skip_serial_hint(merged, row_index), "reason": "联系方式重复（文件内去重）", "contact_info": merged.get("contact_info", "")})
                    continue
                seen_contact_keys.add(ck)
            ensure_merged_turnover_employment(merged)
            mc, normalized_cn = resolve_roster_customer_client(db, merged.get("customer_name", ""), Client)
            if mc:
                merged["customer_name"] = normalized_cn
            mapped_client_id = mc.id if mc else 0
            apply_roster_salary_quote_ratio(merged)
            db.add(RosterEntry(client_id=mapped_client_id, **merged))
            imported += 1
        resequence_roster_serial_no_all_clients(db, RosterEntry)
        db.commit()
        skip_total = skipped_duplicates + skipped_empty
        skip_brief = ""
        if skip_total:
            preview = "；".join([f"{x['serial_no']}({x['reason']})" for x in skipped_details[:8]])
            skip_brief = f"；跳过 {skip_total} 行：{preview}"
            if len(skipped_details) > 8:
                skip_brief += f"；其余 {len(skipped_details) - 8} 行见导入提示"
        db.add(AuditLog(client_id=0, operator=user, action=(
            f"离职档案 CSV 导入前备份 {len(left_rows)} 行到 {bk_file or '无备份'}，"
            f"清空离职池 {cleared_existing} 行，导入新增 {imported} 行"
            f"（文件内去重跳过 {skipped_duplicates} 行，空行跳过 {skipped_empty} 行）"
            f"{skip_brief}"
        )))
        db.commit()
        return {"cleared_existing": cleared_existing, "backup_file": bk_file, "imported": imported, "skipped_duplicates": skipped_duplicates, "skipped_empty": skipped_empty, "skipped_total": skip_total, "skipped_details": skipped_details, "matched_headers_count": len(header_info["matched_headers"]), "unmatched_headers": header_info["unmatched_headers"]}

    @app.post("/api/clients/{client_id}/roster/import")
    async def roster_import_csv(
        client_id: int,
        file: UploadFile = File(...),
        confirm: str = Form(""),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.write")),
    ):
        def _skip_serial_hint(merged_row: Dict[str, str], csv_line_no: int) -> str:
            serial = (merged_row.get("serial_no") or "").strip()
            return serial if serial else f"CSV第{csv_line_no}行"

        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        raw = await file.read()
        if len(raw) > max_file_size:
            raise HTTPException(status_code=400, detail="文件超过大小限制")
        if str(confirm).strip().upper() != "CONFIRM":
            raise HTTPException(status_code=400, detail="导入前请确认覆盖操作（confirm=CONFIRM）")
        text = strip_excel_sep(decode_roster_upload_bytes(raw))
        header_info = analyze_roster_csv_headers(text)
        existing_rows = db.query(RosterEntry).filter(RosterEntry.client_id == client_id).order_by(RosterEntry.id).all()
        bk_file = write_roster_backup_csv(c, existing_rows, backup_dir, RosterEntry) if existing_rows else ""
        active_cleared = (
            db.query(RosterEntry)
            .filter(RosterEntry.client_id == client_id, sql_roster_employment_active_pool(RosterEntry))
            .delete(synchronize_session=False)
        )
        db.commit()
        cleared_existing = int(active_cleared or 0)

        imported = 0
        skipped_duplicates = 0
        skipped_empty = 0
        skipped_details: List[Dict[str, str]] = []
        seen_contact_keys: set = set()
        for row_index, mapped in enumerate(iter_roster_csv_data_rows(text), start=2):
            merged = normalize_roster_payload(mapped)
            if not any(merged.values()):
                skipped_empty += 1
                skipped_details.append({"serial_no": _skip_serial_hint(merged, row_index), "reason": "空行或全部字段为空"})
                continue
            ck = contact_dedup_key(merged.get("contact_info", ""))
            if ck:
                if ck in seen_contact_keys:
                    skipped_duplicates += 1
                    skipped_details.append({"serial_no": _skip_serial_hint(merged, row_index), "reason": "联系方式重复（文件内去重）", "contact_info": merged.get("contact_info", "")})
                    continue
                seen_contact_keys.add(ck)
            apply_roster_salary_quote_ratio(merged)
            entry = RosterEntry(client_id=client_id, **merged)
            db.add(entry)
            imported += 1
        resequence_roster_serial_no(db, client_id, RosterEntry)
        db.commit()
        skip_total = skipped_duplicates + skipped_empty
        skip_brief = ""
        if skip_total:
            preview = "；".join([f"{x['serial_no']}({x['reason']})" for x in skipped_details[:8]])
            skip_brief = f"；跳过 {skip_total} 行：{preview}"
            if len(skipped_details) > 8:
                skip_brief += f"；其余 {len(skipped_details) - 8} 行见导入提示"
        log = AuditLog(client_id=client_id, operator=user, action=(
            f"花名册 CSV 导入前全量备份 {len(existing_rows)} 行到 {bk_file or '无备份'}，"
            f"清空在职池 {cleared_existing} 行（该客户已离职档案未删），导入新增 {imported} 行"
            f"（文件内去重跳过 {skipped_duplicates} 行，空行跳过 {skipped_empty} 行）"
            f"{skip_brief}"
        ))
        db.add(log)
        if skipped_details:
            detail_lines = [f"{item['serial_no']}：{item['reason']}" for item in skipped_details]
            detail_text = "\n".join(detail_lines)
            db.add(AuditLog(client_id=client_id, operator=user, action=f"花名册导入跳过明细：\n{detail_text}"))
        db.commit()
        return {"cleared_existing": cleared_existing, "backup_file": bk_file, "imported": imported, "skipped_duplicates": skipped_duplicates, "skipped_empty": skipped_empty, "skipped_total": skip_total, "skipped_details": skipped_details, "matched_headers_count": len(header_info["matched_headers"]), "unmatched_headers": header_info["unmatched_headers"]}

    # --- Restore ---

    @app.post("/api/roster/restore/latest")
    async def roster_restore_latest_backup_all(
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.write")),
    ):
        latest = pick_latest_backup("roster_backup_all__")
        if not latest:
            raise HTTPException(status_code=404, detail="未找到整体花名册备份文件")
        backup_path = os.path.join(backup_dir, latest)
        with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
            text = f.read()
        text = strip_excel_sep(text)
        cleared_existing = db.query(RosterEntry).count()
        if cleared_existing:
            db.query(RosterEntry).delete()
            db.commit()
        restored_rows = 0
        for mapped in iter_roster_csv_data_rows(text):
            merged = normalize_roster_payload(mapped)
            if not any(merged.values()):
                continue
            mc, normalized_cn = resolve_roster_customer_client(db, merged.get("customer_name", ""), Client)
            if mc:
                merged["customer_name"] = normalized_cn
            mapped_client_id = mc.id if mc else 0
            apply_roster_salary_quote_ratio(merged)
            db.add(RosterEntry(client_id=mapped_client_id, **merged))
            restored_rows += 1
        resequence_roster_serial_no_all_clients(db, RosterEntry)
        db.commit()
        db.add(AuditLog(client_id=0, operator=user, action=f"整体花名册从备份恢复：{latest}，清空 {cleared_existing} 行，恢复 {restored_rows} 行"))
        db.commit()
        return {"backup_file": latest, "cleared_existing": cleared_existing, "restored_rows": restored_rows}

    @app.post("/api/clients/{client_id}/roster/restore/latest")
    async def roster_restore_latest_backup(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.write")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        latest = pick_latest_backup("roster_backup_", client_id=client_id)
        if not latest:
            raise HTTPException(status_code=404, detail="未找到该客户花名册备份文件")
        backup_path = os.path.join(backup_dir, latest)
        with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
            text = f.read()
        text = strip_excel_sep(text)
        cleared_existing = db.query(RosterEntry).filter(RosterEntry.client_id == client_id).count()
        if cleared_existing:
            db.query(RosterEntry).filter(RosterEntry.client_id == client_id).delete()
            db.commit()
        restored_rows = 0
        for mapped in iter_roster_csv_data_rows(text):
            merged = normalize_roster_payload(mapped)
            if not any(merged.values()):
                continue
            apply_roster_salary_quote_ratio(merged)
            db.add(RosterEntry(client_id=client_id, **merged))
            restored_rows += 1
        resequence_roster_serial_no(db, client_id, RosterEntry)
        db.commit()
        db.add(AuditLog(client_id=client_id, operator=user, action=f"花名册从备份恢复：{latest}，清空 {cleared_existing} 行，恢复 {restored_rows} 行"))
        db.commit()
        return {"backup_file": latest, "cleared_existing": cleared_existing, "restored_rows": restored_rows}

    @app.post("/api/roster/turnover/restore/latest")
    async def roster_turnover_restore_latest_backup_all(
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.roster.write")),
    ):
        latest = pick_latest_backup("roster_backup_turnover_all__")
        if not latest:
            raise HTTPException(status_code=404, detail="未找到离职档案备份文件")
        backup_path = os.path.join(backup_dir, latest)
        with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
            text = f.read()
        text = strip_excel_sep(text)
        left_before = roster_entries_turnover_pool(db, RosterEntry, Client)
        cleared_existing = len(left_before)
        if cleared_existing:
            db.query(RosterEntry).filter(sql_roster_employment_left(RosterEntry)).delete(synchronize_session=False)
            db.commit()
        restored_rows = 0
        for mapped in iter_roster_csv_data_rows(text):
            merged = normalize_roster_payload(mapped)
            if not any(merged.values()):
                continue
            ensure_merged_turnover_employment(merged)
            mc, normalized_cn = resolve_roster_customer_client(db, merged.get("customer_name", ""), Client)
            if mc:
                merged["customer_name"] = normalized_cn
            mapped_client_id = mc.id if mc else 0
            apply_roster_salary_quote_ratio(merged)
            db.add(RosterEntry(client_id=mapped_client_id, **merged))
            restored_rows += 1
        resequence_roster_serial_no_all_clients(db, RosterEntry)
        db.commit()
        db.add(AuditLog(client_id=0, operator=user, action=f"离职档案从备份恢复：{latest}，清空离职池 {cleared_existing} 行，恢复 {restored_rows} 行"))
        db.commit()
        return {"backup_file": latest, "cleared_existing": cleared_existing, "restored_rows": restored_rows}
