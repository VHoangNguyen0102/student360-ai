"""Keyword lists for rule-based routing.

This file is intentionally dumb + transparent: easy to tweak without touching
router logic.
"""

from __future__ import annotations

FINANCE_KEYWORDS = [
    "6 lọ",
    "6 lo",
    "lọ",
    "jar",
    "chi tiêu",
    "chi tieu",
    "thu nhập",
    "thu nhap",
    "giao dịch",
    "giao dich",
    "ngân sách",
    "ngan sach",
    "vay",
    "khoản vay",
    "khoan vay",
    "tiết kiệm",
    "tiet kiem",
    "đầu tư",
    "dau tu",
    "lãi",
    "lai",
]

CAREER_KEYWORDS = [
    "cv",
    "resume",
    "phỏng vấn",
    "phong van",
    "ứng tuyển",
    "ung tuyen",
    "việc làm",
    "viec lam",
    "job",
    "intern",
    "thực tập",
    "thuc tap",
    "cover letter",
]

CONTENT_KEYWORDS = [
    "viết bài",
    "viet bai",
    "bài viết",
    "bai viet",
    "tag",
    "gắn thẻ",
    "gan the",
    "kiểm duyệt",
    "kiem duyet",
    "moderation",
    "nội dung",
    "noi dung",
]

PERSONALIZATION_KEYWORDS = [
    "feed",
    "gợi ý",
    "goi y",
    "đề xuất",
    "de xuat",
    "tóm tắt",
    "tom tat",
    "ưu tiên",
    "uu tien",
]
