"""Delivery Settlement API routes — migrated from main.py (Phase 2)."""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type
from urllib.parse import quote

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth import data_scope as ds
from auth.data_scope_catalog import RESOURCE_DELIVERY_SETTLEMENT
from auth.deps import _require_super_admin, get_current_context, require_permission
from auth.service import AuthContext
from services.delivery_settlement import (
    SETTLEMENT_EXPORT_HEADERS,
    SETTLEMENT_HEADER_MAP,
    normalize_settlement_payload,
    resequence_settlement_serial_no_all,
    resolve_settlement_client_id,
    settlement_dedup_key,
    settlement_entry_to_dict,
    validate_settlement_payload,
    write_settlement_backup_csv,
)


def register_delivery_settlement_routes(
    app,
    *,
    get_db: Callable,
    Client,
    DeliverySettlementEntry,
    AuditLog,
    backup_dir: str,
    max_file_size: int,
    decode_upload_bytes: Callable,
    strip_excel_sep: Callable,
    pick_latest_backup: Callable,
    set_csv_download_headers: Callable,
):
    @app.get("/api/delivery/settlement")
    async def settlement_list(
        db: Session = Depends(get_db),
        ctx: AuthContext = Depends(get_current_context),
        user: str = Depends(require_permission("delivery.settlement.read")),
    ):
        q = db.query(DeliverySettlementEntry).order_by(DeliverySettlementEntry.id)
        q = ds.filter_query_by_client_scope(
            q, db, ctx, RESOURCE_DELIVERY_SETTLEMENT, "read", DeliverySettlementEntry.client_id, Client
        )
        rows = q.all()
        return [settlement_entry_to_dict(r) for r in rows]

    @app.post("/api/delivery/settlement")
    async def settlement_create_row(
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.settlement.write")),
    ):
        data = normalize_settlement_payload(body if isinstance(body, dict) else {})
        validate_settlement_payload(data)
        client_id = resolve_settlement_client_id(db, data.get("customer_name", ""), Client, require_existing=False)
        max_id_row = db.query(DeliverySettlementEntry).order_by(desc(DeliverySettlementEntry.id)).first()
        if max_id_row and str(max_id_row.serial_no or "").isdigit():
            data["serial_no"] = str(int(max_id_row.serial_no) + 1)
        else:
            data["serial_no"] = "1"
        entry = DeliverySettlementEntry(client_id=client_id, **data)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        db.add(AuditLog(client_id=client_id or 0, operator=user, action=f"结算回款新增: {data.get('customer_name', '')}"))
        db.commit()
        return settlement_entry_to_dict(entry)

    @app.put("/api/delivery/settlement/row/{row_id}")
    async def settlement_update_row(
        row_id: int,
        body: Dict[str, Any] = Body(default={}),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.settlement.write")),
    ):
        entry = db.query(DeliverySettlementEntry).filter(DeliverySettlementEntry.id == row_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="记录不存在")
        data = normalize_settlement_payload(body if isinstance(body, dict) else {})
        validate_settlement_payload(data)
        entry.client_id = resolve_settlement_client_id(db, data.get("customer_name", ""), Client, require_existing=False)
        for k, v in data.items():
            if k == "serial_no":
                continue
            setattr(entry, k, v)
        db.commit()
        db.refresh(entry)
        db.add(AuditLog(client_id=entry.client_id or 0, operator=user, action=f"结算回款修改行 id={row_id}"))
        db.commit()
        return settlement_entry_to_dict(entry)

    @app.delete("/api/delivery/settlement/row/{row_id}")
    async def settlement_delete_row(row_id: int, db: Session = Depends(get_db), user: str = Depends(require_permission("delivery.settlement.delete"))):
        entry = db.query(DeliverySettlementEntry).filter(DeliverySettlementEntry.id == row_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="记录不存在")
        cid = entry.client_id or 0
        db.delete(entry)
        db.flush()
        resequence_settlement_serial_no_all(db, DeliverySettlementEntry)
        db.commit()
        db.add(AuditLog(client_id=cid, operator=user, action=f"结算回款删除行 id={row_id}"))
        db.commit()
        return {"status": "deleted"}

    @app.post("/api/delivery/settlement/import")
    async def settlement_import_csv(
        file: UploadFile = File(...),
        confirm: str = Form(""),
        db: Session = Depends(get_db),
        user: str = Depends(require_permission("delivery.settlement.write")),
    ):
        raw = await file.read()
        if len(raw) > max_file_size:
            raise HTTPException(status_code=400, detail="文件超过大小限制")
        if str(confirm).strip().upper() != "CONFIRM":
            raise HTTPException(status_code=400, detail="导入前请确认覆盖操作（confirm=CONFIRM）")
        text = strip_excel_sep(decode_upload_bytes(raw))
        existing_rows = db.query(DeliverySettlementEntry).order_by(DeliverySettlementEntry.id).all()
        cleared_existing = len(existing_rows)
        backup_file = write_settlement_backup_csv(existing_rows, backup_dir) if cleared_existing else ""
        if cleared_existing:
            db.query(DeliverySettlementEntry).delete()
            db.commit()
        reader = csv.DictReader(io.StringIO(text))
        imported = 0
        skipped_duplicates = 0
        skipped_details: List[Dict[str, str]] = []
        seen_keys: set = set()
        for row_index, row in enumerate(reader, start=2):
            mapped: Dict[str, str] = {}
            for hk, fk in SETTLEMENT_HEADER_MAP.items():
                mapped[fk] = str(row.get(hk, "") or "").strip()
            mapped["serial_no"] = ""
            if not any(mapped.values()):
                continue
            dedup_key = settlement_dedup_key(
                mapped.get("customer_name", ""),
                mapped.get("fee_month", ""),
                mapped.get("amount", ""),
                mapped.get("remarks", ""),
            )
            if dedup_key:
                if dedup_key in seen_keys:
                    skipped_duplicates += 1
                    shown = mapped.get("serial_no", "").strip() or f"CSV第{row_index}行"
                    skipped_details.append(
                        {
                            "serial_no": shown,
                            "reason": (
                                "客户+费用月份+金额+备注重复"
                                f"（{mapped.get('customer_name', '')} / {mapped.get('fee_month', '')} / {mapped.get('amount', '')} / {mapped.get('remarks', '')}）"
                            ),
                        }
                    )
                    continue
                seen_keys.add(dedup_key)
            validate_settlement_payload(mapped)
            client_id = resolve_settlement_client_id(db, mapped.get("customer_name", ""), Client, require_existing=False)
            entry = DeliverySettlementEntry(client_id=client_id, **mapped)
            db.add(entry)
            imported += 1
        db.flush()
        resequence_settlement_serial_no_all(db, DeliverySettlementEntry)
        db.commit()
        skip_total = skipped_duplicates
        log = AuditLog(
            client_id=0,
            operator=user,
            action=(
                f"结算回款 CSV 导入前备份 {cleared_existing} 行到 {backup_file or '无备份'}，"
                f"清空 {cleared_existing} 行，导入新增 {imported} 行（按客户+费用月份+金额+备注去重跳过 {skipped_duplicates} 行）"
            ),
        )
        db.add(log)
        if skipped_details:
            detail_lines = [f"{item['serial_no']}：{item['reason']}" for item in skipped_details]
            detail_log = AuditLog(
                client_id=0,
                operator=user,
                action=f"结算回款导入跳过明细：\n" + "\n".join(detail_lines),
            )
            db.add(detail_log)
        db.commit()
        return {
            "cleared_existing": cleared_existing,
            "backup_file": backup_file,
            "imported": imported,
            "skipped_duplicates": skipped_duplicates,
            "skipped_total": skip_total,
            "skipped_details": skipped_details,
        }

    @app.get("/api/delivery/settlement/export")
    async def settlement_export_csv(db: Session = Depends(get_db), user: str = Depends(require_permission("delivery.settlement.read"))):
        rows = db.query(DeliverySettlementEntry).order_by(DeliverySettlementEntry.id).all()
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(SETTLEMENT_EXPORT_HEADERS)
        for e in rows:
            d = settlement_entry_to_dict(e)
            writer.writerow([d.get(SETTLEMENT_HEADER_MAP[h], "") for h in SETTLEMENT_EXPORT_HEADERS])
        response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"结算回款_{ts}.csv"
        set_csv_download_headers(
            response,
            chinese_filename=filename,
            ascii_base=f"settlement_{ts}",
        )
        return response

    @app.get("/api/delivery/settlement/logs")
    async def settlement_logs(
        db: Session = Depends(get_db),
        _ctx: AuthContext = Depends(_require_super_admin),
    ):
        logs = (
            db.query(AuditLog)
            .filter(AuditLog.action.like("结算回款%"))
            .order_by(desc(AuditLog.created_at))
            .all()
        )
        return logs

    @app.post("/api/delivery/settlement/restore/latest")
    async def settlement_restore_latest_backup(db: Session = Depends(get_db), user: str = Depends(require_permission("delivery.settlement.write"))):
        latest = pick_latest_backup("settlement_backup_")
        if not latest:
            raise HTTPException(status_code=404, detail="未找到结算回款备份文件")
        backup_path = os.path.join(backup_dir, latest)

        with open(backup_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        cleared_existing = db.query(DeliverySettlementEntry).count()
        if cleared_existing:
            db.query(DeliverySettlementEntry).delete()
            db.commit()

        restored_rows = 0
        for row in rows:
            mapped: Dict[str, str] = {}
            for hk, fk in SETTLEMENT_HEADER_MAP.items():
                mapped[fk] = str(row.get(hk, "") or "").strip()
            if not any(mapped.values()):
                continue
            validate_settlement_payload(mapped)
            client_id = resolve_settlement_client_id(db, mapped.get("customer_name", ""), Client, require_existing=False)
            entry = DeliverySettlementEntry(client_id=client_id, **mapped)
            db.add(entry)
            restored_rows += 1
        db.flush()
        resequence_settlement_serial_no_all(db, DeliverySettlementEntry)
        db.commit()
        db.add(
            AuditLog(
                client_id=0,
                operator=user,
                action=f"结算回款从备份恢复：{latest}，清空 {cleared_existing} 行，恢复 {restored_rows} 行",
            )
        )
        db.commit()
        return {"backup_file": latest, "cleared_existing": cleared_existing, "restored_rows": restored_rows}
