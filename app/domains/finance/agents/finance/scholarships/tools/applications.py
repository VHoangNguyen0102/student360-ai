"""Scholarship application tools -- ho so xin hoc bong cua sinh vien.

Schema thuc te (tu s360-backend entities):
  student_scholarships       -- ho so apply hoc bong cua sinh vien
  student_scholarship_documents -- tai lieu sinh vien da nop
  scholarship_documents      -- danh sach tai lieu yeu cau cua hoc bong
  scholarship_requirements   -- dieu kien/yeu cau cua hoc bong
  scholarship_reviews        -- lich su xet duyet (theo stage)

Tools:
  get_my_scholarship_applications    -- Lay danh sach hoc bong sinh vien da apply
                                        (tat ca, co the loc theo status)
  get_scholarship_application_detail -- Lay chi tiet 1 ho so apply + tai lieu da nop
                                        + lich su xet duyet
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.database import get_pool

logger = structlog.get_logger()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _serialize(value: Any) -> Any:
    """Recursively make asyncpg data JSON-serializable."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def _uid(config: RunnableConfig) -> str:
    return config["configurable"]["user_id"]


# ──────────────────────────────────────────────────────────────────────────────
# Tool 1: Lay danh sach tat ca don hoc bong sinh vien da apply
# ──────────────────────────────────────────────────────────────────────────────


@tool
async def get_my_scholarship_applications(
    config: RunnableConfig,
    status_filter: str = "",
) -> str:
    """
    Lấy danh sách tất cả hồ sơ xin học bổng của sinh viên đang đăng nhập.

    Args:
        status_filter: Lọc theo trạng thái hồ sơ. Các giá trị hợp lệ:
            - "" (chuỗi rỗng): lấy tất cả
            - "draft": bản nháp, chưa nộp
            - "submitted": đã nộp, chờ xét duyệt
            - "under_review" hoặc "reviewing": đang trong quá trình xét duyệt
            - "approved": đã được phê duyệt
            - "rejected": bị từ chối
            - "awarded": đã nhận học bổng
            - "cancelled": đã hủy

    Trả về:
        Danh sách hồ sơ apply với thông tin: tên học bổng, nhà cung cấp,
        trạng thái, ngày nộp, ngày quyết định, số tiền học bổng, ghi chú.

    Sử dụng tool này khi sinh viên hỏi:
        - "Tôi đang apply học bổng nào?"
        - "Học bổng của tôi đang ở trạng thái gì?"
        - "Tôi có hồ sơ học bổng nào đang chờ xét duyệt không?"
    """
    user_id = _uid(config)
    status = (status_filter or "").strip().lower()

    # Normalize alias: DB dung 'under_review' thay vi 'reviewing'
    if status == "reviewing":
        status = "under_review"

    valid_statuses = {"draft", "submitted", "under_review", "approved", "rejected", "awarded", "cancelled"}
    if status and status not in valid_statuses:
        return json.dumps(
            {
                "error": f"status_filter không hợp lệ: '{status}'. Giá trị hợp lệ: {sorted(valid_statuses)}",
            },
            ensure_ascii=False,
        )

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT
                        ss.id,
                        ss.scholarship_id,
                        s.name               AS scholarship_name,
                        s.provider,
                        s.amount             AS scholarship_amount,
                        s.currency           AS scholarship_currency,
                        ss.status,
                        ss.application_date,
                        ss.decision_date,
                        ss.awarded_amount,
                        ss.currency,
                        ss.submitted_form_url,
                        ss.note,
                        ss.feedback,
                        ss.created_at,
                        ss.updated_at
                    FROM   student_scholarships ss
                    JOIN   scholarships s ON s.id = ss.scholarship_id
                    WHERE  ss.user_id = $1
                      AND  ss.status  = $2
                    ORDER  BY ss.created_at DESC
                    """,
                    user_id,
                    status,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT
                        ss.id,
                        ss.scholarship_id,
                        s.name               AS scholarship_name,
                        s.provider,
                        s.amount             AS scholarship_amount,
                        s.currency           AS scholarship_currency,
                        ss.status,
                        ss.application_date,
                        ss.decision_date,
                        ss.awarded_amount,
                        ss.currency,
                        ss.submitted_form_url,
                        ss.note,
                        ss.feedback,
                        ss.created_at,
                        ss.updated_at
                    FROM   student_scholarships ss
                    JOIN   scholarships s ON s.id = ss.scholarship_id
                    WHERE  ss.user_id = $1
                    ORDER  BY ss.created_at DESC
                    """,
                    user_id,
                )

        if not rows:
            msg = (
                f"Không tìm thấy hồ sơ học bổng nào với trạng thái '{status}'."
                if status
                else "Sinh viên chưa có hồ sơ xin học bổng nào trong hệ thống."
            )
            return json.dumps(
                {"user_id": user_id, "applications": [], "total": 0, "message": msg},
                ensure_ascii=False,
            )

        applications = [_serialize(dict(r)) for r in rows]

        # Thong ke nhanh theo status
        status_counts: dict[str, int] = {}
        for app in applications:
            s = app.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1

        return json.dumps(
            {
                "user_id": user_id,
                "total": len(applications),
                "status_counts": status_counts,
                "filter_applied": status or "none",
                "applications": applications,
            },
            ensure_ascii=False,
        )

    except Exception as exc:
        logger.error("get_my_scholarship_applications_failed", error=str(exc), user_id=user_id)
        return json.dumps(
            {"error": f"Lỗi truy vấn danh sách hồ sơ học bổng: {str(exc)}"},
            ensure_ascii=False,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Tool 2: Lay chi tiet 1 ho so apply (bao gom tai lieu, lich su xet duyet,
#         va yeu cau cua hoc bong) -- dung cho LLM du doan ty le trung tuyen
# ──────────────────────────────────────────────────────────────────────────────


@tool
async def get_scholarship_application_detail(
    application_id: str,
    config: RunnableConfig,
) -> str:
    """
    Lấy thông tin đầy đủ của một hồ sơ xin học bổng cụ thể, bao gồm:
      - Thông tin hồ sơ apply: trạng thái, ngày nộp, ghi chú, phản hồi
      - Thông tin học bổng: tên, nhà cung cấp, số tiền, điều kiện xét tuyển,
        danh sách yêu cầu (scholarship_requirements) và tài liệu yêu cầu
        (scholarship_documents)
      - Tài liệu sinh viên đã nộp (student_scholarship_documents): tên tài liệu,
        URL, trạng thái (pending/approved/rejected), ghi chú của người xét duyệt
      - Lịch sử xét duyệt (scholarship_reviews): giai đoạn, trạng thái, nhận xét

    Thông tin này dùng để LLM phân tích và dự đoán tỉ lệ trúng tuyển học bổng
    bằng cách so sánh hồ sơ sinh viên với yêu cầu của học bổng.

    Args:
        application_id: UUID của hồ sơ apply (lấy từ get_my_scholarship_applications).

    Sử dụng tool này khi:
        - Sinh viên hỏi về tỉ lệ trúng tuyển / khả năng được duyệt
        - Cần chi tiết hồ sơ để đánh giá mức độ đáp ứng yêu cầu
        - Muốn biết tài liệu nào còn thiếu hoặc bị từ chối
    """
    raw_id = (application_id or "").strip()
    if not raw_id:
        return json.dumps({"error": "application_id là bắt buộc."}, ensure_ascii=False)

    try:
        app_uuid = str(uuid.UUID(raw_id))
    except ValueError:
        return json.dumps(
            {"error": "application_id phải là UUID hợp lệ.", "application_id": raw_id},
            ensure_ascii=False,
        )

    user_id = _uid(config)

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:

            # 1. Lay thong tin ho so apply + thong tin hoc bong
            app_row = await conn.fetchrow(
                """
                SELECT
                    ss.id,
                    ss.user_id,
                    ss.scholarship_id,
                    ss.status,
                    ss.application_date,
                    ss.decision_date,
                    ss.awarded_amount,
                    ss.currency,
                    ss.submitted_form_url,
                    ss.note,
                    ss.feedback,
                    ss.reviewer_id,
                    ss.created_at,
                    ss.updated_at,
                    -- Thong tin hoc bong
                    s.name                      AS scholarship_name,
                    s.description               AS scholarship_description,
                    s.eligibility_criteria,
                    s.provider,
                    s.amount                    AS scholarship_amount,
                    s.currency                  AS scholarship_currency,
                    s.quantity,
                    s.benefits,
                    s.application_deadline,
                    s.result_announcement_date,
                    s.contact_email,
                    s.contact_phone,
                    s.official_website,
                    s.is_active,
                    sc.name                     AS category_name
                FROM   student_scholarships ss
                JOIN   scholarships s  ON s.id  = ss.scholarship_id
                LEFT JOIN scholarship_categories sc ON sc.id = s.category_id
                WHERE  ss.id      = $1
                  AND  ss.user_id = $2
                LIMIT  1
                """,
                app_uuid,
                user_id,
            )

            if app_row is None:
                return json.dumps(
                    {
                        "error": "Không tìm thấy hồ sơ hoặc bạn không có quyền truy cập.",
                        "application_id": app_uuid,
                        "user_id": user_id,
                    },
                    ensure_ascii=False,
                )

            scholarship_id = str(app_row["scholarship_id"])

            # 2. Yeu cau cua hoc bong (scholarship_requirements)
            req_rows = await conn.fetch(
                """
                SELECT id, title, description, is_required, sort_order
                FROM   scholarship_requirements
                WHERE  scholarship_id = $1
                ORDER  BY sort_order ASC, created_at ASC
                """,
                scholarship_id,
            )

            # 3. Tai lieu yeu cau cua hoc bong (scholarship_documents)
            req_doc_rows = await conn.fetch(
                """
                SELECT id, document_name, document_type, is_required,
                       max_file_size_mb, sample_url
                FROM   scholarship_documents
                WHERE  scholarship_id = $1
                ORDER  BY is_required DESC, created_at ASC
                """,
                scholarship_id,
            )

            # 4. Tai lieu sinh vien da nop (student_scholarship_documents)
            #    JOIN voi scholarship_documents de lay ten tai lieu
            submitted_doc_rows = await conn.fetch(
                """
                SELECT
                    ssd.id,
                    ssd.document_id,
                    sd.document_name,
                    sd.document_type,
                    sd.is_required,
                    ssd.file_url,
                    ssd.upload_date,
                    ssd.status,
                    ssd.reviewer_note,
                    ssd.created_at
                FROM   student_scholarship_documents ssd
                JOIN   scholarship_documents sd ON sd.id = ssd.document_id
                WHERE  ssd.student_scholarship_id = $1
                ORDER  BY ssd.created_at ASC
                """,
                app_uuid,
            )

            # 5. Lich su xet duyet (scholarship_reviews)
            review_rows = await conn.fetch(
                """
                SELECT id, reviewer_id, stage, status, comment, reviewed_at, created_at
                FROM   scholarship_reviews
                WHERE  student_scholarship_id = $1
                ORDER  BY created_at ASC
                """,
                app_uuid,
            )

        # ---------- Tong hop ket qua ----------
        application_data = dict(app_row)
        requirements = [dict(r) for r in req_rows]
        required_docs = [dict(r) for r in req_doc_rows]
        submitted_docs = [dict(r) for r in submitted_doc_rows]
        reviews = [dict(r) for r in review_rows]

        # Thong ke tai lieu da nop
        submitted_doc_status: dict[str, int] = {}
        for doc in submitted_docs:
            s = doc.get("status", "unknown")
            submitted_doc_status[s] = submitted_doc_status.get(s, 0) + 1

        # Tai lieu bat buoc chua nop: so sanh required_docs vs submitted_docs
        submitted_doc_ids = {str(d["document_id"]) for d in submitted_docs}
        missing_required_docs = [
            d for d in required_docs
            if d.get("is_required") and str(d["id"]) not in submitted_doc_ids
        ]

        # Yeu cau hoc bong
        required_req_count = sum(1 for r in requirements if r.get("is_required"))

        payload = {
            "application": _serialize(application_data),
            "scholarship_requirements": {
                "total": len(requirements),
                "required_count": required_req_count,
                "items": _serialize(requirements),
            },
            "scholarship_required_documents": {
                "total": len(required_docs),
                "required_count": sum(1 for d in required_docs if d.get("is_required")),
                "items": _serialize(required_docs),
            },
            "submitted_documents": {
                "total": len(submitted_docs),
                "status_summary": submitted_doc_status,
                "missing_required_docs": _serialize(missing_required_docs),
                "items": _serialize(submitted_docs),
            },
            "review_history": {
                "total_reviews": len(reviews),
                "items": _serialize(reviews),
            },
            # Tong hop nhanh cho LLM du doan
            "eligibility_summary": {
                "eligibility_criteria": _serialize(application_data.get("eligibility_criteria")),
                "application_status": _serialize(application_data.get("status")),
                "feedback_from_reviewer": _serialize(application_data.get("feedback")),
                "note": _serialize(application_data.get("note")),
                "has_missing_required_docs": len(missing_required_docs) > 0,
                "missing_required_doc_count": len(missing_required_docs),
                "all_required_docs_approved": all(
                    d.get("status") == "approved"
                    for d in submitted_docs
                    if d.get("is_required")
                ) if submitted_docs else False,
            },
        }

        return json.dumps(payload, ensure_ascii=False)

    except Exception as exc:
        logger.error(
            "get_scholarship_application_detail_failed",
            error=str(exc),
            application_id=raw_id,
            user_id=user_id,
        )
        return json.dumps(
            {
                "error": f"Lỗi lấy chi tiết hồ sơ học bổng: {str(exc)}",
                "application_id": raw_id,
            },
            ensure_ascii=False,
        )
