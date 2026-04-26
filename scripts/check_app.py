# -*- coding: utf-8 -*-
"""Check current state of scholarship application ea120835 in the DB."""
import asyncio
import asyncpg
import sys
sys.stdout.reconfigure(encoding='utf-8')

APP_ID = "ea120835-cf69-44da-977c-1510de2e41be"
DB_URL = "postgresql://neondb_owner:npg_i8CB9aURsPKV@ep-plain-sound-adaxrn02-pooler.c-2.us-east-1.aws.neon.tech/DDD?sslmode=require"


async def main():
    conn = await asyncpg.connect(DB_URL)

    print("=== 1. APPLICATION ===")
    r = await conn.fetchrow("SELECT * FROM student_scholarships WHERE id = $1", APP_ID)
    if not r:
        print("  NOT FOUND"); await conn.close(); return
    for k, v in dict(r).items():
        print(f"  {k}: {v}")
    sch_id = str(r["scholarship_id"])

    print("\n=== 2. SCHOLARSHIP ===")
    r2 = await conn.fetchrow(
        "SELECT id, name, eligibility_criteria, provider, amount FROM scholarships WHERE id = $1",
        sch_id,
    )
    if r2:
        for k, v in dict(r2).items():
            print(f"  {k}: {v}")

    print("\n=== 3. REQUIREMENTS (scholarship_requirements) ===")
    rows = await conn.fetch(
        "SELECT id, title, description, is_required FROM scholarship_requirements WHERE scholarship_id = $1 ORDER BY sort_order",
        sch_id,
    )
    if rows:
        for row in rows:
            print(" ", dict(row))
    else:
        print("  (empty)")

    print("\n=== 4. REQUIRED DOCS (scholarship_documents) ===")
    rows = await conn.fetch(
        "SELECT id, document_name, document_type, is_required FROM scholarship_documents WHERE scholarship_id = $1",
        sch_id,
    )
    if rows:
        for row in rows:
            print(" ", dict(row))
    else:
        print("  (empty)")

    print("\n=== 5. SUBMITTED DOCS (student_scholarship_documents) ===")
    rows = await conn.fetch(
        "SELECT * FROM student_scholarship_documents WHERE student_scholarship_id = $1",
        APP_ID,
    )
    if rows:
        for row in rows:
            print(" ", dict(row))
    else:
        print("  (empty)")

    print("\n=== 6. REVIEWS (scholarship_reviews) ===")
    rows = await conn.fetch(
        "SELECT * FROM scholarship_reviews WHERE student_scholarship_id = $1",
        APP_ID,
    )
    if rows:
        for row in rows:
            print(" ", dict(row))
    else:
        print("  (empty)")

    await conn.close()


asyncio.run(main())
