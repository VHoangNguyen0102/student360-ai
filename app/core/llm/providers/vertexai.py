from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Optional

import json
import uuid
import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import ConfigDict

from app.config import settings


def _extract_json_objects(buffer: str) -> tuple[list[dict], str]:
    """Pull complete JSON objects out of a streaming JSON-array buffer."""
    objects: list[dict] = []
    i = 0
    while i < len(buffer):
        start = buffer.find("{", i)
        if start == -1:
            break
        depth = 0
        in_string = False
        escape = False
        end = -1
        for j in range(start, len(buffer)):
            c = buffer[j]
            if escape:
                escape = False
                continue
            if c == "\\" and in_string:
                escape = True
                continue
            if c == '"':
                in_string = not in_string
            if not in_string:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = j
                        break
        if end == -1:
            break
        try:
            objects.append(json.loads(buffer[start : end + 1]))
        except json.JSONDecodeError:
            pass
        i = end + 1
    return objects, buffer[i:]


class VertexRestChatModel(BaseChatModel):
    """Vertex REST chat model using streamGenerateContent + API key.

    This follows the exact endpoint style:
    /v1/publishers/google/models/{model}:streamGenerateContent?key=...
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    model_name: str
    api_key: str
    temperature: float = 0.1
    timeout_s: float = 60.0

    @property
    def _llm_type(self) -> str:
        return "vertex-rest-stream"

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:
        """Bind tools to the model by storing them for payload building."""
        from langchain_core.runnables import RunnableBinding
        return RunnableBinding(bound=self, kwargs={"tools": tools, **kwargs})

    def _to_vertex_role(self, msg: BaseMessage) -> str:
        if isinstance(msg, AIMessage) or msg.type == "ai":
            return "model"
        if isinstance(msg, (ToolMessage, SystemMessage)) or msg.type in ("tool", "system"):
            return "user"
        return "user"

    def _to_vertex_text(self, msg: BaseMessage) -> str:
        if isinstance(msg, SystemMessage):
            return f"[System]\n{msg.content}"
        if isinstance(msg, HumanMessage):
            return str(msg.content)
        return str(msg.content)

    def _url(self) -> str:
        # Use explicit host override if provided, else derive from location.
        location = settings.VERTEX_AI_LOCATION
        base_url = (settings.VERTEX_AI_ENDPOINT_HOST or "").strip() or "aiplatform.googleapis.com"
        if not (settings.VERTEX_AI_ENDPOINT_HOST or "").strip() and location and location != "global":
            base_url = f"{location}-aiplatform.googleapis.com"

        return (
            f"https://{base_url}/v1/projects/{settings.VERTEX_AI_PROJECT}/locations/{location}/publishers/google/models/"
            f"{self.model_name}:streamGenerateContent?key={self.api_key}"
        )

    def _build_payload(self, messages: list[BaseMessage], **kwargs: Any) -> dict[str, Any]:
        contents: list[dict[str, Any]] = []
        for msg in messages:
            parts: list[dict[str, Any]] = []
            
            # Handle tool call results (ToolMessage)
            if msg.type == "tool":
                try:
                    content_json = json.loads(msg.content)
                except Exception:
                    content_json = {"result": msg.content}
                tool_name = getattr(msg, "name", None) or "unknown_tool"
                parts.append({
                    "functionResponse": {
                        "name": tool_name,
                        "response": content_json
                    }
                })
            # Handle AI messages (with possible tool calls)
            elif msg.type == "ai":
                if msg.content:
                    parts.append({"text": msg.content})
                tcalls = getattr(msg, "tool_calls", [])
                for tc in tcalls:
                    parts.append({
                        "functionCall": {
                            "name": tc["name"],
                            "args": tc["args"]
                        }
                    })
            # Handle normal text messages (Human/System)
            else:
                text = self._to_vertex_text(msg).strip()
                if text:
                    parts.append({"text": text})

            if parts:
                contents.append({
                    "role": self._to_vertex_role(msg),
                    "parts": parts,
                })
        
        payload: dict[str, Any] = {"contents": contents}
        
        # Add tools if bound
        tools = kwargs.get("tools")
        if tools:
            payload["tools"] = [{"function_declarations": [
                t if isinstance(t, dict) else {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.args_schema.schema() if hasattr(t, "args_schema") and t.args_schema else {"type": "object", "properties": {}}
                } for t in tools
            ]}]

        temp = kwargs.get("temperature", self.temperature)
        payload["generationConfig"] = {"temperature": float(temp)}
        return payload

    def _extract_ai_message(self, chunks: list[dict[str, Any]]) -> AIMessage:
        full_text = ""
        tool_calls = []
        
        for chunk in chunks:
            for candidate in chunk.get("candidates", []) or []:
                content = candidate.get("content", {}) or {}
                for part in content.get("parts", []) or []:
                    if "text" in part:
                        full_text += part["text"]
                    if "functionCall" in part:
                        fc = part["functionCall"]
                        tool_calls.append({
                            "name": fc["name"],
                            "args": fc["args"],
                            "id": f"call_{uuid.uuid4().hex[:12]}"
                        })
        
        return AIMessage(content=full_text.strip(), tool_calls=tool_calls)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        _ = stop, run_manager
        payload = self._build_payload(messages, **kwargs)
        with httpx.Client(timeout=self.timeout_s) as client:
            res = client.post(self._url(), json=payload)
        if res.status_code >= 400:
            raise RuntimeError(
                f"Vertex REST error {res.status_code}: {res.text}"
            )
        chunks = res.json()
        if not isinstance(chunks, list):
            raise RuntimeError(f"Unexpected Vertex response: {chunks}")
        
        import uuid
        msg = self._extract_ai_message(chunks)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        _ = stop, run_manager
        payload = self._build_payload(messages, **kwargs)
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            res = await client.post(self._url(), json=payload)
        if res.status_code >= 400:
            raise RuntimeError(
                f"Vertex REST error {res.status_code}: {res.text}"
            )
        chunks = res.json()
        if not isinstance(chunks, list):
            raise RuntimeError(f"Unexpected Vertex response: {chunks}")

        import uuid
        msg = self._extract_ai_message(chunks)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _astream(  # type: ignore[override]
        self,
        messages: list[BaseMessage],
        _stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        # Strip tools — tool calls cannot be streamed; use _agenerate for tool-calling turns.
        stream_kwargs = {k: v for k, v in kwargs.items() if k != "tools"}
        payload = self._build_payload(messages, **stream_kwargs)
        buffer = ""
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            async with client.stream("POST", self._url(), json=payload) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise RuntimeError(
                        f"Vertex REST stream error {response.status_code}: {body.decode()}"
                    )
                async for text_chunk in response.aiter_text():
                    buffer += text_chunk
                    objs, buffer = _extract_json_objects(buffer)
                    for obj in objs:
                        for candidate in obj.get("candidates", []) or []:
                            content = candidate.get("content", {}) or {}
                            for part in content.get("parts", []) or []:
                                text = part.get("text", "")
                                if text:
                                    chunk = ChatGenerationChunk(
                                        message=AIMessageChunk(content=text)
                                    )
                                    if run_manager:
                                        await run_manager.on_llm_new_token(text)
                                    yield chunk


def build_vertexai_chat_model(model: str | None = None, temperature: float = 0.1) -> BaseChatModel:
    vertex_api_key = (settings.VERTEX_API_KEY or "").strip()
    model_name = model or settings.VERTEX_LLM_MODEL
    if not vertex_api_key:
        raise ValueError("VERTEX_API_KEY is required when LLM_PROVIDER=vertexai")
    return VertexRestChatModel(
        model_name=model_name,
        api_key=vertex_api_key,
        temperature=temperature,
    )
