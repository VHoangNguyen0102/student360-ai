# -*- coding: utf-8 -*-
"""
Seed thêm dữ liệu realistics cho application ea120835 (under_review)
để AI agent có đủ ngữ cảnh phân tích tỉ lệ trúng tuyển:

Thay đổi:
1. scholarship_requirements: thêm requirement "GPA >= 3.0" (is_required=True)
                              và "Kinh nghiệm dự án" (is_required=True)
   (giữ "Bảng điểm" và "Thư giới thiệu" đã có)
2. scholarship_documents: thêm "Thu gioi thieu" (is_required=False)
3. student_scholarship_documents:
     - CV         -> status='approved',  reviewer_note='CV trình bày rõ ràng, đạt yêu cầu'
     - Bang diem  -> status='rejected',  reviewer_note='GPA 2.8 chưa đạt ngưỡng tối thiểu 3.0'
4. scholarship_reviews: thêm 2 vòng xét duyệt có comment
5. student_scholarships: cập nhật feedback + reviewer_id thực hơn
"""
import asyncio
import sys
import uuid
from datetime import datetime

import asyncpg

sys.stdout.reconfigure(encoding="utf-8")

DB_URL = "postgresql://neondb_owner:npg_i8CB9aURsPKV@ep-plain-sound-adaxrn02-pooler.c-2.us-east-1.aws.neon.tech/DDD?sslmode=require"

APP_ID  = "ea120835-cf69-44da-977c-1510de2e41be"
SCH_ID  = "a1305d3e-f286-4096-b6c1-c978433a907a"
USER_ID = "217ad15c-2071-45e3-bfa2-05bab5ef64cc"

# IDs tài liệu đã có
DOC_CV_REQUIRED_ID         = "d0ac559e-67a5-4a75-8c54-7f855d357961"  # CV (is_required=True)
DOC_BANGDIEM_REQUIRED_ID   = "1705ec64-942b-4839-8a3c-053a3be91ab8"  # Bang diem (is_required=True)

# IDs submitted docs đã có
SUBMITTED_CV_ID       = "7a4929a8-9964-458a-a6bf-a2648c5898bf"
SUBMITTED_BANGDIEM_ID = "e6d4a629-c866-496c-b855-e1dd768e7d92"

# Reviewer giả (dùng UUID cố định để nhất quán)
REVIEWER_ID = "aaaaaaaa-bbbb-cccc-dddd-000000000001"

# --- IDs mới sẽ seed ---
REQ_GPA_ID     = str(uuid.uuid4())
REQ_PROJECT_ID = str(uuid.uuid4())
DOC_THUGIOITHIEU_ID      = str(uuid.uuid4())
REVIEW_ROUND1_ID = str(uuid.uuid4())
REVIEW_ROUND2_ID = str(uuid.uuid4())

now = datetime.now()


async def main():
    conn = await asyncpg.connect(DB_URL)

    print("=" * 60)
    print("SEED: scholarship data for application ea120835")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. scholarship_requirements – thêm GPA + Kinh nghiệm dự án
    # ------------------------------------------------------------------
    print("\n[1] Thêm scholarship_requirements (GPA, Kinh nghiem du an)...")

    # Xem requirements hiện có
    existing_reqs = await conn.fetch(
        "SELECT title FROM scholarship_requirements WHERE scholarship_id = $1", SCH_ID
    )
    existing_titles = {r["title"] for r in existing_reqs}

    if "GPA >= 3.0" not in existing_titles:
        await conn.execute(
            """
            INSERT INTO scholarship_requirements
                (id, scholarship_id, title, description, is_required, sort_order, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            REQ_GPA_ID, SCH_ID,
            "GPA >= 3.0",
            "Sinh vien can dat diem trung binh tich luy tu 3.0/4.0 tro len trong hoc ky gan nhat",
            True,  # is_required
            1,
            now, now,
        )
        print(f"  + Added requirement: GPA >= 3.0 (id={REQ_GPA_ID})")
    else:
        print("  ~ GPA requirement already exists, skip")

    if "Kinh nghiem du an" not in existing_titles:
        await conn.execute(
            """
            INSERT INTO scholarship_requirements
                (id, scholarship_id, title, description, is_required, sort_order, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            REQ_PROJECT_ID, SCH_ID,
            "Kinh nghiem du an",
            "Co it nhat 1 du an thuc te hoac nghien cuu khoa hoc duoc ghi nhan",
            True,  # is_required
            3,
            now, now,
        )
        print(f"  + Added requirement: Kinh nghiem du an (id={REQ_PROJECT_ID})")
    else:
        print("  ~ Project requirement already exists, skip")

    # ------------------------------------------------------------------
    # 2. scholarship_documents – thêm Thu gioi thieu (not required)
    # ------------------------------------------------------------------
    print("\n[2] Thêm scholarship_documents (Thu gioi thieu, optional)...")

    existing_docs = await conn.fetch(
        "SELECT document_name FROM scholarship_documents WHERE scholarship_id = $1", SCH_ID
    )
    existing_doc_names = {r["document_name"] for r in existing_docs}

    if "Thu gioi thieu" not in existing_doc_names:
        await conn.execute(
            """
            INSERT INTO scholarship_documents
                (id, scholarship_id, document_name, document_type, is_required,
                 max_file_size_mb, sample_url, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            DOC_THUGIOITHIEU_ID, SCH_ID,
            "Thu gioi thieu",
            "pdf",
            False,   # is_required = False
            5,       # max_file_size_mb
            None,    # sample_url
            now, now,
        )
        print(f"  + Added doc: Thu gioi thieu (id={DOC_THUGIOITHIEU_ID})")
    else:
        print("  ~ Thu gioi thieu doc already exists, skip")

    # ------------------------------------------------------------------
    # 3. student_scholarship_documents – update CV approved, bảng điểm rejected
    # ------------------------------------------------------------------
    print("\n[3] Cập nhật submitted docs (CV=approved, Bang diem=rejected)...")

    await conn.execute(
        """
        UPDATE student_scholarship_documents
        SET status = $1, reviewer_note = $2, updated_at = $3
        WHERE id = $4
        """,
        "approved",
        "CV trinh bay ro rang, co kinh nghiem du an thuc te phu hop voi yeu cau hoc bong. Dat yeu cau.",
        now,
        SUBMITTED_CV_ID,
    )
    print(f"  * Updated CV (id={SUBMITTED_CV_ID}) -> approved")

    await conn.execute(
        """
        UPDATE student_scholarship_documents
        SET status = $1, reviewer_note = $2, updated_at = $3
        WHERE id = $4
        """,
        "rejected",
        "GPA hoc ky gan nhat la 2.85/4.0, chua dat nguong toi thieu 3.0. Sinh vien can cai thien ket qua hoc tap truoc khi nop lai.",
        now,
        SUBMITTED_BANGDIEM_ID,
    )
    print(f"  * Updated Bang diem (id={SUBMITTED_BANGDIEM_ID}) -> rejected")

    # ------------------------------------------------------------------
    # 4. scholarship_reviews – 2 vòng xét duyệt
    # ------------------------------------------------------------------
    print("\n[4] Thêm scholarship_reviews (2 rounds)...")

    existing_reviews = await conn.fetch(
        "SELECT id FROM scholarship_reviews WHERE student_scholarship_id = $1", APP_ID
    )
    if not existing_reviews:
        # Vòng 1: sơ tuyển hồ sơ — passed
        await conn.execute(
            """
            INSERT INTO scholarship_reviews
                (id, student_scholarship_id, reviewer_id, stage, status, comment, reviewed_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            REVIEW_ROUND1_ID, APP_ID, REVIEWER_ID,
            "eligibility_check",
            "approved",
            "Ho so nop day du tai lieu bat buoc. CV tot, co kinh nghiem du an. Chuyen sang vong xem xet tai lieu chi tiet.",
            datetime(2026, 4, 5, 9, 0, 0),
            datetime(2026, 4, 5, 9, 0, 0),
            datetime(2026, 4, 5, 9, 0, 0),
        )
        print(f"  + Added round 1 review (eligibility_check, approved): id={REVIEW_ROUND1_ID}")

        # Vòng 2: xét duyệt GPA — pending (đang chờ sinh viên giải trình)
        await conn.execute(
            """
            INSERT INTO scholarship_reviews
                (id, student_scholarship_id, reviewer_id, stage, status, comment, reviewed_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            REVIEW_ROUND2_ID, APP_ID, REVIEWER_ID,
            "document_review",
            "pending",
            "Bang diem hoc ky 1/2025 cho thay GPA 2.85, chua dat nguong 3.0. "
            "Hoi dong yeu cau sinh vien nop them bang diem bo sung hoc ky 2/2025 "
            "hoac thu giai trinh ly do GPA giam. Han chot: 30/04/2026.",
            None,  # reviewed_at = None (chua xet xong)
            datetime(2026, 4, 10, 14, 30, 0),
            datetime(2026, 4, 10, 14, 30, 0),
        )
        print(f"  + Added round 2 review (document_review, pending): id={REVIEW_ROUND2_ID}")
    else:
        print(f"  ~ Reviews already exist ({len(existing_reviews)} rows), skip")

    # ------------------------------------------------------------------
    # 5. student_scholarships – cập nhật feedback + reviewer_id
    # ------------------------------------------------------------------
    print("\n[5] Cập nhật feedback và reviewer_id trong student_scholarships...")

    await conn.execute(
        """
        UPDATE student_scholarships
        SET feedback = $1, reviewer_id = $2, updated_at = $3,
            note = $4
        WHERE id = $5
        """,
        "Ho so dang o vong xet duyet GPA. CV va kinh nghiem du an du dieu kien, "
        "nhung bang diem hien tai chua dat nguong GPA 3.0. "
        "Sinh vien can nop bo sung bang diem hoc ky 2/2025 truoc 30/04/2026.",
        REVIEWER_ID,
        now,
        "Sinh vien tu nhan xet: Em da hoan thanh 2 du an thuc te tai cong ty ABC. "
        "GPA hoc ky nay bi anh huong do gia dinh co viec rieng, em se co gang cai thien.",
        APP_ID,
    )
    print(f"  * Updated student_scholarships feedback + reviewer_id")

    # ------------------------------------------------------------------
    # Final check
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("VERIFY: trạng thái sau khi seed")
    print("=" * 60)

    req_count = await conn.fetchval(
        "SELECT COUNT(*) FROM scholarship_requirements WHERE scholarship_id = $1", SCH_ID
    )
    doc_count = await conn.fetchval(
        "SELECT COUNT(*) FROM scholarship_documents WHERE scholarship_id = $1", SCH_ID
    )
    submitted_count = await conn.fetchval(
        "SELECT COUNT(*) FROM student_scholarship_documents WHERE student_scholarship_id = $1", APP_ID
    )
    review_count = await conn.fetchval(
        "SELECT COUNT(*) FROM scholarship_reviews WHERE student_scholarship_id = $1", APP_ID
    )

    print(f"  scholarship_requirements : {req_count}")
    print(f"  scholarship_documents    : {doc_count}")
    print(f"  submitted docs           : {submitted_count}")
    print(f"  review rounds            : {review_count}")

    rows_docs = await conn.fetch(
        """
        SELECT ssd.status, ssd.reviewer_note, sd.document_name
        FROM student_scholarship_documents ssd
        JOIN scholarship_documents sd ON sd.id = ssd.document_id
        WHERE ssd.student_scholarship_id = $1
        """,
        APP_ID,
    )
    print("\n  Submitted docs detail:")
    for row in rows_docs:
        print(f"    [{row['status']}] {row['document_name']}: {str(row['reviewer_note'])[:60]}...")

    rows_rev = await conn.fetch(
        "SELECT stage, status, comment FROM scholarship_reviews WHERE student_scholarship_id = $1 ORDER BY created_at",
        APP_ID,
    )
    print("\n  Reviews detail:")
    for row in rows_rev:
        print(f"    [{row['stage']}] {row['status']}: {str(row['comment'])[:60]}...")

    await conn.close()
    print("\nDone! Seed completed successfully.")


asyncio.run(main())
