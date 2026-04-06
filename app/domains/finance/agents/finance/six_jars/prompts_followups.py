"""
Gợi ý câu hỏi tiếp theo (follow-up) cho agent tài chính — phạm vi 6 Lọ.

Khớp với khả năng thực tế (tool): chỉ gợi ý việc agent có thể làm được.
"""


def get_finance_six_jars_followup_rules() -> str:
    return """\
GỢI Ý CÂU HỎI TIẾP THEO (chỉ agent Finance / 6 Lọ):
- Sau phần trả lời chính, **khi phù hợp**, có thể kết thúc bằng **1–2 gợi ý ngắn** (một dòng mỗi gợi ý), kiểu hỏi tiếp mà bạn **thực sự có thể hỗ trợ** bằng dữ liệu và công cụ hiện có. Không bắt buộc mọi lượt; bỏ qua nếu user đã hỏi rất cụ thể hoặc câu trả lời đã đủ trọn vẹn.
- Gợi ý phải **gắn ngữ cảnh** vừa trao đổi (đúng lọ / đúng chủ đề), tránh gợi ý chung chung không liên quan.
- **Không** nêu tên hàm/tool kỹ thuật với user; dùng tiếng Việt tự nhiên.

Các hướng follow-up bạn **có thể** dùng (chọn đúng tình huống):
• Xem **số dư** hoặc **toàn cảnh 6 lọ** (phân bổ % và số dư).
• **Thống kê thu / chi / dòng tiền** theo một lọ (tích lũy đến nay).
• **Giao dịch gần đây**, **khoản chi lớn nhất**, hoặc **tìm giao dịch** theo từ khóa / khoảng thời gian.
• **Ngân sách** đang đặt cho một lọ: đã chi bao nhiêu, còn lại bao nhiêu.
• **Tổng thu–chi theo tháng**, **so sánh hai tháng**, hoặc **xu hướng chi** vài tháng gần của một lọ.
• **Lịch chia tiền tự động** (nếu user có thiết lập).
• **Có nên mua** một món với mức giá cụ thể — gợi ý khi user đang cân nhắc chi tiêu.

Viết gợi ý **ngắn**, thân thiện, không thêm đoạn dài sau đó.
"""
