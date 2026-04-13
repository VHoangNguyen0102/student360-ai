"""Gemini chat model with transparent API key rotation on quota exhaustion."""

from __future__ import annotations

import threading
from typing import Any, Optional

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import ConfigDict, PrivateAttr

from app.config import settings

_QUOTA_SIGNALS = ("RESOURCE_EXHAUSTED", "429", "quota exhausted")


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc)
    return any(sig in msg for sig in _QUOTA_SIGNALS)


class GeminiKeyPool:
    """Thread-safe round-robin pool of Gemini API keys."""

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise ValueError("GeminiKeyPool requires at least one API key.")
        self._keys = list(keys)
        self._lock = threading.Lock()
        self._idx = 0

    def size(self) -> int:
        return len(self._keys)

    def all_keys(self) -> list[str]:
        return list(self._keys)

    def rotate(self) -> None:
        """Advance index to the next key (called on quota error)."""
        with self._lock:
            self._idx = (self._idx + 1) % len(self._keys)

    def indices_from_current(self) -> list[int]:
        """Return all key indices starting from the current one (wraps around)."""
        with self._lock:
            start = self._idx
        n = len(self._keys)
        return [(start + i) % n for i in range(n)]


class RotatingGeminiChatModel(BaseChatModel):
    """
    Wraps multiple ChatGoogleGenerativeAI instances (one per API key).

    On every LLM call it tries the current key first.
    If a RESOURCE_EXHAUSTED / 429 quota error occurs, it rotates to the next
    key and retries — transparently, without the caller knowing.
    After exhausting all keys the last quota error is re-raised.

    Works with a single key too (no rotation needed, no overhead).
    Supports `bind_tools` via delegation to the primary inner model so that
    Gemini-specific tool formatting is preserved.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Public Pydantic fields (needed for BaseChatModel serialisation)
    gemini_model_name: str
    inner_temperature: float = 0.1

    # Private — not serialised, set in __init__
    _pool: GeminiKeyPool = PrivateAttr(default=None)
    _models: list = PrivateAttr(default_factory=list)  # list[ChatGoogleGenerativeAI]

    def __init__(
        self,
        *,
        pool: GeminiKeyPool,
        gemini_model_name: str,
        temperature: float = 0.1,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            gemini_model_name=gemini_model_name,
            inner_temperature=temperature,
            **kwargs,
        )
        self._pool = pool
        self._models = [
            ChatGoogleGenerativeAI(
                model=gemini_model_name,
                google_api_key=key,
                temperature=temperature,
            )
            for key in pool.all_keys()
        ]

    @property
    def _llm_type(self) -> str:
        return "rotating-gemini"

    def _models_from_current(self) -> list[ChatGoogleGenerativeAI]:
        return [self._models[i] for i in self._pool.indices_from_current()]

    # ------------------------------------------------------------------
    # Core generation — sync
    # ------------------------------------------------------------------

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_exc: Exception | None = None
        for model in self._models_from_current():
            try:
                return model._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as exc:
                if _is_quota_error(exc):
                    self._pool.rotate()
                    last_exc = exc
                    continue
                raise
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Core generation — async (primary path used by the agents)
    # ------------------------------------------------------------------

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_exc: Exception | None = None
        for model in self._models_from_current():
            try:
                return await model._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as exc:
                if _is_quota_error(exc):
                    self._pool.rotate()
                    last_exc = exc
                    continue
                raise
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Tool binding — delegate to primary model for correct Gemini formatting
    # ------------------------------------------------------------------

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        """
        Use the primary inner model's bind_tools so tools are formatted in
        Gemini's native format, then re-bind the formatted kwargs onto self
        so our rotation logic still applies during the actual invocation.
        """
        primary = self._models[0]
        primary_bound = primary.bind_tools(tools, **kwargs)
        # RunnableBinding stores the resolved kwargs; apply them to self
        return self.bind(**primary_bound.kwargs)


def build_gemini_chat_model(
    model: str | None = None,
    temperature: float = 0.1,
) -> RotatingGeminiChatModel:
    keys = settings.GEMINI_API_KEYS
    if not keys:
        raise ValueError(
            "GEMINI_API_KEY is required when LLM_PROVIDER=gemini. "
            "Set it as a single key or comma-separated list: key1,key2,..."
        )
    pool = GeminiKeyPool(keys)
    return RotatingGeminiChatModel(
        pool=pool,
        gemini_model_name=model or settings.GEMINI_LLM_MODEL,
        temperature=temperature,
    )
