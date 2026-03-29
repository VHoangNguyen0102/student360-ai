from langchain_core.messages import AIMessage, ToolMessage

from app.api.finance.chat import _synthesise_reply_from_tools


def test_synthesise_reply_from_get_jar_statistics_tool_output():
    tool_json = (
        "Record 1:\n"
        "{"
        '"jar_code":"ENJOYMENT",'
        '"name":"ENJOYMENT",'
        '"accumulated_income":1000000,'
        '"accumulated_expense":250000,'
        '"net_flow":750000,'
        '"current_balance":500000'
        "}"
    )

    messages = [
        AIMessage(content="", tool_calls=[{"id": "tc1", "name": "get_jar_statistics", "args": {}}]),
        ToolMessage(content=tool_json, tool_call_id="tc1"),
        AIMessage(content=""),
    ]

    reply = _synthesise_reply_from_tools(messages)
    assert reply is not None
    assert "Tổng thu" in reply
    assert "1.000.000 VND" in reply
    assert "250.000 VND" in reply
    assert "750.000 VND" in reply
