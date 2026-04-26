# -*- coding: utf-8 -*-
import asyncio, sys, asyncpg
sys.stdout.reconfigure(encoding='utf-8')

DB_URL = "postgresql://neondb_owner:npg_i8CB9aURsPKV@ep-plain-sound-adaxrn02-pooler.c-2.us-east-1.aws.neon.tech/DDD?sslmode=require"

async def main():
    conn = await asyncpg.connect(DB_URL)
    
    print("=== All ENUMs in DB ===")
    rows = await conn.fetch(
        "SELECT t.typname, e.enumlabel FROM pg_enum e "
        "JOIN pg_type t ON t.oid = e.enumtypid "
        "ORDER BY t.typname, e.enumsortorder"
    )
    current_type = None
    for r in rows:
        if r['typname'] != current_type:
            current_type = r['typname']
            print(f"\n  [{current_type}]")
        print(f"    - {r['enumlabel']}")
    
    await conn.close()

asyncio.run(main())
