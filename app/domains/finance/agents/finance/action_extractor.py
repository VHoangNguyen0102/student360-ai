"""ActionExtractor — extract executable action proposals from AI reply context.

Runs a lightweight LLM call (temperature=0) after the main streaming response
to identify at most 2 actions that could be executed immediately (one-tap).
Returns an empty list on any error so the main response is never blocked.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import date

import structlog

from app.core.llm.factory import get_chat_model
from app.domains.finance.models.action_proposal import ActionProposal, ActionType

logger = structlog.get_logger()

_EXTRACT_TIMEOUT_S = 5.0

_SYSTEM_PROMPT = """\
Bạn là trợ lý phân tích tài chính. Nhiệm vụ của bạn là đọc tin nhắn người dùng và câu trả lời của AI, \
rồi xác định xem có hành động tài chính nào có thể thực thi ngay không.

Ngày hôm nay: {today}

Các loại hành động được hỗ trợ:
- CREATE_TRANSACTION: Ghi nhận một khoản thu hoặc chi vào lọ cụ thể
- DISTRIBUTE_INCOME: Phân bổ thu nhập vào các lọ theo tỷ lệ 6 lọ
- TRANSFER_BETWEEN_JARS: Chuyển tiền từ lọ này sang lọ khác
- UPDATE_ALLOCATION: Điều chỉnh tỷ lệ % phân bổ của các lọ
- CREATE_AUTO_TRANSFER_SCHEDULE: Tạo lịch tự động chuyển/tiết kiệm định kỳ
- DELETE_AUTO_TRANSFER_SCHEDULE: Xóa một lịch tự động theo tên
- TOGGLE_AUTO_TRANSFER_SCHEDULE: Tạm dừng hoặc bật lại một lịch tự động (không xóa)
- UPDATE_AUTO_TRANSFER_SCHEDULE: Sửa thông tin lịch tự động (số tiền, tần suất, ngày...)
- DELETE_TRANSACTION: Xóa một giao dịch đã ghi nhận

Quy tắc nhận dạng:
- "vừa chi / mua / ăn / uống / thanh toán + số tiền" → CREATE_TRANSACTION (type=EXPENSE)
- "nhận lương / nhận tiền / có thu nhập + số tiền" → DISTRIBUTE_INCOME
- "chuyển từ lọ X sang lọ Y + số tiền" → TRANSFER_BETWEEN_JARS
- "tăng/giảm/điều chỉnh tỷ lệ lọ X lên/xuống N%" → UPDATE_ALLOCATION
- "mỗi tháng/tuần/ngày + chuyển/tiết kiệm/để dành + số tiền (+ vào lọ X)" → CREATE_AUTO_TRANSFER_SCHEDULE
  (KHÔNG đề xuất nếu không rõ tần suất hoặc số tiền)
- "xóa/hủy lịch [tên lịch]" → DELETE_AUTO_TRANSFER_SCHEDULE (params: scheduleName)
- "tạm dừng/dừng/bật lại/kích hoạt lịch [tên lịch]" → TOGGLE_AUTO_TRANSFER_SCHEDULE (params: scheduleName)
- "sửa/đổi/cập nhật lịch [tên lịch] + thay đổi" → UPDATE_AUTO_TRANSFER_SCHEDULE (params: scheduleName + trường cần sửa)
- "xóa giao dịch [mô tả]" → DELETE_TRANSACTION (params: transactionId nếu có trong context)

Mã lọ chuẩn (dùng trong params.jarCode hoặc params.sourceJarCode/targetJarCode):
- essentials (Thiết yếu/Chi tiêu hàng ngày, ~55%)
- enjoyment (Hưởng thụ/Giải trí, ~10%)
- education (Giáo dục/Học tập, ~10%)
- reserve (Tiết kiệm dự phòng, ~10%)
- investment (Đầu tư, ~10%)
- sharing (Cho đi/Từ thiện, ~5%)

Trả về JSON với format:
{{"actions": [
    {{
      "type": "CREATE_TRANSACTION",
      "title": "Ghi chi tiêu cà phê",
      "description": "Chi 45.000đ • Lọ Thiết yếu • Hôm nay",
      "params": {{
        "type": "EXPENSE",
        "amount": 45000,
        "description": "Cà phê",
        "jarCode": "essentials",
        "transactionDate": "2026-05-05"
      }},
      "risk_level": "low"
    }},
    {{
      "type": "DISTRIBUTE_INCOME",
      "title": "Phân bổ thu nhập",
      "description": "Phân bổ 10.000.000 VND vào 6 lọ",
      "params": {{
        "amount": 10000000,
        "description": "Thu nhập tháng 5",
        "transactionDate": "2026-05-05"
      }},
      "risk_level": "low"
    }},
    {{
      "type": "CREATE_AUTO_TRANSFER_SCHEDULE",
      "title": "Tạo lịch tiết kiệm hàng tháng",
      "description": "500.000đ/tháng • vào ngày 1 • Lọ Tiết kiệm",
      "params": {{
        "name": "Tiết kiệm tháng",
        "amount": 500000,
        "frequency": "MONTHLY",
        "allocationType": "SINGLE_JAR",
        "targetJarCode": "reserve",
        "dayOfMonth": 1
      }},
      "risk_level": "medium"
    }},
    {{
      "type": "DELETE_AUTO_TRANSFER_SCHEDULE",
      "title": "Xóa lịch tiết kiệm tháng",
      "description": "Xóa vĩnh viễn lịch tự động",
      "params": {{"scheduleName": "Tiết kiệm tháng"}},
      "risk_level": "high"
    }},
    {{
      "type": "TOGGLE_AUTO_TRANSFER_SCHEDULE",
      "title": "Tạm dừng lịch tiết kiệm tháng",
      "description": "Tạm dừng không xóa, có thể bật lại",
      "params": {{"scheduleName": "Tiết kiệm tháng"}},
      "risk_level": "low"
    }},
    {{
      "type": "UPDATE_AUTO_TRANSFER_SCHEDULE",
      "title": "Sửa lịch tiết kiệm tháng",
      "description": "Đổi số tiền thành 800.000đ/tháng",
      "params": {{"scheduleName": "Tiết kiệm tháng", "amount": 800000}},
      "risk_level": "medium"
    }},
    {{
      "type": "DELETE_TRANSACTION",
      "title": "Xóa giao dịch cà phê",
      "description": "Chi 45.000đ • Lọ Hưởng thụ",
      "params": {{"transactionId": "uuid-from-context"}},
      "risk_level": "high"
    }}
  ]
}}

Quy tắc quan trọng:
- Chỉ đề xuất hành động nếu có đủ thông tin (số tiền, loại giao dịch)
- Tối đa 10 đề xuất, ưu tiên hành động rõ ràng nhất
- Nếu không có hành động nào phù hợp, trả về {{"actions": []}}
- Không bao giờ đề xuất khi không chắc chắn về số tiền
- Định dạng số tiền là số nguyên VND (ví dụ: 45000, không phải "45k" hay "45,000đ")
- transactionDate phải là định dạng YYYY-MM-DD
- LUÔN LUÔN dùng key "transactionDate" cho ngày thực hiện.
"""

_USER_PROMPT = """\
Tin nhắn người dùng: {user_message}

Câu trả lời của AI: {ai_reply}

Hãy xác định các hành động có thể thực thi và trả về JSON.
"""


class ActionExtractor:
    async def extract(
        self,
        user_message: str,
        ai_reply: str,
        user_id: str,
    ) -> list[ActionProposal]:
        start = time.monotonic()
        try:
            proposals = await asyncio.wait_for(
                self._run_extraction(user_message, ai_reply),
                timeout=_EXTRACT_TIMEOUT_S,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "action_extractor_done",
                user_id=user_id,
                proposals_count=len(proposals),
                latency_ms=latency_ms,
            )
            return proposals
        except asyncio.TimeoutError:
            logger.warning(
                "action_extractor_timeout",
                user_id=user_id,
                timeout_s=_EXTRACT_TIMEOUT_S,
            )
            return []
        except Exception as exc:
            logger.error(
                "action_extractor_error",
                user_id=user_id,
                error=str(exc),
            )
            return []

    async def _run_extraction(
        self,
        user_message: str,
        ai_reply: str,
    ) -> list[ActionProposal]:
        llm = get_chat_model(temperature=0)
        today = date.today().isoformat()

        system = _SYSTEM_PROMPT.format(today=today)
        user = _USER_PROMPT.format(
            user_message=user_message[:500],
            ai_reply=ai_reply[:800],
        )

        from langchain_core.messages import HumanMessage, SystemMessage

        response = await llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=user),
        ])

        raw = response.content
        if isinstance(raw, list):
            raw = " ".join(str(b.get("text", "")) for b in raw if isinstance(b, dict))
        raw = str(raw).strip()
        
        logger.debug("action_extractor_raw", raw=raw)

        import re
        json_match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
        if json_match:
            raw = json_match.group(0)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("action_extractor_json_error", error=str(e), raw=raw)
            return []

        # Handle both {"actions": [...]} and [...] formats
        if isinstance(data, dict):
            actions_raw = data.get("actions") or data.get("proposals") or []
        elif isinstance(data, list):
            actions_raw = data
        else:
            actions_raw = []

        actions: list[ActionProposal] = []
        if not isinstance(actions_raw, list):
            return []

        for item in actions_raw[:10]:
            if not isinstance(item, dict):
                continue
            try:
                atype_str = str(item.get("type", "")).upper()
                if not atype_str:
                    continue

                params = item.get("params", {})
                # Normalize keys to camelCase for Backend DTOs
                normalized_params = {}
                for k, v in params.items():
                    if k == "jar_code": normalized_params["jarCode"] = v
                    elif k == "transaction_date": normalized_params["transactionDate"] = v
                    elif k == "distribution_date": normalized_params["transactionDate"] = v
                    elif k == "distributionDate": normalized_params["transactionDate"] = v
                    else: normalized_params[k] = v
                
                # Default to today if missing date
                if "transactionDate" not in normalized_params:
                    normalized_params["transactionDate"] = today
                
                # Standardize jar codes (e.g. sharing vs share)
                if "jarCode" in normalized_params:
                    jc = str(normalized_params["jarCode"]).lower()
                    if jc in ["share", "charity"]: normalized_params["jarCode"] = "sharing"
                    if jc in ["saving", "savings"]: normalized_params["jarCode"] = "reserve"
                    if jc in ["invest", "investment"]: normalized_params["jarCode"] = "investment"
                    if jc in ["learn", "learning", "edu"]: normalized_params["jarCode"] = "education"
                    if jc in ["play", "entertainment"]: normalized_params["jarCode"] = "enjoyment"
                    if jc in ["bill", "living", "necessity"]: normalized_params["jarCode"] = "essentials"
                
                actions.append(ActionProposal(
                    type=ActionType(atype_str),
                    title=item.get("title", "Hành động đề xuất"),
                    description=item.get("description", ""),
                    params=normalized_params,
                    risk_level=item.get("risk_level", "low"),
                ))
            except Exception as e:
                logger.warning("action_extractor_item_skip", error=str(e), item=item)
                continue

        return actions
