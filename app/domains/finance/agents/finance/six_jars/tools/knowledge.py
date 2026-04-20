"""
Six Jars — Internal knowledge retrieval tool.
Allows the AI to fetch specific guidance on complex financial topics
without a Vector DB or external RAG system.
"""
from __future__ import annotations

import json
from typing import Literal

from langchain_core.tools import tool

# Finance topics supported by this tool
Topic = Literal[
    "debt_management",
    "irregular_income",
    "budget_reset",
    "savings_goals",
    "student_tips",
    "jar_ratios",
]


_GUIDELINES: dict[Topic, str] = {
    "debt_management": """\
GỢI Ý QUẢN LÝ NỢ (DEBT MANAGEMENT) VỚI 6 LỌ:

1. Phân loại nợ:
   - Nợ tiêu dùng (vay mượn tiền ăn, mua sắm): Trích từ lọ Essentials.
   - Nợ đầu tư (vay học phí, mua laptop học tập): Trích từ lọ Education.
   - Nợ khẩn cấp (viện phí, sửa xe): Trích từ lọ Reserve.

2. Chiến lược trả nợ:
   - "Tuyết lăn" (Snowball): Trả các khoản nợ nhỏ trước để tạo động lực.
   - Trích thêm 1-2% từ lọ Enjoyment sang Essentials nếu nợ đang quá tải.

3. Quy tắc vàng: Đừng vay thêm để trả nợ cũ. Luôn ưu tiên trả nợ có lãi suất cao nhất trước.
""",
    "irregular_income": """\
CHIẾN LƯỢC THU NHẬP KHÔNG ĐỀU (GRAB, PART-TIME, FREELANCE):

1. Mô hình "Lọ Chờ" (Holding Jar):
   - Khi có thu nhập hàng ngày, đừng chia ngay. Hãy gom hết tất cả tiền vào 1 tài khoản/phong bì gọi là "Lọ Chờ".
   - Cuối tuần hoặc cuối tháng mới thực hiện chia tổng số tiền đó vào 6 lọ theo tỷ lệ chuẩn.

2. Ưu tiên "Sống sót":
   - Nếu thu nhập thấp hơn mức mong đợi, hãy ưu tiên đổ đầy lọ Essentials đầu tiên để đảm bảo nhu cầu cơ bản.
   - Cắt giảm Enjoyment và Sharing về mức tối thiểu (1%).

3. Quản lý biến động: Dùng lọ Reserve để bù đắp cho những tháng thu nhập thấp.
""",
    "budget_reset": """\
CÁCH KHỞI ĐỘNG LẠI (BUDGET RESET) KHI VƯỢT LỌ:

1. Đừng tự trách: Việc tiêu quá tay là bình thường khi mới bắt đầu. Đừng cố gắng "nhịn ăn" để bù lại lọ đã âm, điều đó dễ dẫn đến bỏ cuộc.

2. Reset số dư: Chấp nhận số dư hiện tại là thực tế. Đừng cố gắng trả nợ "tưởng tượng" cho chính mình giữa các lọ.

3. Chia lại từ đầu: Áp dụng tỷ lệ chia đúng 6 lọ cho KHOẢN THU NHẬP TIẾP THEO bạn nhận được.

4. Điều chỉnh tỷ lệ: Nếu lọ Essentials liên tục bị âm, hãy cân nhắc tăng tỷ lệ Essentials lên 60% và giảm Enjoyment xuống 5% trong 1-2 tháng tới.
""",
    "savings_goals": """\
ĐẶT MỤC TIÊU TIẾT KIỆM (SAVINGS GOALS) TRONG 6 LỌ:

1. Xác định mục tiêu: Mua laptop, du ngoạn, đóng học phí kỳ tới...
2. Chọn lọ tương ứng:
   - Mua laptop/khóa học -> Lọ Education.
   - Đi du lịch -> Lọ Enjoyment.
   - Quỹ dự phòng/mục tiêu lớn -> Lọ Reserve hoặc Investment.

3. Công thức tích lũy:
   Số tiền mỗi tháng = (Tổng tiền mục tiêu - Số dư hiện tại) / Số tháng còn lại.

4. Theo dõi: Dùng mô tả giao dịch hoặc ghi chú trên Student360 để đánh dấu khoản tiền tiết kiệm cho mục tiêu đó.
""",
    "student_tips": """\
MẸO TÀI CHÍNH ĐẶC THÙ CHO SINH VIÊN VIỆT NAM:

1. Ăn uống: Tự nấu ăn giúp tiết kiệm lọ Essentials đáng kể (~30-50%) so với ăn ngoài.
2. Di chuyển: Tận dụng xe buýt và các gói ưu đãi Grab/Be dành cho sinh viên.
3. Học tập: Mượn sách thư viện, mua sách cũ hoặc dùng tài liệu số để tiết kiệm lọ Education.
4. Tận dụng ưu đãi: Luôn mang theo thẻ sinh viên để được giảm giá tại rạp phim, bảo tàng, cửa hàng sách.
5. Kiếm thêm: Tìm các công việc part-time liên quan đến ngành học để vừa tăng thu nhập vừa làm giàu CV.
""",
    "jar_ratios": """\
GIẢI THÍCH CHI TIẾT TỶ LỆ 6 LỌ VÀ CÁCH ĐIỀU CHỈNH:

- Tỷ lệ chuẩn (T. Harv Eker): Essentials 55% | Education 10% | Enjoyment 10% | Investment 10% | Reserve 10% | Sharing 5%.

- Điều chỉnh cho sinh viên (Linh hoạt):
  - Essentials: 50% - 70% (tùy vào tiền thuê nhà).
  - Tiết kiệm: Khi mới bắt đầu, dù chỉ 1% cho Investment cũng cực kỳ quan trọng để hình thành thói quen.
  - Hưởng thụ: Đừng cắt bỏ 100% Enjoyment, bạn sẽ bị "burnout". Hãy giữ ít nhất 5%.

Quy tắc: Dù bạn điều chỉnh thế nào, TỔNG CỘNG luôn phải là 100%.
""",
}


@tool
def get_financial_guidelines(topic: Topic) -> str:
    """
    Get detailed internal guidelines and advice for a specific financial topic.
    Useful for questions about debt, irregular income, budget resets, and savings goals.

    Args:
        topic: The topic to get guidance on.
               One of: 'debt_management', 'irregular_income', 'budget_reset',
               'savings_goals', 'student_tips', 'jar_ratios'.
    """
    guideline = _GUIDELINES.get(topic)
    if not guideline:
        return json.dumps({
            "error": f"Topic '{topic}' not found.",
            "available_topics": list(_GUIDELINES.keys())
        })

    return guideline
