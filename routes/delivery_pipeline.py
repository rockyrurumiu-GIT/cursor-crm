"""Delivery Pipeline API routes — migrated from main.py (Phase 5B)."""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Type

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth.deps import require_permission
from schemas.delivery_pipeline import (
    PIPELINE_EXPORT_HEADERS,
    PIPELINE_HEADER_MAP,
    PIPELINE_IMPORT_HEADER_ALIASES,
)
from services.delivery_pipeline import (
    compute_pipeline_insight,
    normalize_pipeline_insight_demand_payload,
    normalize_pipeline_payload,
    pipeline_entry_to_dict,
    resequence_pipeline_serial_no,
    validate_pipeline_payload,
    write_pipeline_backup_csv,
)
from services.period_utils import period_sort_key


def register_delivery_pipeline_routes(
    app,
    *,
    get_db: Callable,
    Client: Type,
    PipelineEntry: Type,
    InsightDemand: Type,
    AuditLog: Type,
    backup_dir: str,
    max_file_size: int,
    strip_excel_sep: Callable[[str], str],
    decode_upload_bytes: Callable[[bytes], str],
    pick_latest_backup: Callable,
    set_csv_download_headers: Callable,
):
    # --- Read ---

    @app.get("/api/clients/{client_id}/delivery/pipeline/insight")
    async def pipeline_insight(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.pipeline.read")),
    ):
        return compute_pipeline_insight(db, client_id, Client, PipelineEntry, InsightDemand)

    @app.get("/api/clients/{client_id}/delivery/pipeline")
    async def pipeline_list(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.pipeline.read")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        rows = db.query(PipelineEntry).filter(PipelineEntry.client_id == client_id).all()
        row_dicts = [pipeline_entry_to_dict(r) for r in rows]
        row_dicts.sort(
            key=lambda x: (period_sort_key(str(x.get("date", ""))), int(x.get("id", 0) or 0)),
            reverse=True,
        )
        return row_dicts

    @app.get("/api/clients/{client_id}/delivery/pipeline/export")
    async def pipeline_export_csv(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.pipeline.read")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        rows = (
            db.query(PipelineEntry)
            .filter(PipelineEntry.client_id == client_id)
            .order_by(PipelineEntry.id)
            .all()
        )
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(PIPELINE_EXPORT_HEADERS)
        for e in rows:
            d = pipeline_entry_to_dict(e)
            writer.writerow([d.get(PIPELINE_HEADER_MAP[h], "") for h in PIPELINE_EXPORT_HEADERS])
        response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        set_csv_download_headers(response, chinese_filename=f"{c.name}_管道数据_{ts}.csv", ascii_base=f"client_{client_id}_pipeline_{ts}")
        return response

    @app.get("/api/clients/{client_id}/delivery/pipeline/logs")
    async def pipeline_logs(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.pipeline.read")),
    ):
        logs = (
            db.query(AuditLog)
            .filter(AuditLog.client_id == client_id)
            .filter(AuditLog.action.like("管道数据%"))
            .order_by(desc(AuditLog.created_at))
            .all()
        )
        return logs

    # --- Write ---

    @app.put("/api/clients/{client_id}/delivery/pipeline/insight-demand")
    async def pipeline_insight_update_demand(
        client_id: int,
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.pipeline.write")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        data = normalize_pipeline_insight_demand_payload(body if isinstance(body, dict) else {})
        period = data["period"]
        position = data["position"]
        region = data["region"]
        if not period or not position:
            raise HTTPException(status_code=400, detail="时间和岗位不能为空")
        entry = (
            db.query(InsightDemand)
            .filter(InsightDemand.client_id == client_id)
            .filter(InsightDemand.period == period)
            .filter(InsightDemand.position == position)
            .filter(InsightDemand.region == region)
            .first()
        )
        demand_qty = data["demand_qty"]
        if entry:
            if demand_qty:
                entry.demand_qty = demand_qty
            else:
                db.delete(entry)
        elif demand_qty:
            db.add(InsightDemand(client_id=client_id, period=period, position=position, region=region, demand_qty=demand_qty))
        db.commit()
        return {"status": "ok", "demand_qty": demand_qty}

    @app.post("/api/clients/{client_id}/delivery/pipeline")
    async def pipeline_create_row(
        client_id: int,
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.pipeline.write")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        data = normalize_pipeline_payload(body if isinstance(body, dict) else {})
        validate_pipeline_payload(data, context="管道数据新增")
        max_row = (
            db.query(PipelineEntry)
            .filter(PipelineEntry.client_id == client_id)
            .order_by(desc(PipelineEntry.id))
            .first()
        )
        if max_row and str(max_row.serial_no or "").isdigit():
            data["serial_no"] = str(int(max_row.serial_no) + 1)
        else:
            data["serial_no"] = "1"
        entry = PipelineEntry(client_id=client_id, **data)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        db.add(AuditLog(client_id=client_id, operator=user, action=f"管道数据新增行 id={entry.id}"))
        db.commit()
        return pipeline_entry_to_dict(entry)

    @app.put("/api/delivery/pipeline/row/{row_id}")
    async def pipeline_update_row(
        row_id: int,
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.pipeline.write")),
    ):
        entry = db.query(PipelineEntry).filter(PipelineEntry.id == row_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="记录不存在")
        data = normalize_pipeline_payload(body if isinstance(body, dict) else {})
        validate_pipeline_payload(data, context="管道数据修改")
        for k, v in data.items():
            if k == "serial_no":
                continue
            setattr(entry, k, v)
        db.commit()
        db.refresh(entry)
        db.add(AuditLog(client_id=entry.client_id, operator=user, action=f"管道数据修改行 id={row_id}"))
        db.commit()
        return pipeline_entry_to_dict(entry)

    @app.delete("/api/delivery/pipeline/row/{row_id}")
    async def pipeline_delete_row(
        row_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.pipeline.write")),
    ):
        entry = db.query(PipelineEntry).filter(PipelineEntry.id == row_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="记录不存在")
        cid = entry.client_id
        db.delete(entry)
        db.flush()
        resequence_pipeline_serial_no(db, cid, PipelineEntry)
        db.commit()
        db.add(AuditLog(client_id=cid, operator=user, action=f"管道数据删除行 id={row_id}"))
        db.commit()
        return {"status": "deleted"}

    # --- Import ---

    @app.post("/api/clients/{client_id}/delivery/pipeline/import")
    async def pipeline_import_csv(
        client_id: int,
        file: UploadFile = File(...),
        confirm: str = Form(""),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.pipeline.write")),
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
            return str(h or "").replace("\ufeff", "").replace(" ", "").replace("\u3000", "").strip().lower()

        norm_map = {_norm_header(hk): fk for hk, fk in PIPELINE_HEADER_MAP.items()}
        for alias_hk, fk in PIPELINE_IMPORT_HEADER_ALIASES.items():
            norm_map[_norm_header(alias_hk)] = fk

        matched_columns = {}
        for original_h in reader.fieldnames:
            fk = norm_map.get(_norm_header(original_h))
            if fk and fk not in matched_columns:
                matched_columns[fk] = original_h

        matched_non_serial = [k for k in matched_columns.keys() if k != "serial_no"]
        if not matched_non_serial:
            raise HTTPException(
                status_code=400,
                detail=f"CSV 表头未匹配到管道数据字段（仅匹配到序号或未匹配）。检测到表头: {', '.join([str(h or '') for h in reader.fieldnames])}",
            )

        pending_rows: List[Dict[str, str]] = []
        total_rows = 0
        skipped_empty_rows = 0
        skipped_empty_row_numbers: List[int] = []
        for row in reader:
            total_rows += 1
            csv_line_no = total_rows + 1
            mapped = {fk: "" for fk in PIPELINE_HEADER_MAP.values()}
            for fk, original_h in matched_columns.items():
                mapped[fk] = str(row.get(original_h, "") or "").strip()
            mapped["serial_no"] = ""
            mapped = normalize_pipeline_payload(mapped)
            if not any(mapped.get(k, "") for k in matched_non_serial):
                skipped_empty_rows += 1
                if len(skipped_empty_row_numbers) < 20:
                    skipped_empty_row_numbers.append(csv_line_no)
                continue
            validate_pipeline_payload(mapped, context="管道数据CSV导入", row_hint=f"第{csv_line_no}行")
            pending_rows.append(mapped)

        existing_rows = (
            db.query(PipelineEntry)
            .filter(PipelineEntry.client_id == client_id)
            .order_by(PipelineEntry.id)
            .all()
        )
        cleared_existing = len(existing_rows)
        bk_file = write_pipeline_backup_csv(c, existing_rows, backup_dir) if cleared_existing else ""
        if cleared_existing:
            db.query(PipelineEntry).filter(PipelineEntry.client_id == client_id).delete()
            db.commit()

        imported = 0
        for mapped in pending_rows:
            entry = PipelineEntry(client_id=client_id, **mapped)
            db.add(entry)
            imported += 1
        resequence_pipeline_serial_no(db, client_id, PipelineEntry)
        db.commit()
        db.add(AuditLog(client_id=client_id, operator=user, action=(
            f"管道数据 CSV 导入前备份 {cleared_existing} 行到 {bk_file or '无备份'}，"
            f"清空 {cleared_existing} 行，CSV 总行数 {total_rows}，"
            f"空行跳过 {skipped_empty_rows}，导入新增 {imported} 行"
        )))
        db.commit()
        return {
            "cleared_existing": cleared_existing,
            "backup_file": bk_file,
            "imported": imported,
            "total_rows": total_rows,
            "skipped_empty_rows": skipped_empty_rows,
            "skipped_rows": skipped_empty_rows,
            "skipped_empty_row_numbers_preview": skipped_empty_row_numbers,
            "skipped_empty_row_numbers_truncated": skipped_empty_rows > len(skipped_empty_row_numbers),
            "matched_columns_count": len(matched_non_serial),
            "matched_columns": sorted(matched_non_serial),
        }

    @app.post("/api/delivery/pipeline/import")
    async def pipeline_import_csv_global(
        client_id: int = Form(...),
        file: UploadFile = File(...),
        confirm: str = Form(""),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.pipeline.write")),
    ):
        return await pipeline_import_csv(
            client_id=client_id, file=file, confirm=confirm, db=db, user=user,
        )

    # --- Restore ---

    @app.post("/api/clients/{client_id}/delivery/pipeline/restore/latest")
    async def pipeline_restore_latest_backup(
        client_id: int,
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.pipeline.write")),
    ):
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="客户不存在")
        latest = pick_latest_backup("pipeline_backup_", client_id=client_id)
        if not latest:
            raise HTTPException(status_code=404, detail="未找到该客户管道数据备份文件")
        backup_path = os.path.join(backup_dir, latest)
        with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        cleared_existing = db.query(PipelineEntry).filter(PipelineEntry.client_id == client_id).count()
        if cleared_existing:
            db.query(PipelineEntry).filter(PipelineEntry.client_id == client_id).delete()
            db.commit()
        restored_rows = 0
        for row in rows:
            mapped = {fk: "" for fk in set(PIPELINE_HEADER_MAP.values())}
            for hk, fk in PIPELINE_HEADER_MAP.items():
                cell = str(row.get(hk, "") or "").strip()
                if cell:
                    mapped[fk] = cell
            mapped["serial_no"] = ""
            if not any(mapped.values()):
                continue
            db.add(PipelineEntry(client_id=client_id, **mapped))
            restored_rows += 1
        resequence_pipeline_serial_no(db, client_id, PipelineEntry)
        db.commit()
        db.add(AuditLog(client_id=client_id, operator=user, action=f"管道数据从备份恢复：{latest}，清空 {cleared_existing} 行，恢复 {restored_rows} 行"))
        db.commit()
        return {"backup_file": latest, "cleared_existing": cleared_existing, "restored_rows": restored_rows}
