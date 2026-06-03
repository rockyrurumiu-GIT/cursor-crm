"""RMS ORM models (Phase 1: mapping only; tables created by migrations/005_rms_tables.sql)."""
from __future__ import annotations

from typing import Dict, Type

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text

_CLASS_BY_TABLE: Dict[str, str] = {
    "rms_jobs": "RmsJob",
    "rms_candidates": "RmsCandidate",
    "rms_resumes": "RmsResume",
    "rms_applications": "RmsApplication",
    "rms_application_status_history": "RmsApplicationStatusHistory",
    "rms_interviews": "RmsInterview",
    "rms_offers": "RmsOffer",
    "rms_match_results": "RmsMatchResult",
}

_models_cache_by_base: Dict[int, Dict[str, Type]] = {}


def _ensure_sys_user_stub(Base) -> None:
    if "sys_user" not in Base.metadata.tables:
        class SysUser(Base):  # noqa: F841 — FK target for RMS ORM only
            __tablename__ = "sys_user"
            id = Column(Integer, primary_key=True)


def _models_from_metadata(Base) -> Dict[str, Type]:
    out: Dict[str, Type] = {}
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        tablename = getattr(cls, "__tablename__", None)
        if tablename in _CLASS_BY_TABLE:
            out[_CLASS_BY_TABLE[tablename]] = cls
    expected = set(_CLASS_BY_TABLE.values())
    if set(out.keys()) != expected:
        missing = expected - set(out.keys())
        raise RuntimeError(f"RMS models incomplete in metadata: missing {missing}")
    return out


def register_rms_models(Base) -> Dict[str, Type]:
    """Register RMS ORM classes on Base. Idempotent per metadata; does not call create_all."""
    _ensure_sys_user_stub(Base)
    cache_key = id(Base.metadata)
    if cache_key in _models_cache_by_base:
        return dict(_models_cache_by_base[cache_key])
    if "rms_jobs" in Base.metadata.tables:
        models = _models_from_metadata(Base)
        _models_cache_by_base[cache_key] = models
        return dict(models)

    class RmsCandidate(Base):
        __tablename__ = "rms_candidates"
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String, default="")
        phone = Column(String, default="")
        email = Column(String, default="")
        wechat = Column(String, default="")
        current_company = Column(String, default="")
        current_title = Column(String, default="")
        city = Column(String, default="")
        source = Column(String, default="")
        tags = Column(Text, default="[]")
        created_by_user_id = Column(Integer, ForeignKey("sys_user.id"), nullable=True)
        created_at = Column(String, default="")
        updated_at = Column(String, default="")

    class RmsJob(Base):
        __tablename__ = "rms_jobs"
        id = Column(Integer, primary_key=True, index=True)
        client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
        title = Column(String, default="")
        department = Column(String, default="")
        location = Column(String, default="")
        headcount = Column(Integer, default=1)
        job_description = Column(Text, default="")
        requirements = Column(Text, default="")
        status = Column(String, default="open")
        owner_user_id = Column(Integer, ForeignKey("sys_user.id"), nullable=False, index=True)
        created_at = Column(String, default="")
        updated_at = Column(String, default="")

    class RmsResume(Base):
        __tablename__ = "rms_resumes"
        id = Column(Integer, primary_key=True, index=True)
        candidate_id = Column(Integer, ForeignKey("rms_candidates.id"), nullable=False, index=True)
        file_name = Column(String, default="")
        file_path = Column(String, default="")
        file_type = Column(String, default="")
        parsed_text = Column(Text, default="")
        parsed_json = Column(Text, default="{}")
        uploaded_by = Column(Integer, ForeignKey("sys_user.id"), nullable=True)
        created_at = Column(String, default="")

    class RmsApplication(Base):
        __tablename__ = "rms_applications"
        id = Column(Integer, primary_key=True, index=True)
        job_id = Column(Integer, ForeignKey("rms_jobs.id"), nullable=False, index=True)
        candidate_id = Column(Integer, ForeignKey("rms_candidates.id"), nullable=False, index=True)
        client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
        resume_id = Column(Integer, ForeignKey("rms_resumes.id"), nullable=True)
        status = Column(String, default="recommended")
        recommended_by = Column(Integer, ForeignKey("sys_user.id"), nullable=True)
        recommended_at = Column(String, default="")
        current_stage = Column(String, default="")
        last_activity_at = Column(String, default="")
        created_at = Column(String, default="")
        updated_at = Column(String, default="")

    class RmsApplicationStatusHistory(Base):
        __tablename__ = "rms_application_status_history"
        id = Column(Integer, primary_key=True, index=True)
        application_id = Column(Integer, ForeignKey("rms_applications.id"), nullable=False, index=True)
        from_status = Column(String, default="")
        to_status = Column(String, default="")
        reason = Column(String, default="")
        note = Column(Text, default="")
        changed_by = Column(Integer, ForeignKey("sys_user.id"), nullable=True)
        changed_at = Column(String, default="")

    class RmsInterview(Base):
        __tablename__ = "rms_interviews"
        id = Column(Integer, primary_key=True, index=True)
        application_id = Column(Integer, ForeignKey("rms_applications.id"), nullable=False, index=True)
        interview_time = Column(String, default="")
        interview_round = Column(String, default="")
        interviewer = Column(String, default="")
        result = Column(String, default="")
        feedback = Column(Text, default="")
        created_at = Column(String, default="")
        updated_at = Column(String, default="")

    class RmsOffer(Base):
        __tablename__ = "rms_offers"
        id = Column(Integer, primary_key=True, index=True)
        application_id = Column(Integer, ForeignKey("rms_applications.id"), nullable=False, index=True)
        offer_status = Column(String, default="")
        salary = Column(String, default="")
        expected_onboard_date = Column(String, default="")
        actual_onboard_date = Column(String, default="")
        note = Column(Text, default="")
        created_at = Column(String, default="")
        updated_at = Column(String, default="")

    class RmsMatchResult(Base):
        __tablename__ = "rms_match_results"
        id = Column(Integer, primary_key=True, index=True)
        application_id = Column(Integer, ForeignKey("rms_applications.id"), nullable=False, index=True)
        job_id = Column(Integer, ForeignKey("rms_jobs.id"), nullable=False, index=True)
        candidate_id = Column(Integer, ForeignKey("rms_candidates.id"), nullable=False)
        resume_id = Column(Integer, ForeignKey("rms_resumes.id"), nullable=True)
        score = Column(Float, nullable=True)
        summary = Column(Text, default="")
        strengths = Column(Text, default="")
        risks = Column(Text, default="")
        model_name = Column(String, default="")
        created_by = Column(Integer, ForeignKey("sys_user.id"), nullable=True)
        created_at = Column(String, default="")

    models = {
        "RmsJob": RmsJob,
        "RmsCandidate": RmsCandidate,
        "RmsResume": RmsResume,
        "RmsApplication": RmsApplication,
        "RmsApplicationStatusHistory": RmsApplicationStatusHistory,
        "RmsInterview": RmsInterview,
        "RmsOffer": RmsOffer,
        "RmsMatchResult": RmsMatchResult,
    }
    _models_cache_by_base[cache_key] = models
    return dict(models)
