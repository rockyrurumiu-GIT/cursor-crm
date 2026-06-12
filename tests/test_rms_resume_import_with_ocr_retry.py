"""RMS Phase 3D-1F: import + OCR retry wrapper."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

MODULE = "scripts.import_rms_resumes_with_ocr_retry"


@pytest.fixture
def wrapper_mod():
    if MODULE in sys.modules:
        return sys.modules[MODULE]
    return importlib.import_module(MODULE)


@pytest.fixture
def fake_import_result(tmp_path):
    report_csv = tmp_path / "import.csv"
    report_csv.write_text("file_path\n", encoding="utf-8")
    return {
        "scanned": 2,
        "would_create": 1,
        "created": 0,
        "skipped_duplicate": 0,
        "skipped_unparseable": 1,
        "failed": 0,
        "report_csv": str(report_csv),
        "report_json": str(tmp_path / "import.json"),
    }


@pytest.fixture
def fake_ocr_result(tmp_path):
    return {
        "scanned": 2,
        "ocr_attempted": 1,
        "would_update": 1,
        "updated": 0,
        "would_create": 0,
        "created": 0,
        "skipped_duplicate": 0,
        "skipped_unparseable": 0,
        "conflict": 0,
        "failed": 0,
        "report_csv": str(tmp_path / "ocr.csv"),
        "report_json": str(tmp_path / "ocr.json"),
    }


def _run_wrapper(
    wrapper_mod,
    monkeypatch,
    tmp_path,
    *,
    import_result,
    ocr_result,
    dry_run: bool = True,
    commit: bool = False,
    limit: int | None = None,
    ocr_limit: int | None = None,
):
    import_calls: list[dict] = []
    ocr_calls: list[dict] = []

    def fake_import(db, **kwargs):
        import_calls.append(kwargs)
        return import_result

    def fake_ocr(db, **kwargs):
        ocr_calls.append(kwargs)
        return ocr_result

    monkeypatch.setattr("services.rms_resume_import.import_resume_batch", fake_import)
    monkeypatch.setattr("services.rms_resume_ocr_retry.retry_ocr_from_report", fake_ocr)

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    report_dir = tmp_path / "reports"

    result = wrapper_mod.run_import_with_ocr_retry(
        db=MagicMock(),
        source_dir=source_dir,
        dry_run=dry_run,
        commit=commit,
        recursive=False,
        source="批量导入",
        limit=limit,
        ocr_limit=ocr_limit,
        report_dir=report_dir,
        uploaded_by_user_id=1,
        upload_dir=str(tmp_path / "uploads"),
        models={},
    )
    return result, import_calls, ocr_calls, report_dir


def test_dry_run_chain(wrapper_mod, monkeypatch, tmp_path, fake_import_result, fake_ocr_result):
    (_, ocr_result, _), import_calls, ocr_calls, _ = _run_wrapper(
        wrapper_mod,
        monkeypatch,
        tmp_path,
        import_result=fake_import_result,
        ocr_result=fake_ocr_result,
        dry_run=True,
        commit=False,
    )

    assert len(import_calls) == 1
    assert import_calls[0]["dry_run"] is True
    assert import_calls[0]["commit"] is False

    assert len(ocr_calls) == 1
    assert ocr_calls[0]["dry_run"] is True
    assert ocr_calls[0]["commit"] is False
    assert ocr_calls[0]["report_csv"] == fake_import_result["report_csv"]
    assert ocr_calls[0]["uploaded_by_user_id"] == 1
    assert ocr_calls[0]["upload_dir"] == str(tmp_path / "uploads")
    assert ocr_calls[0]["source"] == "批量导入"
    assert ocr_result == fake_ocr_result


def test_commit_chain(wrapper_mod, monkeypatch, tmp_path, fake_import_result, fake_ocr_result):
    _, import_calls, ocr_calls, _ = _run_wrapper(
        wrapper_mod,
        monkeypatch,
        tmp_path,
        import_result=fake_import_result,
        ocr_result=fake_ocr_result,
        dry_run=False,
        commit=True,
    )

    assert import_calls[0]["commit"] is True
    assert import_calls[0]["dry_run"] is False
    assert ocr_calls[0]["commit"] is True
    assert ocr_calls[0]["dry_run"] is False


def test_limit_separation(wrapper_mod, monkeypatch, tmp_path, fake_import_result, fake_ocr_result):
    _, import_calls, ocr_calls, _ = _run_wrapper(
        wrapper_mod,
        monkeypatch,
        tmp_path,
        import_result=fake_import_result,
        ocr_result=fake_ocr_result,
        limit=10,
        ocr_limit=3,
    )

    assert import_calls[0]["limit"] == 10
    assert ocr_calls[0]["limit"] == 3


def test_missing_report_csv_skips_ocr(wrapper_mod, monkeypatch, tmp_path, fake_ocr_result):
    import_result = {
        "scanned": 1,
        "failed": 0,
        "report_csv": "",
    }
    ocr_called = []

    monkeypatch.setattr(
        "services.rms_resume_import.import_resume_batch",
        lambda db, **kwargs: import_result,
    )
    monkeypatch.setattr(
        "services.rms_resume_ocr_retry.retry_ocr_from_report",
        lambda db, **kwargs: ocr_called.append(kwargs) or fake_ocr_result,
    )

    source_dir = tmp_path / "src"
    source_dir.mkdir()

    with pytest.raises(SystemExit) as exc:
        wrapper_mod.run_import_with_ocr_retry(
            db=MagicMock(),
            source_dir=source_dir,
            dry_run=True,
            commit=False,
            recursive=False,
            source="批量导入",
            limit=None,
            ocr_limit=None,
            report_dir=tmp_path / "reports",
            uploaded_by_user_id=1,
            upload_dir=str(tmp_path / "uploads"),
            models={},
        )

    assert exc.value.code == 2
    assert not ocr_called


def test_combined_json_written(wrapper_mod, monkeypatch, tmp_path, fake_import_result, fake_ocr_result):
    (import_result, ocr_result, combined_path), _, _, report_dir = _run_wrapper(
        wrapper_mod,
        monkeypatch,
        tmp_path,
        import_result=fake_import_result,
        ocr_result=fake_ocr_result,
    )

    assert combined_path is not None
    assert combined_path.parent == report_dir
    assert combined_path.name.startswith("rms_resume_import_with_ocr_retry_")
    payload = json.loads(combined_path.read_text(encoding="utf-8"))
    assert payload["import"] == import_result
    assert payload["ocr_retry"] == ocr_result


def test_import_failed_still_runs_ocr(
    wrapper_mod,
    monkeypatch,
    tmp_path,
    fake_import_result,
    fake_ocr_result,
):
    import_result = {**fake_import_result, "failed": 1}
    (imp, ocr, combined), _, ocr_calls, report_dir = _run_wrapper(
        wrapper_mod,
        monkeypatch,
        tmp_path,
        import_result=import_result,
        ocr_result=fake_ocr_result,
    )

    assert len(ocr_calls) == 1
    assert imp["failed"] == 1
    assert ocr == fake_ocr_result
    assert combined is not None

    source_dir = tmp_path / "src_exit"
    source_dir.mkdir()
    mock_db = MagicMock()
    mock_main = MagicMock()
    mock_main.SessionLocal.return_value = mock_db
    mock_main.UPLOAD_DIR = str(tmp_path / "uploads_exit")
    mock_main.RMS_MODELS = {}
    monkeypatch.setitem(sys.modules, "main", mock_main)
    monkeypatch.setattr(wrapper_mod, "_resolve_uploaded_by_user_id", lambda db, uid: 1)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_rms_resumes_with_ocr_retry.py",
            "--source-dir",
            str(source_dir),
            "--dry-run",
            "--report-dir",
            str(report_dir),
        ],
    )

    assert wrapper_mod.main() == 2


def test_combined_json_write_failure_non_blocking(
    wrapper_mod,
    monkeypatch,
    tmp_path,
    fake_import_result,
    fake_ocr_result,
    capsys,
):
    real_write_text = Path.write_text

    def patched_write_text(self, *args, **kwargs):
        if "rms_resume_import_with_ocr_retry_" in self.name:
            raise OSError("disk full")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", patched_write_text)

    (imp, ocr, combined), _, _, _ = _run_wrapper(
        wrapper_mod,
        monkeypatch,
        tmp_path,
        import_result=fake_import_result,
        ocr_result=fake_ocr_result,
    )

    assert imp == fake_import_result
    assert ocr == fake_ocr_result
    assert combined is None
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
    assert "failed to write combined json" in captured.err.lower()
