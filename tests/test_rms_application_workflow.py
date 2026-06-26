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
    PARSE_DRAFT_TEXT_MAX,
    _build_extract_warning,
    _clean_resume_text_for_parse,
    _extract_draft_fields_from_text,
    _extract_explicit_work_years,
    _extract_name,
    _extract_name_candidates_from_filename,
    _parse_work_years_from_periods,
)
from sqlalchemy import text

from tests.test_rms_phase2_mvp import (
    _create_user,
    _enable_delivery_rms_mvp,
    _enable_sales_rms_jobs_write,
    _grant_role_permissions,
    _login,
    _revoke_role_permissions,
    _trial_job_and_candidate,
    _unique_phone,
)
from auth.data_scope_catalog import RESOURCE_RMS_CANDIDATE, SCOPE_NONE

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


def _full_candidate_report(job_id: int, client_id: int, **overrides) -> dict:
    payload = {
        "job_id": job_id,
        "client_id": client_id,
        "city": "西安",
        "recommendation_note": "匹配客户要求",
        "current_salary": "16000",
        "expected_salary": "18000",
        "name": "陈昭兵",
        "age": "28",
        "work_years": "4年8个月",
        "phone": "15988192434",
        "email_wechat": "15988192434@163.com",
        "available_date": "2026-06-08",
        "education_level": "硕士",
        "school": "西安工业大学",
        "major": "仪器仪表工程",
        "gender": "男",
        "marital_status": "未婚",
        "source": "朋友介绍",
    }
    payload.update(overrides)
    return payload


def _delivery_login(client, admin_auth, uniq_suffix: str):
    delivery_user = f"rms_wf_delivery_{uniq_suffix}"
    _create_user(client, admin_auth, delivery_user, [ROLE_DELIVERY])
    login = _login(client, delivery_user)
    assert login.status_code == 200
    return login


def _fetch_resume_parse(rms_engine, resume_id: int) -> tuple[str, dict]:
    with rms_engine.connect() as conn:
        row = conn.execute(
            text("SELECT parsed_text, parsed_json FROM rms_resumes WHERE id = :id"),
            {"id": resume_id},
        ).one()
    return row[0] or "", json.loads(row[1] or "{}")


def _long_resume_text_for_truncation_test() -> str:
    header = (
        "姓名：长简历测试\n"
        "手机 13800138888\n"
        "email: long@test.com\n"
    )
    filler = "工作经历补充说明段落内容。" * 250
    return header + filler


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


def test_extract_draft_fields_name_header_when_phone_later_in_resume():
    text = (
        "张宇志\n"
        "个人简历\n"
        "工作经历\n"
        "手机：13800138881\n"
    )
    draft = _extract_draft_fields_from_text(text)
    assert draft.get("name") == "张宇志"
    assert draft.get("phone") == "13800138881"


def test_extract_draft_fields_boss_style_header():
    text = (
        "邓明超\n"
        "男 | 41岁 | 13510304005\n"
        "19年工作经验 | 求职意向：设计总监/经理 | 期望城市：深圳\n"
    )
    draft = _extract_draft_fields_from_text(text)
    assert draft.get("name") == "邓明超"
    assert draft.get("age") == "41"
    assert draft.get("phone") == "13510304005"
    assert draft.get("work_years") == "19年"


def test_extract_draft_fields_boss_style_work_line_before_profile():
    text = (
        "邓明超\n"
        "19年工作经验 | 求职意向：设计总监/经理 | 期望城市：深圳\n"
        "男 | 41岁 | 13510304005\n"
    )
    draft = _extract_draft_fields_from_text(text)
    assert draft.get("name") == "邓明超"
    assert draft.get("age") == "41"
    assert draft.get("gender") == "男"
    assert draft.get("phone") == "13510304005"
    assert draft.get("work_years") == "19年"


def test_extract_draft_fields_boss_style_bare_age_without_sui():
    text = (
        "邓明超\n"
        "19年工作经验 | 求职意向：设计总监/经理 | 期望城市：深圳\n"
        "男 | 41\n"
    )
    draft = _extract_draft_fields_from_text(text)
    assert draft.get("name") == "邓明超"
    assert draft.get("age") == "41"
    assert draft.get("gender") == "男"


def test_extract_draft_fields_boss_style_profile_on_work_line():
    text = (
        "邓明超\n"
        "19年工作经验 | 求职意向：设计总监/经理 | 期望城市：深圳 | 男 | 41岁 | 13510304005\n"
    )
    draft = _extract_draft_fields_from_text(text)
    assert draft.get("name") == "邓明超"
    assert draft.get("age") == "41"
    assert draft.get("phone") == "13510304005"


def test_extract_draft_fields_name_from_filename_fallback():
    text = "19年工作经验 | 求职意向：结构设计\n男 | 41岁 | 13510304005\n"
    draft = _extract_draft_fields_from_text(
        text,
        file_name="海桥OSSOFT-结构设计-邓明超-东莞.pdf",
    )
    assert draft.get("name") == "邓明超"
    assert draft.get("age") == "41"


def test_extract_name_candidates_from_filename_preserves_multiple_candidates_order():
    assert _extract_name_candidates_from_filename(
        "海橘OSSOFT-相机效果测试-李湘-西安.pdf"
    ) == ["李湘"]


def test_filename_name_gets_boost_when_appears_anywhere_in_resume_text():
    text = (
        "1998 年2 月\n"
        "汉族\n"
        "武汉市\n"
        "15600033699\n"
        "qinyx_ws@163.com\n"
        "教育背景：本科\n"
        "专业：计算机科学与技术\n"
        "主修课程：移动应用程序设计\n"
        "袁雪芹\n"
        "基础、数据库原理\n"
    )
    draft = _extract_draft_fields_from_text(
        text,
        file_name="海橘OSSOFT-Android开发-袁雪芹-武汉.pdf",
    )
    assert draft.get("name") == "袁雪芹"


def test_filename_role_and_city_candidates_do_not_get_name_boost():
    text = (
        "Android开发\n"
        "武汉\n"
        "汉族\n"
        "15600033699\n"
        "qinyx_ws@163.com\n"
    )
    draft = _extract_draft_fields_from_text(
        text,
        file_name="海橘OSSOFT-Android开发-武汉.pdf",
    )
    assert "name" not in draft


def test_filename_name_boost_matches_spaced_name_in_resume_text():
    text = (
        "1998 年2 月\n"
        "汉族\n"
        "袁 雪 芹\n"
        "15600033699\n"
    )
    draft = _extract_draft_fields_from_text(
        text,
        file_name="海橘OSSOFT-Android开发-袁雪芹-武汉.pdf",
    )
    assert draft.get("name") == "袁雪芹"


def test_filename_name_wins_over_province_header_line():
    text = (
        "1998 年2 月\n"
        "汉族\n"
        "云南\n"
        "15600033699\n"
        "qinyx@163.com\n"
        "教育背景：本科\n"
        "主修课程：Java 程序设计\n"
        "左金平\n"
        "基础、数据库原理\n"
    )
    draft = _extract_draft_fields_from_text(
        text,
        file_name="海橘OSSOFT-Java开发-左金平-昆明.pdf",
    )
    assert draft.get("name") == "左金平"


@pytest.mark.parametrize(
    "line",
    [
        "刘注男26 岁",
        "刘注 男 26岁",
        "刘注 女 | 23岁",
        "刘注 男 | 26",
    ],
)
def test_profile_line_extracts_name_gender_age(line):
    draft = _extract_draft_fields_from_text(
        f"{line}\n手机 13800138000\n",
        file_name="unknown.pdf",
    )
    assert draft.get("name") == "刘注"


def test_extract_draft_fields_profile_line_wins_over_filename_degree_tokens():
    text = (
        "刘注男26 岁\n"
        "手机 13800138000\n"
        "邮箱 liuzhu@example.com\n"
    )
    draft = _extract_draft_fields_from_text(
        text,
        file_name="海橘OSSOFT-天线工程师-本科-刘注-武汉.pdf",
    )
    assert draft.get("name") == "刘注"


def test_filename_excludes_degree_tokens():
    assert "本科" not in _extract_name_candidates_from_filename(
        "海橘OSSOFT-天线工程师-本科-刘注-武汉.pdf"
    )
    assert "刘注" in _extract_name_candidates_from_filename(
        "海橘OSSOFT-天线工程师-本科-刘注-武汉.pdf"
    )


def test_section_heading_does_not_beat_filename_name_in_resume_text():
    draft = _extract_draft_fields_from_text(
        "个人优势\n"
        "在天线行业调试工作快十年\n"
        "曾庆雄\n"
        "男 | 38岁\n"
        "联系方式\n"
        "电话：13265760393\n",
        file_name="海橘科技-天线开发-曾庆雄-东莞.pdf",
    )
    assert draft.get("name") == "曾庆雄"


def test_header_line_rejects_full_section_heading():
    draft = _extract_draft_fields_from_text(
        "个人优势\n联系方式\n电话：13265760393\n",
        file_name="unknown.pdf",
    )
    assert "name" not in draft


def test_extract_draft_fields_prefers_filename_confirmed_header_name_over_split_section_title():
    draft = _extract_draft_fields_from_text(
        "个人优\n势\n郑力豪\n拥有 4 年海外社交与 AI 聊天产品经验\n男 | 26岁\n"
        "联系方式\n电话：18939178834\n邮箱：314575111@qq.com\n",
        file_name="海橘-OSSOFT-产品经理-北京-郑力豪.pdf",
    )
    assert draft.get("name") == "郑力豪"


def test_extract_draft_fields_rejects_split_section_heading_as_name():
    draft = _extract_draft_fields_from_text(
        "个人优\n势\n联系方式\n电话：18939178834\n",
        file_name="unknown.pdf",
    )
    assert "name" not in draft


def test_extract_draft_fields_filename_scores_multiple_candidates():
    draft = _extract_draft_fields_from_text(
        "联系方式\n电话：17349211872\n邮箱：434814837@qq.com\n求职意向：测试工程师\n",
        file_name="海橘OSSOFT-相机效果测试-李湘-西安.pdf",
    )
    assert draft.get("name") == "李湘"
    assert draft.get("phone") == "17349211872"
    assert draft.get("email_wechat") == "434814837@qq.com"


def _resume_with_split_name_labels() -> str:
    return (
        "个人简历\n"
        "个人资料\n"
        "姓\n"
        "名：马兵文\n"
        "性\n"
        "别：\n"
        "男\n"
        "手\n"
        "机：17319885735\n"
        "邮\n"
        "箱：1005867925@qq.com\n"
    )


def test_extract_draft_fields_split_name_labels_without_filename_fallback():
    draft = _extract_draft_fields_from_text(
        _resume_with_split_name_labels(),
        file_name="unknown.pdf",
    )
    assert draft.get("name") == "马兵文"
    assert draft.get("name") != "名：马兵文"
    assert draft.get("phone") == "17319885735"
    assert draft.get("email_wechat") == "1005867925@qq.com"


def test_extract_draft_fields_spaced_name_label():
    draft = _extract_draft_fields_from_text(
        "姓 名： 马 兵 文\n手机：17319885735\n",
        file_name="unknown.pdf",
    )
    assert draft.get("name") == "马兵文"
    assert draft.get("phone") == "17319885735"


def test_extract_name_rejects_standalone_ming_label_line():
    assert _extract_name("名：马兵文\n", file_name="unknown.pdf") == ""


def test_extract_draft_fields_split_name_labels_zhangqin_without_filename_fallback():
    draft = _extract_draft_fields_from_text(
        "个人简历\n基本信息\n姓\n名：张钦\n性\n别：男\n电\n话：19898718413\n",
        file_name="unknown.pdf",
    )
    assert draft.get("name") == "张钦"
    assert draft.get("phone") == "19898718413"


def test_extract_draft_fields_header_line_name_without_filename_fallback():
    draft = _extract_draft_fields_from_text(
        "王浩\n个人信息\n学历：本科\n毕业院校：许昌学院\n专业：通信工程\n电话：18103990015\n",
        file_name="unknown.pdf",
    )
    assert draft.get("name") == "王浩"
    assert draft.get("phone") == "18103990015"


def test_extract_draft_fields_rejects_bad_header_name_candidates():
    draft = _extract_draft_fields_from_text(
        "个人简历\n个人资料\n西安\n电话：13572324241\n",
        file_name="unknown.pdf",
    )
    assert "name" not in draft
    assert draft.get("phone") == "13572324241"


def test_parse_draft_split_name_labels_unknown_pdf(
    client_rbac, admin_auth, rms_engine, uniq
):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    pdf_bytes = _make_text_pdf(_resume_with_split_name_labels())
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("unknown.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    draft = r.json().get("draft_fields") or {}
    assert draft.get("name") == "马兵文"
    assert draft.get("name") != "名：马兵文"
    assert draft.get("phone") == "17319885735"
    assert draft.get("email_wechat") == "1005867925@qq.com"


def test_extract_draft_fields_boss_style_does_not_treat_section_as_name():
    text = (
        "个人信息\n"
        "男 | 41岁 | 13510304005\n"
    )
    draft = _extract_draft_fields_from_text(text)
    assert "name" not in draft


def test_parse_draft_route_boss_style_resume(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    txt = (
        "邓明超\n"
        "男 | 41岁 | 13510304005\n"
        "19年工作经验 | 求职意向：结构设计\n"
    )
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    draft = r.json().get("draft_fields") or {}
    assert draft.get("name") == "邓明超"
    assert draft.get("age") == "41"


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
    assert body.get("duplicate_detected") is False


def test_parse_draft_duplicate_detected_when_candidate_exists(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = f"parse_dup_{uniq}"
    login, _job_id, _cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    dup_phone = "13700137000"
    txt = f"姓名：王磊\n手机 {dup_phone}\n"
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    draft = body.get("draft_fields") or {}
    assert draft.get("name") == "王磊"
    assert draft.get("phone") == dup_phone
    assert body.get("duplicate_detected") is True


def test_check_duplicate_route_detects_existing_phone(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = f"check_dup_{uniq}"
    login, _job_id, _cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    r = client_rbac.post(
        "/api/rms/candidates/check-duplicate",
        cookies=login.cookies,
        json={"name": "其他人", "phone": "13700137000"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("duplicate_detected") is True


def test_parse_draft_duplicate_detected_by_phone_only(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = f"parse_phone_dup_{uniq}"
    login, _job_id, _cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    dup_phone = "13700137000"
    txt = f"姓名：其他姓名\n手机 {dup_phone}\n"
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("duplicate_detected") is True


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
    report = _full_candidate_report(job_id, client_id)
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
    assert body["candidate"]["city"] == "西安"
    assert body["candidate"]["school"] == "西安工业大学"
    assert body["application"]["job_id"] == job_id
    assert body["application"]["candidate_id"] == body["candidate"]["id"]
    assert body["application"]["resume_id"]
    assert body["application"]["recommended_at"]
    listed = client_rbac.get("/api/rms/candidates", cookies=login.cookies)
    assert listed.status_code == 200, listed.text
    cand_row = next(
        item for item in listed.json() if item["id"] == body["candidate"]["id"]
    )
    assert cand_row["recommended_at"] == body["application"]["recommended_at"]


def test_submit_candidate_report_allows_resume_upload_without_candidate_write_scope(
    client_rbac, admin_auth, rms_engine, uniq
):
    from tests.test_rms_phase2_mvp import _set_role_data_scope

    _set_role_data_scope(
        rms_engine, ROLE_DELIVERY, RESOURCE_RMS_CANDIDATE, "write", SCOPE_NONE
    )
    login, job_id, _cand_id, client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"report_scope_{uniq}"
    )
    report = _full_candidate_report(job_id, client_id, phone=_unique_phone())
    r = client_rbac.post(
        "/api/rms/applications/candidate-report",
        cookies=login.cookies,
        data={"report_json": json.dumps(report, ensure_ascii=False)},
        files={"file": ("resume.txt", b"resume content", "text/plain")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["application"]["resume_id"]


def test_submit_candidate_report_persists_txt_parse(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, job_id, _cand_id, client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"report_txt_parse_{uniq}"
    )
    txt = _resume_with_contact_and_education()
    phone = _unique_phone()
    report = _full_candidate_report(
        job_id,
        client_id,
        phone=phone,
        email_wechat=f"{phone}@163.com",
    )
    r = client_rbac.post(
        "/api/rms/applications/candidate-report",
        cookies=login.cookies,
        data={"report_json": json.dumps(report, ensure_ascii=False)},
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    resume_id = r.json()["application"]["resume_id"]
    parsed_text, parsed_json = _fetch_resume_parse(rms_engine, resume_id)
    assert parsed_text
    _assert_contact_and_education_draft(parsed_json)


def test_submit_candidate_report_persists_pdf_parse(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, job_id, _cand_id, client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"report_pdf_parse_{uniq}"
    )
    pdf_bytes = _make_text_pdf(_resume_with_contact_and_education())
    phone = _unique_phone()
    report = _full_candidate_report(
        job_id,
        client_id,
        phone=phone,
        email_wechat=f"{phone}@163.com",
    )
    r = client_rbac.post(
        "/api/rms/applications/candidate-report",
        cookies=login.cookies,
        data={"report_json": json.dumps(report, ensure_ascii=False)},
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    resume_id = r.json()["application"]["resume_id"]
    parsed_text, parsed_json = _fetch_resume_parse(rms_engine, resume_id)
    assert parsed_text
    _assert_contact_and_education_draft(parsed_json)


def test_upload_candidate_resume_persists_parse(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, _job_id, cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"upload_parse_{uniq}"
    )
    txt = _resume_with_contact_and_education()
    r = client_rbac.post(
        f"/api/rms/candidates/{cand_id}/resume",
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    resume_id = r.json()["id"]
    parsed_text, parsed_json = _fetch_resume_parse(rms_engine, resume_id)
    assert parsed_text
    _assert_contact_and_education_draft(parsed_json)


def _resume_with_parse_only_keyword(keyword: str) -> str:
    return (
        "姓名：简历检索测试\n"
        "手机 15900001111\n"
        "email: parseonly@example.com\n"
        f"项目经历：{keyword}\n"
    )


def test_candidate_search_parsed_text_with_contacts_view(
    client_rbac, admin_auth, rms_engine, uniq
):
    import main as crm_main

    keyword = f"PARSEONLY_{uniq}"
    _grant_role_permissions(crm_main.engine, ROLE_DELIVERY, ("rms.contacts.view",))
    login, _job_id, cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"srch_parse_{uniq}"
    )
    txt = _resume_with_parse_only_keyword(keyword)
    upload = client_rbac.post(
        f"/api/rms/candidates/{cand_id}/resume",
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    r = client_rbac.get(f"/api/rms/candidates?q={keyword}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert cand_id in {c["id"] for c in r.json()}


def test_candidate_search_phone_not_leaked_without_contacts_view(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, _job_id, cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"srch_ph_{uniq}"
    )
    with rms_engine.connect() as conn:
        phone = conn.execute(
            text("SELECT phone FROM rms_candidates WHERE id = :id"),
            {"id": cand_id},
        ).scalar()
    r = client_rbac.get(f"/api/rms/candidates?q={phone}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert cand_id not in {c["id"] for c in r.json()}


def test_candidate_search_parsed_text_gated_without_contacts_view(
    client_rbac, admin_auth, rms_engine, uniq
):
    keyword = f"PARSEONLY_{uniq}"
    _revoke_role_permissions(rms_engine, ROLE_DELIVERY, ("rms.contacts.view",))
    login, _job_id, cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"srch_noparse_{uniq}"
    )
    txt = _resume_with_parse_only_keyword(keyword)
    upload = client_rbac.post(
        f"/api/rms/candidates/{cand_id}/resume",
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    r = client_rbac.get(f"/api/rms/candidates?q={keyword}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert cand_id not in {c["id"] for c in r.json()}


def test_submit_candidate_report_word_resume_empty_parse_ok(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, job_id, _cand_id, client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"report_word_{uniq}"
    )
    phone = _unique_phone()
    report = _full_candidate_report(
        job_id,
        client_id,
        phone=phone,
        email_wechat=f"{phone}@163.com",
    )
    r = client_rbac.post(
        "/api/rms/applications/candidate-report",
        cookies=login.cookies,
        data={"report_json": json.dumps(report, ensure_ascii=False)},
        files={
            "file": (
                "resume.docx",
                b"PK fake docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert r.status_code == 200, r.text
    resume_id = r.json()["application"]["resume_id"]
    parsed_text, parsed_json = _fetch_resume_parse(rms_engine, resume_id)
    assert parsed_text == ""
    assert parsed_json == {}


def test_persisted_parsed_text_not_truncated_at_2000(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, job_id, _cand_id, client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"report_long_{uniq}"
    )
    txt = _long_resume_text_for_truncation_test()
    txt_bytes = txt.encode("utf-8")

    draft_r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt_bytes, "text/plain")},
    )
    assert draft_r.status_code == 200, draft_r.text
    draft_body = draft_r.json()
    assert len(draft_body.get("parsed_text") or "") <= PARSE_DRAFT_TEXT_MAX
    assert draft_body.get("parsed_text_length", 0) > PARSE_DRAFT_TEXT_MAX

    phone = _unique_phone()
    report = _full_candidate_report(
        job_id,
        client_id,
        phone=phone,
        email_wechat=f"{phone}@163.com",
    )
    submit_r = client_rbac.post(
        "/api/rms/applications/candidate-report",
        cookies=login.cookies,
        data={"report_json": json.dumps(report, ensure_ascii=False)},
        files={"file": ("resume.txt", txt_bytes, "text/plain")},
    )
    assert submit_r.status_code == 200, submit_r.text
    resume_id = submit_r.json()["application"]["resume_id"]
    parsed_text, _parsed_json = _fetch_resume_parse(rms_engine, resume_id)
    assert len(parsed_text) > PARSE_DRAFT_TEXT_MAX


def test_candidate_report_duplicate_blocks_candidate_and_application(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, job_id, _cand_id, client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"report_dup_{uniq}"
    )
    phone = _unique_phone()
    report = _full_candidate_report(
        job_id,
        client_id,
        name=f"ReportDup_{uniq}",
        phone=phone,
        email_wechat=f"{phone}@163.com",
    )
    files = {"file": ("resume.txt", b"resume content", "text/plain")}
    first = client_rbac.post(
        "/api/rms/applications/candidate-report",
        cookies=login.cookies,
        data={"report_json": json.dumps(report, ensure_ascii=False)},
        files=files,
    )
    assert first.status_code == 200, first.text

    with rms_engine.connect() as conn:
        cand_count = conn.execute(text("SELECT COUNT(*) FROM rms_candidates")).scalar()
        app_count = conn.execute(text("SELECT COUNT(*) FROM rms_applications")).scalar()
        resume_count = conn.execute(text("SELECT COUNT(*) FROM rms_resumes")).scalar()

    dup = client_rbac.post(
        "/api/rms/applications/candidate-report",
        cookies=login.cookies,
        data={"report_json": json.dumps(report, ensure_ascii=False)},
        files=files,
    )
    assert dup.status_code == 409, dup.text
    assert dup.json().get("detail") == "人选已存在系统中"

    with rms_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM rms_candidates")).scalar() == cand_count
        assert conn.execute(text("SELECT COUNT(*) FROM rms_applications")).scalar() == app_count
        assert conn.execute(text("SELECT COUNT(*) FROM rms_resumes")).scalar() == resume_count


def test_submit_candidate_report_requires_city(client_rbac, admin_auth, rms_engine, uniq):
    login, job_id, _cand_id, client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"report_city_{uniq}"
    )
    report = _full_candidate_report(
        job_id,
        client_id,
        city="",
        name="无城市",
        phone="15988192435",
        email_wechat="nocity@163.com",
    )
    r = client_rbac.post(
        "/api/rms/applications/candidate-report",
        cookies=login.cookies,
        data={"report_json": json.dumps(report, ensure_ascii=False)},
    )
    assert r.status_code == 400, r.text
    assert "城市" in r.json().get("detail", "")


def test_submit_candidate_report_requires_available_date(client_rbac, admin_auth, rms_engine, uniq):
    login, job_id, _cand_id, client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"report_avail_{uniq}"
    )
    report = _full_candidate_report(job_id, client_id, available_date="")
    r = client_rbac.post(
        "/api/rms/applications/candidate-report",
        cookies=login.cookies,
        data={"report_json": json.dumps(report, ensure_ascii=False)},
    )
    assert r.status_code == 400, r.text
    assert r.json().get("detail") == "请填写到岗时间"


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


def test_delivery_review_submit_failed_sets_internal_screen_failed(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"dr_fail_{uniq}"
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "failed", "note": "简历不符"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["delivery_review_status"] == "failed"
    assert body["receive_status"] == "pending"
    assert body["status"] == "internal_screen_failed"
    assert body["current_stage"] == "internal_screen_failed"

    listed = client_rbac.get(DELIVERY_REVIEW_LIST_URL, cookies=login.cookies)
    assert listed.status_code == 200
    assert app_id not in [item["id"] for item in listed.json()]

    all_apps = client_rbac.get("/api/rms/applications", cookies=login.cookies)
    assert all_apps.status_code == 200
    found = next((a for a in all_apps.json() if a["id"] == app_id), None)
    assert found is not None
    assert found["delivery_review_status"] == "failed"
    assert found["status"] == "internal_screen_failed"
    assert _pipeline_eligible(found) is False

    hist = client_rbac.get(
        f"/api/rms/applications/{app_id}/status-history",
        cookies=login.cookies,
    )
    assert hist.status_code == 200, hist.text
    items = hist.json()
    assert len(items) == 1
    assert items[0]["from_status"] == "recommended"
    assert items[0]["to_status"] == "internal_screen_failed"
    assert items[0]["reason"] == "delivery_review_failed"


def test_hired_requires_hired_at(client_rbac, admin_auth, rms_engine, uniq):
    from tests.test_rms_phase2_mvp import _advance_to_onboarding

    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"hire_{uniq}"
    )
    _advance_to_onboarding(client_rbac, login, app_id, engine=rms_engine)

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


def test_delivery_review_submit_failed_requires_note(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"dr_no_note_{uniq}"
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "failed", "note": ""},
    )
    assert r.status_code == 400, r.text
    assert "内审失败须填写理由" in r.json().get("detail", "")

    short = client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "failed", "note": "短"},
    )
    assert short.status_code == 400, short.text


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


def test_delete_application_cascades_and_allows_candidate_delete(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"del_app_{uniq}"
    )
    cand_id = client_rbac.get(f"/api/rms/applications/{app_id}", cookies=login.cookies).json()[
        "candidate_id"
    ]
    client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "passed"},
    )
    hist_before = client_rbac.get(
        f"/api/rms/applications/{app_id}/status-history",
        cookies=login.cookies,
    )
    assert hist_before.status_code == 200
    assert len(hist_before.json()) >= 1

    blocked = client_rbac.delete(f"/api/rms/candidates/{cand_id}", cookies=login.cookies)
    assert blocked.status_code == 409

    deleted = client_rbac.delete(f"/api/rms/applications/{app_id}", cookies=login.cookies)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"ok": True, "id": app_id, "candidate_id": cand_id}

    missing = client_rbac.get(f"/api/rms/applications/{app_id}", cookies=login.cookies)
    assert missing.status_code == 404

    hist_after = client_rbac.get(
        f"/api/rms/applications/{app_id}/status-history",
        cookies=login.cookies,
    )
    assert hist_after.status_code == 404

    ok = client_rbac.delete(f"/api/rms/candidates/{cand_id}", cookies=login.cookies)
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"ok": True, "id": cand_id}


def test_delete_application_not_found(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.delete("/api/rms/applications/999999999", cookies=login.cookies)
    assert r.status_code == 404


def test_delete_application_post_fallback(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"del_post_{uniq}"
    )
    r = client_rbac.post(f"/api/rms/applications/{app_id}/delete", cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["id"] == app_id

    missing = client_rbac.get(f"/api/rms/applications/{app_id}", cookies=login.cookies)
    assert missing.status_code == 404


def test_format_interview_schedule_display():
    from schemas.rms import format_interview_schedule_display

    assert format_interview_schedule_display("一面时间7/1下午3点", kind="first") == "7/1下午3点"
    assert format_interview_schedule_display("7/1下午3点", kind="first") == "7/1下午3点"
    assert format_interview_schedule_display("二面时间8/2上午10点", kind="second") == "8/2上午10点"
    assert format_interview_schedule_display("8/2上午10点", kind="second") == ""
    assert format_interview_schedule_display("一面时间2026-06-27 15:00", kind="first") == "2026-06-27 15:00"


def test_build_interview_schedule_note():
    from schemas.rms import build_interview_schedule_note

    assert build_interview_schedule_note("first", "2026-06-27", "15:00") == "一面时间2026-06-27 15:00"
    assert build_interview_schedule_note("second", "2026-06-28", "09:30") == "二面时间2026-06-28 09:30"


def test_validate_correction_backward():
    import pytest
    from fastapi import HTTPException

    from schemas.rms import validate_correction_backward

    validate_correction_backward("first_interview_passed", "pending_first_interview")
    with pytest.raises(HTTPException) as exc:
        validate_correction_backward("pending_client_screen", "onboarding")
    assert "前序" in exc.value.detail

