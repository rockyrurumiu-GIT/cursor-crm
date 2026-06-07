"""RMS candidate-report parse-draft workflow."""
from __future__ import annotations

import importlib
import json
import uuid
from datetime import date

import pytest
from starlette.testclient import TestClient

from auth.permissions import ROLE_DELIVERY
from services.rms_applications import (
    _build_extract_warning,
    _clean_resume_text_for_parse,
    _extract_draft_fields_from_text,
    _extract_explicit_work_years,
    _parse_work_years_from_periods,
)
from tests.test_rms_phase2_mvp import (
    _create_user,
    _enable_delivery_rms_mvp,
    _enable_sales_rms_jobs_write,
    _login,
    _trial_job_and_candidate,
)

PARSE_DRAFT_URL = "/api/rms/applications/candidate-report/parse-draft"
DELIVERY_REVIEW_LIST_URL = "/api/rms/applications/delivery-review"
_FIXED_TODAY = date(2026, 6, 5)


def _pipeline_eligible(app: dict) -> bool:
    return (
        app.get("receive_status") == "accepted"
        and app.get("delivery_review_status") == "passed"
    )


@pytest.fixture
def client_rbac(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


@pytest.fixture
def rms_engine(client_rbac):
    import main as crm_main

    _enable_sales_rms_jobs_write(crm_main.engine)
    _enable_delivery_rms_mvp(crm_main.engine)
    return crm_main.engine


@pytest.fixture
def uniq():
    return uuid.uuid4().hex[:8]


def _delivery_login(client, admin_auth, uniq_suffix: str):
    delivery_user = f"rms_wf_delivery_{uniq_suffix}"
    _create_user(client, admin_auth, delivery_user, [ROLE_DELIVERY])
    login = _login(client, delivery_user)
    assert login.status_code == 200
    return login


def _make_text_pdf(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in text.splitlines():
        page.insert_text((72, y), line, fontname="china-s", fontsize=11)
        y += 14
    data = doc.tobytes()
    doc.close()
    return data


def _resume_with_contact_and_education() -> str:
    return (
        "姓名：测试候选人\n"
        "手机 15988192434\n"
        "email: 15988192434@163.com\n"
        "教育背景\n"
        "2015.09 -- 2019.07  西安工业大学（学士）    测控技术与仪器专业\n"
        "2019.09 -- 2022.07  西安工业大学（硕士）    仪器仪表工程专业\n"
        "毕业论文：《基于DLP 系统的超短焦4K 投影镜头设计》\n"
        "项目经历\n"
        "杭州电子科技大学信息工程学院激光雷达中心"
    )


def _assert_contact_and_education_draft(draft: dict) -> None:
    assert draft.get("phone") == "15988192434"
    assert draft.get("email_wechat") == "15988192434@163.com"
    assert draft.get("school") == "西安工业大学"
    assert draft.get("major") == "仪器仪表工程"
    assert draft.get("education_level") == "硕士"
    major = draft.get("major") or ""
    school = draft.get("school") or ""
    assert "毕业论文" not in major
    assert "DLP" not in major
    assert "杭州" not in school
    assert "2015" not in school


def _resume_with_hyphen_phone_and_split_education() -> str:
    return (
        "姓名：李四\n"
        "181-6174-9101\n"
        "2020-2024  安康学院  计算机科学与\n"
        "技术 | 本科\n"
    )


def _resume_with_spaced_school_name() -> str:
    return (
        "姓名：李四\n"
        "181-6174-9101\n"
        "2020-2024  安 康 学 院  计算机科学与\n"
        "技术 | 本科\n"
    )


def _resume_with_vertical_education() -> str:
    return (
        "姓名：李四\n"
        "181-6174-9101\n"
        "2020-2024\n"
        "安康学院\n"
        "计算机科学与技术\n"
        "本科\n"
    )


def _resume_with_work_periods() -> str:
    return (
        _resume_with_contact_and_education()
        + "\n2024.02-至今  某科技公司  高级工程师\n"
        "工作经历\n"
        "2022.08-2023.10  某研究院  研究员\n"
        "实习经历\n"
        "2020.10-2021.9  某创业公司  实习生\n"
    )


def test_parse_work_years_from_periods_mixed_education_and_work():
    text = _resume_with_work_periods()
    assert _parse_work_years_from_periods(text, today=_FIXED_TODAY) == "4年8个月"
    draft = _extract_draft_fields_from_text(text)
    assert draft.get("work_years") == "4年8个月"
    _assert_contact_and_education_draft(draft)


def test_parse_work_years_from_periods_education_only():
    text = _resume_with_contact_and_education()
    assert _parse_work_years_from_periods(text, today=_FIXED_TODAY) == ""


def test_parse_work_years_from_periods_overlapping_ranges():
    text = "工作经历\n2022.01-2023.01  公司A\n2022.06-2022.12  公司B\n"
    assert _parse_work_years_from_periods(text, today=_FIXED_TODAY) == "1年1个月"


def test_extract_draft_fields_explicit_work_years_overrides_periods():
    text = "工作年限：5年\n" + _resume_with_work_periods()
    assert _extract_draft_fields_from_text(text).get("work_years") == "5年"


def test_extract_draft_fields_explicit_work_years_variants():
    assert _extract_explicit_work_years("工作年限：5") == "5年"
    assert _extract_explicit_work_years("工作年限：5年") == "5年"
    assert _extract_explicit_work_years("8年以上工作经验") == "8年以上"
    text = "8年以上工作经验\n" + _resume_with_work_periods()
    assert _extract_draft_fields_from_text(text).get("work_years") == "8年以上"


def test_explicit_work_years_does_not_match_date_tokens():
    text = "项目经历\n2020年10月 - 2021年9月  某公司  工程师\n"
    assert _extract_explicit_work_years(text) == ""
    assert _extract_draft_fields_from_text(text).get("work_years") == "1年"


def test_extract_draft_fields_hyphenated_phone_and_split_education():
    draft = _extract_draft_fields_from_text(_resume_with_hyphen_phone_and_split_education())
    assert draft.get("phone") == "18161749101"
    assert draft.get("name") == "李四"
    assert draft.get("school") == "安康学院"
    assert draft.get("major") == "计算机科学与技术"
    assert draft.get("education_level") == "统本"


def test_extract_draft_fields_labeled_hyphenated_phone():
    text = "姓名：王五\n电话：181-6174-9101\n"
    draft = _extract_draft_fields_from_text(text)
    assert draft.get("phone") == "18161749101"
    assert draft.get("name") == "王五"


def test_extract_draft_fields_spaced_school_name():
    draft = _extract_draft_fields_from_text(_resume_with_spaced_school_name())
    assert draft.get("school") == "安康学院"
    assert draft.get("major") == "计算机科学与技术"
    assert draft.get("education_level") == "统本"


def test_extract_draft_fields_vertical_education_lines():
    draft = _extract_draft_fields_from_text(_resume_with_vertical_education())
    assert draft.get("school") == "安康学院"
    assert draft.get("major") == "计算机科学与技术"
    assert draft.get("education_level") == "统本"


def test_extract_draft_fields_name_stops_before_phone_label():
    text = "姓名：田帅 电话：181-6174-9101\n"
    draft = _extract_draft_fields_from_text(text)
    assert draft.get("name") == "田帅"
    assert draft.get("phone") == "18161749101"


def test_extract_draft_fields_name_not_merged_with_phone_label():
    text = "姓名：田帅电话：181-6174-9101\n"
    draft = _extract_draft_fields_from_text(text)
    assert draft.get("name") == "田帅"
    assert draft.get("phone") == "18161749101"


def test_parse_draft_route_not_captured_by_application_id(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    txt = "姓名：路由测试\n手机 13800138000\nemail: route@test.com"
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    assert r.status_code != 422


def test_parse_draft_txt_extracts_phone_email_and_work_years(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    txt = (
        "姓名：张三\n"
        "手机 13800138077\n"
        "email: draft@example.com\n"
        "年龄：28\n"
        "工作年限：5年"
    )
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    draft = body.get("draft_fields") or {}
    assert draft.get("phone") == "13800138077"
    assert draft.get("email_wechat") == "draft@example.com"
    assert draft.get("work_years") == "5年"
    assert body.get("parsed_text")


def test_parse_draft_txt_contact_and_education(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    txt = _resume_with_contact_and_education()
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_contact_and_education_draft(body.get("draft_fields") or {})
    assert body.get("parsed_text")


def test_parse_draft_pdf_contact_and_education(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    pdf_bytes = _make_text_pdf(_resume_with_contact_and_education())
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_contact_and_education_draft(body.get("draft_fields") or {})
    assert body.get("parsed_text")


def test_parse_draft_txt_hyphen_phone_and_split_education(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    txt = _resume_with_hyphen_phone_and_split_education()
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    draft = (r.json().get("draft_fields") or {})
    assert draft.get("phone") == "18161749101"
    assert draft.get("school") == "安康学院"
    assert draft.get("major") == "计算机科学与技术"
    assert draft.get("education_level") == "统本"


def test_parse_draft_pdf_hyphen_phone_and_split_education(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    pdf_bytes = _make_text_pdf(_resume_with_hyphen_phone_and_split_education())
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    draft = (r.json().get("draft_fields") or {})
    assert draft.get("phone") == "18161749101"
    assert draft.get("school") == "安康学院"
    assert draft.get("major") == "计算机科学与技术"
    assert draft.get("education_level") == "统本"


def test_parse_draft_pdf_spaced_school_name(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    pdf_bytes = _make_text_pdf(_resume_with_spaced_school_name())
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    draft = (r.json().get("draft_fields") or {})
    assert draft.get("school") == "安康学院"
    assert draft.get("major") == "计算机科学与技术"
    assert draft.get("education_level") == "统本"


def test_parse_draft_pdf_extracts_fields_and_parsed_text(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    pdf_bytes = _make_text_pdf("姓名：王五\n手机 13700137000\nemail: pdf@test.com")
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    draft = body.get("draft_fields") or {}
    assert any(draft.get(k) for k in ("phone", "email_wechat", "name"))
    assert body.get("parsed_text")


def test_clean_resume_text_removes_tracking_line_keeps_contact_line():
    tracking = "711f7a020cbe32a51X1609-7E1ZRwIi2UfiaWOKqmfDXMhNq"
    raw = (
        f"姓名：王智超\n"
        f"手机 15029496938\n"
        f"{tracking}\n"
        "试用水印\n"
        f"{tracking}\n"
        "软通动力有限公司 结构工程师"
    )
    cleaned = _clean_resume_text_for_parse(raw)
    assert tracking not in cleaned
    assert "试用水印" not in cleaned
    assert "15029496938" in cleaned
    assert "王智超" in cleaned
    assert "软通动力" in cleaned


def test_build_extract_warning_flags_low_contact():
    warning = _build_extract_warning("noise only", "", {}, is_pdf=True)
    assert "未能识别" in warning or "中文" in warning or "扫描" in warning


def test_parse_draft_response_includes_length_and_warning_fields(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    txt = (
        "姓名：张三\n"
        "手机 13800138077\n"
        "email: draft@example.com\n"
        "711f7a020cbe32a51X1609-7E1ZRwIi2UfiaWOKqmfDXMhNq\n"
    )
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "parsed_text_length" in body
    assert "parsed_text_raw_length" in body
    assert "parsed_text_raw" in body
    assert "extract_warning" in body
    assert body["parsed_text_length"] > 0
    assert body["parsed_text_raw_length"] >= body["parsed_text_length"]
    assert "711f7a020cbe32a51X1609" not in (body.get("parsed_text") or "")
    draft = body.get("draft_fields") or {}
    assert draft.get("phone") == "13800138077"
    assert draft.get("name") == "张三"


def test_parse_draft_docx_returns_friendly_message(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.docx", b"PK fake docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("draft_fields") == {}
    assert "Word" in (body.get("message") or "")
    assert body.get("parsed_text_length") == 0
    assert body.get("parsed_text_raw_length") == 0
    assert body.get("extract_warning") == ""


def test_parse_draft_unknown_extension_returns_400(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.exe", b"binary", "application/octet-stream")},
    )
    assert r.status_code == 400, r.text


def test_submit_candidate_report_creates_candidate_and_application(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, job_id, _cand_id, client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"report_{uniq}"
    )
    report = {
        "job_id": job_id,
        "client_id": client_id,
        "recommendation_note": "匹配客户要求",
        "current_salary": "16000",
        "expected_salary": "18000",
        "name": "陈昭兵",
        "age": "28",
        "work_years": "4年8个月",
        "phone": "15988192434",
        "email_wechat": "15988192434@163.com",
        "education_level": "硕士",
        "school": "西安工业大学",
        "major": "仪器仪表工程",
        "gender": "男",
        "source": "其他",
    }
    r = client_rbac.post(
        "/api/rms/applications/candidate-report",
        cookies=login.cookies,
        data={"report_json": json.dumps(report, ensure_ascii=False)},
        files={"file": ("resume.txt", b"resume content", "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["candidate"]["id"]
    assert body["candidate"]["target_client_id"] == client_id
    assert body["candidate"]["school"] == "西安工业大学"
    assert body["application"]["job_id"] == job_id
    assert body["application"]["candidate_id"] == body["candidate"]["id"]
    assert body["application"]["resume_id"]


def test_delivery_review_route_not_captured_by_application_id(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get(DELIVERY_REVIEW_LIST_URL, cookies=login.cookies)
    assert r.status_code != 422, r.text
    assert r.status_code == 200, r.text


def test_delivery_review_list_empty(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get(DELIVERY_REVIEW_LIST_URL, cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_delivery_review_list_returns_recommended(client_rbac, admin_auth, rms_engine, uniq):
    login, job_id, cand_id, _ = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"dr_{uniq}"
    )
    created = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert created.status_code == 200, created.text
    app_id = created.json()["id"]

    r = client_rbac.get(DELIVERY_REVIEW_LIST_URL, cookies=login.cookies)
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()]
    assert app_id in ids

    all_apps = client_rbac.get("/api/rms/applications", cookies=login.cookies)
    assert all_apps.status_code == 200
    found = next((a for a in all_apps.json() if a["id"] == app_id), None)
    assert found is not None
    assert _pipeline_eligible(found) is False


def _create_recommended_application(client, admin_auth, rms_engine, suffix: str) -> tuple:
    login, job_id, cand_id, _ = _trial_job_and_candidate(client, rms_engine, admin_auth, suffix)
    created = client.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert created.status_code == 200, created.text
    return login, int(created.json()["id"])


def test_delivery_review_submit_passed_enters_pipeline(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"dr_pass_{uniq}"
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "passed", "note": ""},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["delivery_review_status"] == "passed"
    assert body["receive_status"] == "accepted"
    assert body["status"] == "pending_client_screen"

    listed = client_rbac.get(DELIVERY_REVIEW_LIST_URL, cookies=login.cookies)
    assert listed.status_code == 200
    assert app_id not in [item["id"] for item in listed.json()]

    all_apps = client_rbac.get("/api/rms/applications", cookies=login.cookies)
    assert all_apps.status_code == 200
    found = next((a for a in all_apps.json() if a["id"] == app_id), None)
    assert found is not None
    assert found["status"] == "pending_client_screen"
    assert _pipeline_eligible(found) is True


def test_delivery_review_submit_failed_leaves_recommended_visible(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"dr_fail_{uniq}"
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "failed", "note": ""},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["delivery_review_status"] == "failed"
    assert body["receive_status"] == "pending"
    assert body["status"] == "recommended"

    listed = client_rbac.get(DELIVERY_REVIEW_LIST_URL, cookies=login.cookies)
    assert listed.status_code == 200
    assert app_id not in [item["id"] for item in listed.json()]

    all_apps = client_rbac.get("/api/rms/applications", cookies=login.cookies)
    assert all_apps.status_code == 200
    found = next((a for a in all_apps.json() if a["id"] == app_id), None)
    assert found is not None
    assert found["delivery_review_status"] == "failed"
    assert _pipeline_eligible(found) is False


def test_hired_requires_hired_at(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"hire_{uniq}"
    )
    client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "passed"},
    )
    for st in ("scheduling_interview", "pending_first_interview", "first_interview_passed",
               "second_interview_passed", "pending_offer", "onboarding"):
        prev = client_rbac.get(f"/api/rms/applications/{app_id}", cookies=login.cookies).json()
        nxt = {
            "pending_client_screen": "scheduling_interview",
            "scheduling_interview": "pending_first_interview",
            "pending_first_interview": "first_interview_passed",
            "first_interview_passed": "second_interview_passed",
            "second_interview_passed": "pending_offer",
            "pending_offer": "onboarding",
        }[prev["status"]]
        client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json={"to_status": nxt},
        )
    bad = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "hired"},
    )
    assert bad.status_code == 400
    ok = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "hired", "hired_at": "2026-06-15"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["hired_at"] == "2026-06-15"
    assert ok.json()["status"] == "hired"


def test_hired_roster_check_route_not_422(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get("/api/rms/applications/hired-roster-check", cookies=login.cookies)
    assert r.status_code != 422, r.text
    assert r.status_code == 200, r.text


def test_delivery_review_submit_invalid_result(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"dr_bad_{uniq}"
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "maybe", "note": ""},
    )
    assert r.status_code == 422, r.text


