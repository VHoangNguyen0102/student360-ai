"""Core DB: quản lý asyncpg connection pool dùng chung toàn app.

Tại sao file này quan trọng (Pareto):
- Gần như mọi phần “có DB” đều phải đi qua pool này.
- Nếu DB down/sai URL/leak connection, lỗi thường quy về đây.

Thiết kế chính:
- Dùng **một pool toàn cục** (`_pool`) để tái sử dụng connection.
- **Lazy init**: chỉ tạo pool khi ai đó gọi `get_pool()` lần đầu.
    => lợi ích: test/unit có thể import app mà không cần DB thật (miễn là không
         chạm vào `get_pool()`).

Vòng đời:
- Pool được đóng ở shutdown qua `close_pool()`.
    Trong `app/main.py`, `lifespan()` gọi `close_pool()` sau `yield`.
"""
from __future__ import annotations

import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None


def _dsn() -> str:
    """Chuyển DATABASE_URL kiểu SQLAlchemy → DSN phù hợp cho asyncpg.

    Trong `.env.example` dự án dùng dạng:
        postgresql+asyncpg://user:pass@host:5432/dbname

    Nhưng `asyncpg.create_pool()` mong đợi dạng postgres thuần:
        postgresql://user:pass@host:5432/dbname

    Nên ta replace scheme ở đây.
    """
    return (
        settings.DATABASE_URL
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgres+asyncpg://", "postgresql://")
    )


async def get_pool() -> asyncpg.Pool:
    """Lấy (hoặc tạo) asyncpg pool singleton.

    Pattern: gọi `pool = await get_pool()` ở nơi cần query.
    - Lần đầu: tạo pool.
    - Các lần sau: dùng lại pool cũ.

    Tham số pool hiện tại:
    - min_size=2, max_size=10: giới hạn số connection.
    - command_timeout=30: timeout cho lệnh (giây).
    """
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            _dsn(),
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
    return _pool


async def close_pool() -> None:
    """Đóng pool khi app shutdown.

    Đây là hàm “cleanup” để:
    - đóng tất cả connection
    - set `_pool=None` để nếu app khởi động lại trong cùng process (hiếm) có thể tạo lại
    """
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
