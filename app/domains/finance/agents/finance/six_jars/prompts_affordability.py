"""
Affordability Check — LLM Prompts (Six Jars domain)
"""

from app.core.prompts.chat_voice import get_global_chat_style_rules


def get_affordability_check_prompt(
    description: str,
    amount: float,
    jar_code: str,
    jar_name: str,
    current_balance: float,
    monthly_balance: float,
    recent_avg_monthly_expense: float,
    recent_transactions: str,
    user_context: str = "",
) -> tuple[str, str]:
    """
    Returns (system_prompt, user_message) for affordability evaluation.

    Args:
        description: Item the user wants to buy
        amount: Cost in VND
        jar_code: Jar category (essentials, enjoyment, etc.)
        jar_name: Display name of jar (e.g., "Essentials")
        current_balance: Current balance of that jar
        monthly_balance: Expected monthly income allocated to this jar
        recent_avg_monthly_expense: Average spending in this jar recently
        recent_transactions: Formatted recent transactions in this jar
        user_context: Additional context from user (optional)
    """

    system_prompt = f"""\
Bạn là một trợ lý tài chính thông minh giúp sinh viên đưa ra quyết định mua sắm cơ sở trên dữ liệu tài chính thực tế.

Mục đích: Giúp sinh viên tránh chi tiêu bừa bãi mà vẫn cho phép chi tiêu hợp lý.

Khi đánh giá:
1. Cân nhắc số dư hiện tại vs chi phí
2. Kiểm tra xu hạng chi tiêu gần đây
3. Ưu tiên các nhu cầu thiết yếu
4. Lưu ý đến các khoản chi định kỳ sắp tới
5. Xem xét cho phép chi tiêu vui vẻ trong giới hạn hợp lý

Trả về JSON thuần túy (không markdown):
{{
  "recommendation": "yes" | "no" | "wait",
  "reason": "1–2 câu tiếng Việt, thân thiện, không dài dòng (đồng nhất giọng chat bên dưới)"
}}

Nguyên tắc:
- "yes": Số dư đủ + không ảnh hưởng kế hoạch tài chính
- "no": Nghèo đi hoặc sẽ làm mất cân bằng lọ
- "wait": Có thể mua nhưng tốt hơn là tiết kiệm trước / chờ lương tháng sau

---
{get_global_chat_style_rules()}
"""

    user_message = f"""\
Sinh viên muốn mua: {description}
Chi phí: {amount:,.0f} VND
Lọ chi tiêu: {jar_name} ({jar_code})

TÌNH HÌNH TÀI CHÍNH HIỆN TẠI:
- Số dư hiện tại lọ {jar_name}: {current_balance:,.0f} VND
- Thu nhập dự kiến/tháng (lọ này): {monthly_balance:,.0f} VND
- Chi tiêu trung bình/tháng (lọ này): {recent_avg_monthly_expense:,.0f} VND

CÁC GIAO DỊCH GẦN ĐÂY TRONG LỌ NÀY:
{recent_transactions}

NGỮ CẢNH THÊM:
{user_context if user_context else "(Không có thêm thông tin)"}

DỰA VÀO THÔNG TIN TRÊN, SINH VIÊN CÓ NÊN MUA SẢN PHẨM NÀY KHÔNG?
Trả về JSON với đề xuất (yes / no / wait) và lý do ngắn gọn.
"""

    return system_prompt, user_message
