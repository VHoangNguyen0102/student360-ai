"""Scholarship fit analysis workflow.

The deterministic score and hard blockers are authoritative. The optional LLM
step only improves Vietnamese wording and is allowed to fail silently.
"""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.core.database import get_pool
from app.core.llm import get_llm
from app.domains.finance.models.scholarship_fit import (
    ScholarshipFitAction,
    ScholarshipFitAnalysis,
    ScholarshipFitAnalysisRequest,
    ScholarshipFitReason,
)
from app.domains.finance.scholarships.prompts import SCHOLARSHIP_FIT_ANALYSIS_PROMPT

logger = structlog.get_logger()

ANALYSIS_TTL_HOURS = 24


class _LlmFitWording(BaseModel):
    summary: str
    reasons: list[ScholarshipFitReason] = Field(default_factory=list)
    actions: list[ScholarshipFitAction] = Field(default_factory=list)


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
        return [part.strip() for part in re.split(r"[,;\n]+", stripped) if part.strip()]
    return [str(value).strip()]


def _tokens(value: Any) -> set[str]:
    return {token for token in _normalize_text(value).split() if len(token) >= 2}


def _overlaps(left: Any, right_values: list[str]) -> bool:
    left_tokens = _tokens(left)
    if not left_tokens:
        return False
    for value in right_values:
        right_tokens = _tokens(value)
        if right_tokens and (left_tokens & right_tokens):
            return True
        if _normalize_text(left) and _normalize_text(left) == _normalize_text(value):
            return True
    return False


def _contains_any(text: str, keywords: list[str]) -> bool:
    normalized = _normalize_text(text)
    return any(keyword in normalized for keyword in keywords)


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def analyze_scholarship_fit(
    scholarship_id: str,
    req: ScholarshipFitAnalysisRequest,
) -> ScholarshipFitAnalysis:
    try:
        scholarship_uuid = str(uuid.UUID(scholarship_id))
        user_uuid = str(uuid.UUID(req.user_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid user_id or scholarship_id") from exc

    sources = await _fetch_fit_sources(user_uuid, scholarship_uuid)
    if sources["scholarship"] is None:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    if sources["user"] is None:
        raise HTTPException(status_code=404, detail="User not found")

    generated_at = _now_utc()
    profile_snapshot = _build_profile_snapshot(sources)
    scholarship_snapshot = _build_scholarship_snapshot(sources)
    reasons: list[ScholarshipFitReason] = []
    actions: list[ScholarshipFitAction] = []
    hard_blockers: list[ScholarshipFitReason] = []

    score, score_cap = _evaluate_rules(
        sources=sources,
        profile_snapshot=profile_snapshot,
        scholarship_snapshot=scholarship_snapshot,
        reasons=reasons,
        actions=actions,
        hard_blockers=hard_blockers,
        now=generated_at,
    )

    if hard_blockers:
        fit_score = 0
        fit_level = "impossible"
    else:
        fit_score = max(0, min(int(round(score)), score_cap))
        fit_level = _level_for_score(fit_score)

    summary = _build_summary(fit_level, reasons, actions, hard_blockers)
    if not hard_blockers:
        wording = await _try_refine_with_llm(
            fit_level=fit_level,
            fit_score=fit_score,
            summary=summary,
            reasons=reasons,
            actions=actions,
            profile_snapshot=profile_snapshot,
            scholarship_snapshot=scholarship_snapshot,
        )
        if wording:
            summary = wording.summary or summary
            if wording.reasons:
                reasons = wording.reasons
            if wording.actions:
                actions = wording.actions

    analysis = ScholarshipFitAnalysis(
        analysis_id=str(uuid.uuid4()),
        scholarship_id=scholarship_uuid,
        user_id=user_uuid,
        session_id=req.session_id,
        fit_level=fit_level,
        fit_label=_fit_label(fit_level),
        fit_score=fit_score,
        summary=summary,
        reasons=reasons,
        actions=actions,
        hard_blockers=hard_blockers,
        profile_snapshot=profile_snapshot,
        scholarship_snapshot=scholarship_snapshot,
        generated_at=generated_at,
        expires_at=generated_at + timedelta(hours=ANALYSIS_TTL_HOURS),
        cached=False,
    )

    logger.info(
        "scholarship_fit_analysis_generated",
        user_id=user_uuid,
        scholarship_id=scholarship_uuid,
        fit_level=analysis.fit_level,
        fit_score=analysis.fit_score,
    )
    return analysis


async def _fetch_fit_sources(user_id: str, scholarship_id: str) -> dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        scholarship = await conn.fetchrow(
            """
            SELECT s.id,
                   s.name,
                   s.description,
                   s.eligibility_criteria,
                   s.benefits,
                   s.provider,
                   s.target_majors,
                   s.target_universities,
                   s.minimum_gpa,
                   s.minimum_gpa_scale,
                   s.level,
                   s.is_active,
                   s.application_deadline,
                   sc.name AS category_name
            FROM scholarships s
            LEFT JOIN scholarship_categories sc ON sc.id = s.category_id
            WHERE s.id = $1::uuid
            LIMIT 1
            """,
            scholarship_id,
        )

        requirements = await conn.fetch(
            """
            SELECT id,
                   title,
                   description,
                   is_required,
                   sort_order
            FROM scholarship_requirements
            WHERE scholarship_id = $1::uuid
            ORDER BY is_required DESC, sort_order ASC
            """,
            scholarship_id,
        )

        documents = await conn.fetch(
            """
            SELECT id,
                   document_name,
                   document_type,
                   is_required,
                   sample_url
            FROM scholarship_documents
            WHERE scholarship_id = $1::uuid
            ORDER BY is_required DESC, created_at ASC
            """,
            scholarship_id,
        )

        user = await conn.fetchrow(
            """
            SELECT u.id AS user_id,
                   up.country,
                   up.career_goal,
                   up.summary,
                   up.interests AS interest_ids,
                   up.skill AS skill_ids
            FROM users u
            LEFT JOIN users_profiles up ON up.user_id = u.id
            WHERE u.id = $1::uuid
            LIMIT 1
            """,
            user_id,
        )

        academics = await conn.fetch(
            """
            SELECT university,
                   education_program,
                   degree_level,
                   faculty,
                   major,
                   minor,
                   program_type,
                   gpa,
                   current_year,
                   current_semester
            FROM student_academic_profiles
            WHERE user_id = $1::uuid
            ORDER BY updated_at DESC NULLS LAST
            """,
            user_id,
        )

        certificates = await conn.fetch(
            """
            SELECT sc.final_score,
                   sc.status,
                   sc.issued_date,
                   sc.expiry_date,
                   c.name AS certificate_name,
                   c.issuing_organization,
                   c.certificate_type
            FROM student_certificates sc
            JOIN certificates c ON c.id = sc.certificate_id
            WHERE sc.user_id = $1::uuid
            ORDER BY sc.created_at DESC
            """,
            user_id,
        )

        skill_ids = _as_list(user.get("skill_ids") if user else None)
        interest_ids = _as_list(user.get("interest_ids") if user else None)
        skills = []
        interests = []
        if skill_ids:
            skills = await conn.fetch("SELECT name FROM skills WHERE id = ANY($1::uuid[])", skill_ids)
        if interest_ids:
            interests = await conn.fetch("SELECT name FROM profile_interests WHERE id = ANY($1::uuid[])", interest_ids)

    return {
        "scholarship": dict(scholarship) if scholarship else None,
        "requirements": [dict(item) for item in requirements],
        "documents": [dict(item) for item in documents],
        "user": dict(user) if user else None,
        "academics": [dict(item) for item in academics],
        "certificates": [dict(item) for item in certificates],
        "skills": [dict(item) for item in skills],
        "interests": [dict(item) for item in interests],
    }


def _build_profile_snapshot(sources: dict[str, Any]) -> dict[str, Any]:
    user = sources.get("user") or {}
    academics = sources.get("academics") or []
    latest_academic = academics[0] if academics else {}
    certificates = sources.get("certificates") or []
    return _serialize(
        {
            "major": latest_academic.get("major"),
            "faculty": latest_academic.get("faculty"),
            "university": latest_academic.get("university"),
            "degreeLevel": latest_academic.get("degree_level"),
            "currentYear": latest_academic.get("current_year"),
            "currentSemester": latest_academic.get("current_semester"),
            "gpa": latest_academic.get("gpa"),
            "gpaScale": 4,
            "country": user.get("country"),
            "careerGoal": user.get("career_goal"),
            "skills": [item.get("name") for item in sources.get("skills", []) if item.get("name")],
            "interests": [item.get("name") for item in sources.get("interests", []) if item.get("name")],
            "certificatesCount": len(certificates),
            "certificates": [
                {
                    "name": item.get("certificate_name"),
                    "type": item.get("certificate_type"),
                    "finalScore": item.get("final_score"),
                    "status": item.get("status"),
                }
                for item in certificates
            ],
        }
    )


def _build_scholarship_snapshot(sources: dict[str, Any]) -> dict[str, Any]:
    row = sources.get("scholarship") or {}
    return _serialize(
        {
            "title": row.get("name"),
            "provider": row.get("provider"),
            "category": row.get("category_name"),
            "isActive": row.get("is_active"),
            "applicationDeadline": row.get("application_deadline"),
            "minimumGpa": row.get("minimum_gpa"),
            "minimumGpaScale": row.get("minimum_gpa_scale") or 4,
            "targetMajors": _as_list(row.get("target_majors")),
            "targetUniversities": _as_list(row.get("target_universities")),
            "level": row.get("level"),
            "requiredDocumentsCount": len([doc for doc in sources.get("documents", []) if doc.get("is_required")]),
        }
    )


def _evaluate_rules(
    *,
    sources: dict[str, Any],
    profile_snapshot: dict[str, Any],
    scholarship_snapshot: dict[str, Any],
    reasons: list[ScholarshipFitReason],
    actions: list[ScholarshipFitAction],
    hard_blockers: list[ScholarshipFitReason],
    now: datetime,
) -> tuple[int, int]:
    scholarship = sources["scholarship"]
    requirements = sources.get("requirements") or []
    documents = sources.get("documents") or []
    score = 50
    score_cap = 100

    deadline = _ensure_aware(scholarship.get("application_deadline"))
    if scholarship.get("is_active") is False:
        blocker = ScholarshipFitReason(
            code="scholarship_inactive",
            severity="blocker",
            message="Học bổng hiện không còn hoạt động nên bạn chưa thể nộp hồ sơ.",
            evidence="scholarship.is_active=false",
        )
        hard_blockers.append(blocker)
        reasons.append(blocker)
    elif deadline and deadline < now:
        blocker = ScholarshipFitReason(
            code="deadline_passed",
            severity="blocker",
            message="Học bổng đã hết hạn nộp hồ sơ.",
            evidence=f"Deadline: {deadline.isoformat()}",
        )
        hard_blockers.append(blocker)
        reasons.append(blocker)
    else:
        score += 10
        reasons.append(
            ScholarshipFitReason(
                code="scholarship_open",
                severity="positive",
                message="Học bổng đang mở hoặc chưa có hạn nộp kết thúc.",
                evidence=f"Active: {scholarship.get('is_active')}; deadline: {deadline.isoformat() if deadline else 'not specified'}",
            )
        )

    profile_major = profile_snapshot.get("major") or profile_snapshot.get("faculty")
    target_majors = scholarship_snapshot.get("targetMajors") or []
    text_blob = _scholarship_text_blob(scholarship, requirements, documents)
    if target_majors and profile_major:
        if _overlaps(profile_major, target_majors):
            score += 20
            reasons.append(
                ScholarshipFitReason(
                    code="major_match",
                    severity="positive",
                    message="Ngành hoặc khoa trong hồ sơ của bạn khớp với nhóm ngành mục tiêu.",
                    evidence=f"Profile major/faculty: {profile_major}; targetMajors: {', '.join(target_majors)}",
                )
            )
        else:
            strict_major = _contains_any(
                text_blob,
                ["chi danh cho", "bat buoc nganh", "only for", "must be major", "danh rieng cho"],
            )
            reason = ScholarshipFitReason(
                code="major_mismatch",
                severity="blocker" if strict_major else "warning",
                message="Ngành hoặc khoa trong hồ sơ hiện tại chưa khớp với nhóm ngành mục tiêu của học bổng.",
                evidence=f"Profile major/faculty: {profile_major}; targetMajors: {', '.join(target_majors)}",
            )
            reasons.append(reason)
            if strict_major:
                hard_blockers.append(reason)
            else:
                score -= 20
                score_cap = min(score_cap, 45)
    elif target_majors and not profile_major:
        score -= 5
        reasons.append(
            ScholarshipFitReason(
                code="missing_profile_major",
                severity="unknown",
                message="Hồ sơ hiện tại chưa có ngành học rõ ràng để đối chiếu với học bổng.",
                evidence=f"targetMajors: {', '.join(target_majors)}",
            )
        )
        actions.append(
            ScholarshipFitAction(
                code="update_major",
                priority="medium",
                message="Cập nhật ngành học/khoa trong hồ sơ để AI đánh giá chính xác hơn.",
            )
        )
    else:
        score += 5

    profile_university = profile_snapshot.get("university")
    target_universities = scholarship_snapshot.get("targetUniversities") or []
    if target_universities and profile_university:
        if _overlaps(profile_university, target_universities):
            score += 15
            reasons.append(
                ScholarshipFitReason(
                    code="university_match",
                    severity="positive",
                    message="Trường trong hồ sơ của bạn khớp với trường mục tiêu của học bổng.",
                    evidence=f"Profile university: {profile_university}; targetUniversities: {', '.join(target_universities)}",
                )
            )
        else:
            reason = ScholarshipFitReason(
                code="university_mismatch",
                severity="blocker",
                message="Học bổng giới hạn cho trường khác với trường trong hồ sơ hiện tại của bạn.",
                evidence=f"Profile university: {profile_university}; targetUniversities: {', '.join(target_universities)}",
            )
            reasons.append(reason)
            hard_blockers.append(reason)
    elif target_universities and not profile_university:
        score -= 5
        reasons.append(
            ScholarshipFitReason(
                code="missing_profile_university",
                severity="unknown",
                message="Hồ sơ hiện tại chưa có trường học để đối chiếu với học bổng.",
                evidence=f"targetUniversities: {', '.join(target_universities)}",
            )
        )
    else:
        score += 5

    profile_gpa = _to_float(profile_snapshot.get("gpa"))
    required_gpa = _to_float(scholarship.get("minimum_gpa"))
    scale = scholarship.get("minimum_gpa_scale") or 4
    if required_gpa is not None:
        if profile_gpa is None:
            score -= 10
            reasons.append(
                ScholarshipFitReason(
                    code="missing_profile_gpa",
                    severity="unknown",
                    message="Hồ sơ hiện tại chưa có GPA để kiểm tra yêu cầu tối thiểu.",
                    evidence=f"Required GPA: {required_gpa}/{scale}",
                )
            )
            actions.append(
                ScholarshipFitAction(
                    code="update_gpa",
                    priority="high",
                    message="Cập nhật GPA hiện tại trong hồ sơ trước khi quyết định nộp.",
                )
            )
        elif profile_gpa >= required_gpa:
            score += 15
            reasons.append(
                ScholarshipFitReason(
                    code="gpa_meets_requirement",
                    severity="positive",
                    message="GPA hiện tại đáp ứng yêu cầu tối thiểu của học bổng.",
                    evidence=f"Profile GPA: {profile_gpa}; required GPA: {required_gpa}/{scale}",
                )
            )
        else:
            delta = required_gpa - profile_gpa
            score -= 5 if delta <= 0.3 else 15
            reasons.append(
                ScholarshipFitReason(
                    code="gpa_below_requirement",
                    severity="improvable",
                    message="GPA hiện tại thấp hơn yêu cầu tối thiểu nhưng đây là điểm có thể cải thiện.",
                    evidence=f"Profile GPA: {profile_gpa}; required GPA: {required_gpa}/{scale}",
                )
            )
            actions.append(
                ScholarshipFitAction(
                    code="improve_gpa",
                    priority="high",
                    message=f"Ưu tiên cải thiện GPA lên tối thiểu {required_gpa}/{scale} trước khi nộp.",
                )
            )

    language_required = _detect_language_requirement(text_blob)
    if language_required:
        if _has_language_certificate(sources.get("certificates") or []):
            score += 10
            reasons.append(
                ScholarshipFitReason(
                    code="language_certificate_present",
                    severity="positive",
                    message="Hồ sơ đã có chứng chỉ ngoại ngữ để tham chiếu với yêu cầu học bổng.",
                    evidence="At least one language certificate found in profile.",
                )
            )
        else:
            score -= 10
            reasons.append(
                ScholarshipFitReason(
                    code="missing_language_certificate",
                    severity="improvable",
                    message="Hồ sơ hiện tại chưa có chứng chỉ ngoại ngữ được ghi nhận.",
                    evidence="Language requirement detected from scholarship text/requirements.",
                )
            )
            actions.append(
                ScholarshipFitAction(
                    code="add_language_certificate",
                    priority="medium",
                    message="Cập nhật chứng chỉ ngoại ngữ nếu đã có, hoặc lên kế hoạch thi theo yêu cầu học bổng.",
                )
            )

    if _contains_any(text_blob, ["hoan canh kho khan", "need based", "financial hardship", "kho khan tai chinh"]):
        score -= 10
        reasons.append(
            ScholarshipFitReason(
                code="hardship_evidence_missing",
                severity="warning",
                message="Học bổng có dấu hiệu ưu tiên/yêu cầu hoàn cảnh khó khăn, nhưng hồ sơ hiện tại chưa có thông tin chứng minh điều kiện này.",
                evidence="Need-based/hardship language detected in scholarship text.",
            )
        )
        actions.append(
            ScholarshipFitAction(
                code="prepare_hardship_evidence",
                priority="medium",
                message="Nếu thuộc diện phù hợp, chuẩn bị hoặc cập nhật giấy tờ chứng minh hoàn cảnh theo yêu cầu học bổng.",
            )
        )

    required_docs = [doc for doc in documents if doc.get("is_required")]
    if required_docs:
        actions.append(
            ScholarshipFitAction(
                code="prepare_required_documents",
                priority="medium",
                message=f"Chuẩn bị {len(required_docs)} giấy tờ bắt buộc trước khi nộp hồ sơ.",
            )
        )

    return score, score_cap


def _scholarship_text_blob(
    scholarship: dict[str, Any],
    requirements: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> str:
    parts = [
        scholarship.get("name"),
        scholarship.get("description"),
        scholarship.get("eligibility_criteria"),
        scholarship.get("benefits"),
        scholarship.get("level"),
    ]
    for item in requirements:
        parts.extend([item.get("title"), item.get("description")])
    for item in documents:
        parts.append(item.get("document_name"))
    return " ".join(str(part) for part in parts if part)


def _detect_language_requirement(text: str) -> bool:
    return _contains_any(text, ["ielts", "toeic", "toefl", "language certificate", "ngoai ngu", "tieng anh"])


def _has_language_certificate(certificates: list[dict[str, Any]]) -> bool:
    for cert in certificates:
        text = " ".join(
            str(cert.get(key) or "")
            for key in ["certificate_name", "certificate_type", "issuing_organization"]
        )
        if _detect_language_requirement(text):
            return True
    return False


def _level_for_score(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _fit_label(level: str) -> str:
    return {
        "high": "Cao",
        "medium": "Trung bình",
        "low": "Thấp",
        "impossible": "Không thể nộp",
    }.get(level, "Thấp")


def _build_summary(
    fit_level: str,
    reasons: list[ScholarshipFitReason],
    actions: list[ScholarshipFitAction],
    hard_blockers: list[ScholarshipFitReason],
) -> str:
    if hard_blockers:
        return "Học bổng này hiện không thể nộp dựa trên dữ liệu hệ thống, vì có điều kiện chặn cứng."
    positives = len([reason for reason in reasons if reason.severity == "positive"])
    improvables = len([reason for reason in reasons if reason.severity == "improvable"])
    if fit_level == "high":
        return "Bạn có mức độ phù hợp cao với học bổng này; hãy rà soát giấy tờ và chuẩn bị hồ sơ nộp."
    if fit_level == "medium":
        return f"Bạn có một số điểm phù hợp ({positives}) nhưng vẫn còn điểm cần cải thiện ({improvables}) trước khi nộp."
    return "Mức độ phù hợp hiện còn thấp; nên ưu tiên xử lý các điểm thiếu hoặc cân nhắc học bổng phù hợp hơn."


async def _try_refine_with_llm(
    *,
    fit_level: str,
    fit_score: int,
    summary: str,
    reasons: list[ScholarshipFitReason],
    actions: list[ScholarshipFitAction],
    profile_snapshot: dict[str, Any],
    scholarship_snapshot: dict[str, Any],
) -> _LlmFitWording | None:
    payload = {
        "fit_level": fit_level,
        "fit_score": fit_score,
        "summary": summary,
        "reasons": [reason.model_dump() for reason in reasons],
        "actions": [action.model_dump() for action in actions],
        "profile_snapshot": profile_snapshot,
        "scholarship_snapshot": scholarship_snapshot,
    }
    try:
        llm = get_llm(temperature=0)
        response = await llm.ainvoke(
            [
                {"role": "system", "content": SCHOLARSHIP_FIT_ANALYSIS_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
        )
        content = response.content
        if isinstance(content, list):
            content = " ".join(block.get("text", "") for block in content if isinstance(block, dict))
        text = str(content or "")
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return _LlmFitWording.model_validate(json.loads(text[start : end + 1]))
    except (Exception, ValidationError) as exc:
        logger.warning("scholarship_fit_llm_refine_failed", error=str(exc))
        return None
