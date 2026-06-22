"""Delivery Interviews API routes — migrated from main.py (Phase 5C)."""
from __future__ import annotations

import csv
import io
import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Type

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth.deps import _require_super_admin, require_permission
from auth.service import AuthContext
from schemas.delivery_interviews import (
    INTERVIEW_EXPORT_HEADERS,
    INTERVIEW_HEADER_MAP,
    INTERVIEW_IMPORT_ALIASES,
)
from services.csv_utils import strip_csv_header_noise
from services.delivery_interviews import (
    assert_interview_delivery_judgment_unique,
    interview_display_serial_pairs,
    interview_entry_to_dict,
    interview_mark_left_for_normalized_name_keys,
    normalize_interview_payload,
    normalize_interview_person_name,
    resequence_interview_serial_no,
    validate_interview_business_fields,
    write_interview_backup_csv,
)


def register_delivery_interviews_routes(
    app,
    *,
    get_db: Callable,
    Client: Type,
    InterviewEntry: Type,
    AuditLog: Type,
    backup_dir: str,
    max_file_size: int,
    strip_excel_sep: Callable[[str], str],
    decode_upload_bytes: Callable[[bytes], str],
    pick_latest_backup: Callable,
    set_csv_download_headers: Callable,
):
    # --- List ---

    @app.get("/api/clients/{client_id}/delivery/interviews")
    async def interview_list(client_id: int, db: Session = Depends(get_db), user: str = Depends(require_permission("delivery.interviews.read"))):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        rows = (
            db.query(InterviewEntry)
            .filter(InterviewEntry.client_id == client_id)
            .order_by(InterviewEntry.id)
            .all()
        )
        return [interview_entry_to_dict(r) for r in rows]

    # --- List (aggregate across all clients, read-only) ---

    @app.get("/api/delivery/interviews/all")
    async def interview_list_all(db: Session = Depends(get_db), user: str = Depends(require_permission("delivery.interviews.read"))):
        rows = (
            db.query(InterviewEntry, Client.name)
            .join(Client, Client.id == InterviewEntry.client_id)
            .order_by(Client.name, InterviewEntry.id)
            .all()
        )
        out: List[Dict[str, Any]] = []
        for entry, client_name in rows:
            d = interview_entry_to_dict(entry)
            d["client_name"] = client_name or ""
            out.append(d)
        return out

    # --- Create ---

    @app.post("/api/clients/{client_id}/delivery/interviews")
    async def interview_create_row(
        client_id: int,
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.interviews.write")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        data = normalize_interview_payload(body if isinstance(body, dict) else {})
        validate_interview_business_fields(data)
        assert_interview_delivery_judgment_unique(db, client_id, data.get("full_name", ""), data.get("delivery_judgment", ""), InterviewEntry)
        max_row = (
            db.query(InterviewEntry)
            .filter(InterviewEntry.client_id == client_id)
            .order_by(desc(InterviewEntry.id))
            .first()
        )
        if max_row and str(max_row.serial_no or "").isdigit():
            data["serial_no"] = str(int(max_row.serial_no) + 1)
        else:
            data["serial_no"] = "1"
        entry = InterviewEntry(client_id=client_id, **data)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        db.add(AuditLog(client_id=client_id, operator=user, action=f"员工访谈新增行 id={entry.id}"))
        db.commit()
        return interview_entry_to_dict(entry)

    # --- Mark Employment Left ---

    @app.post("/api/clients/{client_id}/delivery/interviews/mark-employment-left")
    async def interview_mark_employment_left_by_name(
        client_id: int,
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.interviews.write")),
    ):
        """提示「已离职」等场景：仅改在职/离职，不校验交付判断等必填（与 PUT 行接口区分）。"""
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        raw = body if isinstance(body, dict) else {}
        needle = normalize_interview_person_name(raw.get("full_name", ""))
        if not needle:
            raise HTTPException(status_code=400, detail="请提供员工姓名")
        matched = interview_mark_left_for_normalized_name_keys(db, client_id, {needle}, InterviewEntry)
        db.commit()
        if matched:
            label = needle if len(needle) <= 60 else needle[:57] + "..."
            db.add(
                AuditLog(
                    client_id=client_id,
                    operator=user,
                    action=f"员工访谈标离职（免校验）匹配「{label}」共 {matched} 条",
                )
            )
            db.commit()
        return {"updated": matched}

    # --- Update ---

    @app.put("/api/delivery/interviews/row/{row_id}")
    async def interview_update_row(
        row_id: int,
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.interviews.write")),
    ):
        entry = db.query(InterviewEntry).filter(InterviewEntry.id == row_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="记录不存在")
        data = normalize_interview_payload(body if isinstance(body, dict) else {})
        validate_interview_business_fields(data)
        assert_interview_delivery_judgment_unique(
            db,
            entry.client_id,
            data.get("full_name", ""),
            data.get("delivery_judgment", ""),
            InterviewEntry,
            exclude_row_id=row_id,
        )
        for k, v in data.items():
            if k == "serial_no":
                continue
            setattr(entry, k, v)
        db.commit()
        db.refresh(entry)
        db.add(AuditLog(client_id=entry.client_id, operator=user, action=f"员工访谈修改行 id={row_id}"))
        db.commit()
        return interview_entry_to_dict(entry)

    # --- Delete ---

    @app.delete("/api/delivery/interviews/row/{row_id}")
    async def interview_delete_row(row_id: int, db: Session = Depends(get_db), user: str = Depends(require_permission("delivery.interviews.delete"))):
        entry = db.query(InterviewEntry).filter(InterviewEntry.id == row_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="记录不存在")
        cid = entry.client_id
        db.delete(entry)
        db.flush()
        resequence_interview_serial_no(db, cid, InterviewEntry)
        db.commit()
        db.add(AuditLog(client_id=cid, operator=user, action=f"员工访谈删除行 id={row_id}"))
        db.commit()
        return {"status": "deleted"}

    # --- Import ---

    @app.post("/api/clients/{client_id}/delivery/interviews/import")
    async def interview_import_csv(
        client_id: int,
        file: UploadFile = File(...),
        confirm: str = Form(""),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.interviews.write")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        raw = await file.read()
        if len(raw) > max_file_size:
            raise HTTPException(status_code=400, detail="文件超过大小限制")
        if str(confirm).strip().upper() != "CONFIRM":
            raise HTTPException(status_code=400, detail="导入前请确认覆盖操作（confirm=CONFIRM）")
        text = strip_excel_sep(decode_upload_bytes(raw))
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV 缺少表头，无法导入")

        def _norm_header(h: str) -> str:
            s = strip_csv_header_noise(h)
            s = re.sub(r"\s+", "", s)
            for plus_ch in ("\uff0b", "\u2795", "\u229e", "\u208a"):
                s = s.replace(plus_ch, "+")
            return s.strip().lower()

        norm_map: Dict[str, str] = {}
        for hk, fk in INTERVIEW_HEADER_MAP.items():
            norm_map[_norm_header(hk)] = fk
        for alias_hk, fk in INTERVIEW_IMPORT_ALIASES.items():
            norm_map[_norm_header(alias_hk)] = fk

        matched_columns: Dict[str, str] = {}
        for original_h in reader.fieldnames:
            normalized_h = _norm_header(original_h)
            fk = norm_map.get(normalized_h)
            if not fk:
                if ("员工" in normalized_h and "1" in normalized_h and any(token in normalized_h for token in ("加", "+", "q"))):
                    fk = "employee_q1"
            if fk and fk not in matched_columns:
                matched_columns[fk] = original_h

        matched_non_serial = [k for k in matched_columns.keys() if k != "serial_no"]
        if not matched_non_serial:
            raise HTTPException(
                status_code=400,
                detail=(
                    "CSV 表头未匹配到员工访谈字段（仅匹配到序号或未匹配）。检测到表头: "
                    + ", ".join([str(h or "") for h in reader.fieldnames])
                ),
            )

        interview_fk_set = set(INTERVIEW_HEADER_MAP.values())

        pending_rows: List[Dict[str, str]] = []
        total_rows = 0
        skipped_empty_rows = 0
        skipped_empty_row_numbers: List[int] = []
        for row in reader:
            total_rows += 1
            csv_line_no = total_rows + 1
            mapped = {fk: "" for fk in interview_fk_set}
            for fk, original_h in matched_columns.items():
                mapped[fk] = str(row.get(original_h, "") or "").strip()
            mapped["serial_no"] = ""
            if not any(mapped.get(k, "") for k in matched_non_serial):
                skipped_empty_rows += 1
                if len(skipped_empty_row_numbers) < 20:
                    skipped_empty_row_numbers.append(csv_line_no)
                continue
            pending_rows.append(mapped)

        existing_rows = (
            db.query(InterviewEntry)
            .filter(InterviewEntry.client_id == client_id)
            .order_by(InterviewEntry.id)
            .all()
        )
        cleared_existing = len(existing_rows)
        backup_file = write_interview_backup_csv(c, existing_rows, backup_dir) if cleared_existing else ""
        if cleared_existing:
            db.query(InterviewEntry).filter(InterviewEntry.client_id == client_id).delete()
            db.commit()

        imported = 0
        for mapped in pending_rows:
            entry = InterviewEntry(client_id=client_id, **mapped)
            db.add(entry)
            imported += 1
        resequence_interview_serial_no(db, client_id, InterviewEntry)
        db.commit()
        db.add(
            AuditLog(
                client_id=client_id,
                operator=user,
                action=(
                    f"员工访谈 CSV 导入前备份 {cleared_existing} 行到 {backup_file or '无备份'}，"
                    f"清空 {cleared_existing} 行，CSV 总行数 {total_rows}，"
                    f"空行跳过 {skipped_empty_rows}，导入新增 {imported} 行"
                ),
            )
        )
        db.commit()
        return {
            "cleared_existing": cleared_existing,
            "backup_file": backup_file,
            "imported": imported,
            "total_rows": total_rows,
            "skipped_empty_rows": skipped_empty_rows,
            "skipped_rows": skipped_empty_rows,
            "skipped_empty_row_numbers_preview": skipped_empty_row_numbers,
            "skipped_empty_row_numbers_truncated": skipped_empty_rows > len(skipped_empty_row_numbers),
            "matched_columns_count": len(matched_non_serial),
            "matched_columns": sorted(matched_non_serial),
        }

    # --- Import (global form) ---

    @app.post("/api/delivery/interviews/import")
    async def interview_import_csv_global(
        client_id: int = Form(...),
        file: UploadFile = File(...),
        confirm: str = Form(""),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.interviews.write")),
    ):
        return await interview_import_csv(
            client_id=client_id,
            file=file,
            confirm=confirm,
            db=db,
            user=user,
        )

    # --- Export ---

    @app.get("/api/clients/{client_id}/delivery/interviews/export")
    async def interview_export_csv(client_id: int, db: Session = Depends(get_db), user: str = Depends(require_permission("delivery.interviews.read"))):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        rows = (
            db.query(InterviewEntry)
            .filter(InterviewEntry.client_id == client_id)
            .order_by(InterviewEntry.id)
            .all()
        )
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(INTERVIEW_EXPORT_HEADERS)
        for sn, e in interview_display_serial_pairs(rows):
            d = interview_entry_to_dict(e)
            cells = [str(sn)] + [d.get(INTERVIEW_HEADER_MAP[h], "") for h in INTERVIEW_EXPORT_HEADERS[1:]]
            writer.writerow(cells)
        response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        set_csv_download_headers(
            response,
            chinese_filename=f"{c.name}_员工访谈_{ts}.csv",
            ascii_base=f"client_{client_id}_interviews_{ts}",
        )
        return response

    # --- Export (aggregate across all clients, read-only) ---

    @app.get("/api/delivery/interviews/export/all")
    async def interview_export_csv_all(db: Session = Depends(get_db), user: str = Depends(require_permission("delivery.interviews.read"))):
        clients = (
            db.query(Client.id, Client.name)
            .join(InterviewEntry, InterviewEntry.client_id == Client.id)
            .distinct()
            .order_by(Client.name)
            .all()
        )
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(["客户"] + INTERVIEW_EXPORT_HEADERS)
        for cid, cname in clients:
            rows = (
                db.query(InterviewEntry)
                .filter(InterviewEntry.client_id == cid)
                .order_by(InterviewEntry.id)
                .all()
            )
            for sn, e in interview_display_serial_pairs(rows):
                d = interview_entry_to_dict(e)
                cells = [cname or "", str(sn)] + [d.get(INTERVIEW_HEADER_MAP[h], "") for h in INTERVIEW_EXPORT_HEADERS[1:]]
                writer.writerow(cells)
        response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        set_csv_download_headers(
            response,
            chinese_filename=f"整体员工访谈_{ts}.csv",
            ascii_base=f"interviews_all_{ts}",
        )
        return response

    # --- Logs ---

    @app.get("/api/clients/{client_id}/delivery/interviews/logs")
    async def interview_logs(
        client_id: int,
        db: Session = Depends(get_db),
        _ctx: AuthContext = Depends(_require_super_admin),
    ):
        logs = (
            db.query(AuditLog)
            .filter(AuditLog.client_id == client_id)
            .filter(AuditLog.action.like("员工访谈%"))
            .order_by(desc(AuditLog.created_at))
            .all()
        )
        return logs

    # --- Restore ---

    @app.post("/api/clients/{client_id}/delivery/interviews/restore/latest")
    async def interview_restore_latest_backup(client_id: int, db: Session = Depends(get_db), user: str = Depends(require_permission("delivery.interviews.write"))):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        latest = pick_latest_backup("interview_backup_", client_id=client_id)
        if not latest:
            raise HTTPException(status_code=404, detail="未找到该客户员工访谈备份文件")
        backup_path = os.path.join(backup_dir, latest)
        with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        cleared_existing = db.query(InterviewEntry).filter(InterviewEntry.client_id == client_id).count()
        if cleared_existing:
            db.query(InterviewEntry).filter(InterviewEntry.client_id == client_id).delete()
            db.commit()
        restored_rows = 0
        for row in rows:
            mapped = {fk: "" for fk in set(INTERVIEW_HEADER_MAP.values())}
            for hk, fk in INTERVIEW_HEADER_MAP.items():
                cell = str(row.get(hk, "") or "").strip()
                if cell:
                    mapped[fk] = cell
            mapped["serial_no"] = ""
            if not any(mapped.values()):
                continue
            db.add(InterviewEntry(client_id=client_id, **mapped))
            restored_rows += 1
        resequence_interview_serial_no(db, client_id, InterviewEntry)
        db.commit()
        db.add(
            AuditLog(
                client_id=client_id,
                operator=user,
                action=f"员工访谈从备份恢复：{latest}，清空 {cleared_existing} 行，恢复 {restored_rows} 行",
            )
        )
        db.commit()
        return {"backup_file": latest, "cleared_existing": cleared_existing, "restored_rows": restored_rows}
