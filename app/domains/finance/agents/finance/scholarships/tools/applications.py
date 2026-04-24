"""Scholarship application tools -- ho so xin hoc bong cua sinh vien.

NOTE: Ten bang `scholarship_applications` va cac cot ben duoi la GIA DINH (mock).
Khi co schema DB chinh thuc, refactor lai ten bang / cot tuong ung.

Tools:
  get_current_scholarship_application -- Lay ho so hoc bong dang pending cua sinh vien
                                         (tu dong tim, khong can truyen ID)
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
# Mock data -- dung khi DB chua co bang thuc
# Xoa / comment block nay khi co schema that
#
# 1 ho so duy nhat voi day du thong tin sinh vien + tai lieu da nop chi tiet
# de LLM co the dua ra tu van ca nhan hoa ma khong can hoi nguoc lai nguoi dung.
# ──────────────────────────────────────────────────────────────────────────────

_MOCK_PENDING_APPLICATION: dict[str, Any] = {
    "id": "aaaaaaaa-0001-0001-0001-000000000002",
    "scholarship_id": "bbbbbbbb-0001-0001-0001-000000000002",
    "scholarship_name": "Hoc bong Vuot kho Vuon len 2024",
    "provider": "Quy Ho tro Sinh vien - Truong DH KHTN TP.HCM",
    "status": "pending",
    "applied_at": "2025-02-15T09:30:00",
    "reviewed_at": None,
    "amount_awarded": None,
    "currency": "VND",
    "rejection_reason": None,
    "notes": "Ho so dang trong giai doan tham dinh lan 2 boi Phong Cong tac Sinh vien.",
    # Thong tin sinh vien nop don
    "student_profile": {
        "full_name": "Nguyen Van An",
        "student_id": "21120001",
        "email": "21120001@student.hcmus.edu.vn",
        "phone": "0901234567",
        "major": "Khoa hoc May tinh",
        "faculty": "Khoa Cong nghe Thong tin",
        "year_of_study": 3,
        "enrollment_status": "active",
        "academic": {
            "gpa_latest_semester": 3.42,
            "gpa_cumulative": 3.38,
            "gpa_scale": 4.0,
            "drl_latest_semester": 85,
            "drl_classification": "Tot",
            "credits_completed": 90,
            "credits_total_program": 150,
            "academic_warnings": 0,
            "academic_rank": "Kha",
        },
        "socioeconomic": {
            "household_income_monthly_vnd": 3800000,
            "income_per_capita_monthly_vnd": 950000,
            "household_size": 4,
            "household_classification": "Can ngheo",
            "poverty_cert_issued_by": "UBND Phuong 5, Quan Binh Thanh, TP.HCM",
            "poverty_cert_valid_until": "2025-12-31",
            "living_situation": "O tro xa nha",
            "monthly_living_cost_vnd": 4200000,
            "has_part_time_job": True,
            "part_time_income_monthly_vnd": 2500000,
            "part_time_job_description": "Gia su toan, 3 buoi/tuan",
        },
        "family_background": {
            "father_status": "Mat suc lao dong (tai nan lao dong nam 2021, mat 65% suc lao dong)",
            "mother_status": "Lam noi tro, thu nhap khong on dinh (ban hang online)",
            "siblings": [
                {
                    "relation": "Em gai",
                    "age": 16,
                    "education": "Hoc sinh THPT",
                    "receiving_scholarship": True,
                }
            ],
            "special_circumstances": (
                "Cha bi tai nan lao dong nam 2021, mat 65% suc lao dong. "
                "Gia dinh phu thuoc vao tro cap BHXH 1.800.000 VND/thang va thu nhap bat on cua me. "
                "Sinh vien tu trang trai phan lon chi phi hoc tap va sinh hoat bang viec lam them."
            ),
        },
        "achievements": [
            {
                "title": "Giai Ba - Cuoc thi Lap trinh ACM-ICPC cap truong 2023",
                "issued_by": "Khoa CNTT - DH KHTN",
                "year": 2023,
            },
            {
                "title": "Tinh nguyen vien - Chien dich Mua he Xanh 2023",
                "issued_by": "Doan Thanh nien DH KHTN",
                "year": 2023,
                "volunteer_hours": 120,
            },
            {
                "title": "Chung chi TOEIC 650",
                "issued_by": "IIG Vietnam",
                "year": 2024,
            },
        ],
    },
    # Danh gia so bo tu can bo Phong CTSV
    "preliminary_assessment": {
        "assessed_by": "Can bo Phong CTSV - Tran Thi Bich",
        "assessed_at": "2025-03-01T14:00:00",
        "meets_gpa_threshold": True,
        "meets_drl_threshold": True,
        "meets_income_threshold": True,
        "completeness_score": 95,
        "missing_items": ["Xac nhan BHXH cua cha (bo sung truoc 20/03/2025)"],
        "notes_for_committee": (
            "Sinh vien dap ung du dieu kien co ban (GPA >= 3.2, DRL >= 80, thu nhap binh quan < 1.500.000 VND/nguoi/thang). "
            "Hoan canh cha mat suc lao dong da duoc xac minh. "
            "Cho bo sung ban xac nhan BHXH de hoan chinh ho so."
        ),
    },
    # Tai lieu da nop kem content_summary chi tiet
    "submitted_documents": [
        {
            "document_name": "Bang diem HK1 2024-2025",
            "document_type": "transcript",
            "submitted_at": "2025-02-15T09:35:00",
            "status": "accepted",
            "reviewer_note": "Bang diem hop le, co dau do Phong Dao tao. GPA 3.42/4.0.",
            "content_summary": {
                "semester": "HK1 2024-2025",
                "gpa": 3.42,
                "total_credits": 18,
                "passed_credits": 18,
                "failed_subjects": [],
                "subjects": [
                    {"name": "Tri tue Nhan tao", "credits": 3, "grade": "A", "gpa_point": 4.0},
                    {"name": "Mang May tinh", "credits": 3, "grade": "B+", "gpa_point": 3.5},
                    {"name": "Ky nghe Phan mem", "credits": 3, "grade": "A-", "gpa_point": 3.7},
                    {"name": "Co so Du lieu Nang cao", "credits": 3, "grade": "B+", "gpa_point": 3.5},
                    {"name": "Kinh te Dai cuong", "credits": 3, "grade": "B", "gpa_point": 3.0},
                    {"name": "Giao duc The chat", "credits": 3, "grade": "A", "gpa_point": 4.0},
                ],
            },
        },
        {
            "document_name": "Giay xac nhan sinh vien dang hoc",
            "document_type": "enrollment_cert",
            "submitted_at": "2025-02-15T09:38:00",
            "status": "accepted",
            "reviewer_note": "Hop le, con hieu luc den 31/08/2025.",
            "content_summary": {
                "issued_by": "Phong Dao tao - DH KHTN TP.HCM",
                "issue_date": "2025-02-10",
                "valid_until": "2025-08-31",
                "confirms": "Sinh vien nam 3, he chinh quy, chua bi canh cao hoc vu.",
            },
        },
        {
            "document_name": "Giay xac nhan ho can ngheo",
            "document_type": "poverty_cert",
            "submitted_at": "2025-02-15T09:42:00",
            "status": "accepted",
            "reviewer_note": "Xac nhan can ngheo con hieu luc. Thu nhap binh quan 950.000 VND/nguoi/thang.",
            "content_summary": {
                "classification": "Ho can ngheo",
                "issued_by": "UBND Phuong 5, Quan Binh Thanh, TP.HCM",
                "issue_date": "2025-01-10",
                "valid_until": "2025-12-31",
                "income_per_capita_monthly_vnd": 950000,
                "household_size": 4,
            },
        },
        {
            "document_name": "Don xin hoc bong (tu viet tay)",
            "document_type": "application_letter",
            "submitted_at": "2025-02-15T09:45:00",
            "status": "accepted",
            "reviewer_note": "Don trinh bay ro rang, co chu ky va xac nhan Khoa.",
            "content_summary": {
                "stated_purpose": (
                    "Sinh vien trinh bay hoan canh cha mat suc lao dong do tai nan, "
                    "me thu nhap khong on dinh. Mong muon nhan hoc bong de trang trai "
                    "hoc phi va tap trung hoc tap, huong toi tot nghiep loai Gioi."
                ),
                "commitment": "Cam ket duy tri GPA >= 3.2 va DRL >= 80 trong cac hoc ky tiep theo.",
                "signed_by_faculty": True,
                "faculty_endorsement": (
                    "Khoa CNTT xac nhan sinh vien co tinh than hoc tap tot, "
                    "tich cuc tham gia hoat dong Doan."
                ),
            },
        },
        {
            "document_name": "Xac nhan BHXH cua cha (bo sung)",
            "document_type": "social_insurance_cert",
            "submitted_at": None,
            "status": "missing",
            "reviewer_note": (
                "Chua nop. Han bo sung: 20/03/2025. "
                "Neu khong nop, ho so se bi loai khoi vong xet duyet."
            ),
            "content_summary": None,
        },
    ],
}


# ──────────────────────────────────────────────────────────────────────────────
# DB helper (se thay the mock khi co schema that)
# ──────────────────────────────────────────────────────────────────────────────


async def _fetch_pending_application_from_db(user_id: str) -> dict[str, Any] | None:
    """
    Lay don hoc bong dang pending cua sinh vien tu DB.

    TODO: Thay ten bang va cac cot khi co schema that.
          Hien tai raise NotImplementedError de roi vao mock fallback.
    """
    raise NotImplementedError("DB table name not confirmed -- using mock data")

    # --- Template SQL de refactor sau ---
    # pool = await get_pool()
    # async with pool.acquire() as conn:
    #     row = await conn.fetchrow(
    #         """
    #         SELECT sa.id,
    #                sa.scholarship_id,
    #                s.name               AS scholarship_name,
    #                s.provider,
    #                sa.status,
    #                sa.applied_at,
    #                sa.reviewed_at,
    #                sa.amount_awarded,
    #                sa.currency,
    #                sa.rejection_reason,
    #                sa.notes
    #         FROM   scholarship_applications sa   -- TODO: xac nhan ten bang
    #         JOIN   scholarships s ON s.id = sa.scholarship_id
    #         WHERE  sa.user_id    = $1
    #           AND  sa.status     = 'pending'
    #           AND  sa.is_deleted = false
    #         ORDER  BY sa.applied_at DESC
    #         LIMIT  1
    #         """,
    #         user_id,
    #     )
    #
    #     if row is None:
    #         return None
    #
    #     application = dict(row)
    #
    #     # Lay tai lieu da nop
    #     docs = await conn.fetch(
    #         """
    #         SELECT document_name,
    #                document_type,
    #                submitted_at,
    #                status,
    #                reviewer_note
    #         FROM   scholarship_application_documents   -- TODO: xac nhan ten bang
    #         WHERE  application_id = $1
    #         ORDER  BY submitted_at ASC NULLS LAST
    #         """,
    #         str(row["id"]),
    #     )
    #     application["submitted_documents"] = [dict(d) for d in docs]
    #     return application


# ──────────────────────────────────────────────────────────────────────────────
# Tool: Lay ho so hoc bong dang pending cua sinh vien hien tai
# ──────────────────────────────────────────────────────────────────────────────


@tool
async def get_current_scholarship_application(config: RunnableConfig) -> str:
    """
    Lay thong tin day du ho so xin hoc bong dang cho xet duyet (pending)
    cua sinh vien dang dang nhap. Moi sinh vien chi co the dang apply
    mot hoc bong tai mot thoi diem, nen khong can truyen ID.

    Tra ve:
    - Thong tin hoc bong dang apply (ten, don vi cap, trang thai)
    - Ho so sinh vien day du: hoc luc (GPA, DRL), hoan canh kinh te,
      hoan canh gia dinh, thanh tich noi bat
    - Danh gia so bo tu can bo xet duyet (co / khong du tieu chi, muc do hoan chinh)
    - Danh sach tai lieu da nop va tung tai lieu: trang thai (accepted / missing),
      ghi chu cua nguoi xet duyet, noi dung chi tiet (content_summary)

    Su dung tool nay khi sinh vien hoi ve: ti le thanh cong, trang thai ho so,
    tai lieu con thieu, nhan xet ve hoc luc / hoan canh, kha nang duoc duyet.
    """
    user_id = _uid(config)

    try:
        application = await _fetch_pending_application_from_db(user_id)
    except NotImplementedError:
        logger.warning("get_current_scholarship_application_using_mock", user_id=user_id)
        application = _MOCK_PENDING_APPLICATION
    except Exception as exc:
        logger.error("get_current_scholarship_application_failed", error=str(exc), user_id=user_id)
        return json.dumps(
            {"error": f"Loi truy van ho so hoc bong: {str(exc)}"},
            ensure_ascii=False,
        )

    if application is None:
        return json.dumps(
            {
                "user_id": user_id,
                "message": (
                    "Hien tai sinh vien khong co don xin hoc bong nao dang cho xet duyet. "
                    "Co the sinh vien chua nop don hoac don da duoc xu ly xong."
                ),
            },
            ensure_ascii=False,
        )

    # Tinh nhanh tong ket tai lieu
    docs: list[dict[str, Any]] = application.get("submitted_documents", [])
    doc_summary = {
        "total": len(docs),
        "accepted": sum(1 for d in docs if d.get("status") == "accepted"),
        "missing": sum(1 for d in docs if d.get("status") == "missing"),
        "pending": sum(1 for d in docs if d.get("status") == "pending"),
    }

    payload = {
        "user_id": user_id,
        "application": _serialize(application),
        "document_summary": doc_summary,
        "_data_source": "mock -- cho xac nhan schema DB thuc",
    }

    return json.dumps(payload, ensure_ascii=False)
