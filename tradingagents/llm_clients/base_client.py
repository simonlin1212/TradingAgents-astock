from abc import ABC, abstractmethod
from typing import Any, Optional
import logging
import warnings

logger = logging.getLogger(__name__)

# 各 provider 表示"因为撞到输出上限才停下"的字段值（一律小写后比较）。
# ⚠️ 每家形状都不一样，少一种就等于那家的用户完全收不到告警：
#   · Anthropic          → stop_reason="max_tokens"
#   · OpenAI 兼容(Chat)   → finish_reason="length"
#   · Gemini             → finish_reason="MAX_TOKENS"
#   · OpenAI Responses   → status="incomplete" + incomplete_details.reason="max_output_tokens"
#     （**这条最要命**：`openai` 是默认 provider 且走 Responses API，漏掉它等于
#      默认配置下这个告警根本不会响）
_TRUNCATION_MARKERS = {
    "stop_reason": {"max_tokens"},
    "finish_reason": {"length", "max_tokens"},
}
_RESPONSES_INCOMPLETE_REASONS = {"max_output_tokens", "max_tokens"}


def _truncation_field(metadata: dict):
    """返回触发截断判定的 (字段, 值)；没截断则返回 None。"""
    for field, truncated_values in _TRUNCATION_MARKERS.items():
        value = metadata.get(field)
        if isinstance(value, str) and value.strip().lower() in truncated_values:
            return field, value
    # OpenAI Responses API：截断信息藏在嵌套的 incomplete_details 里
    if str(metadata.get("status", "")).lower() == "incomplete":
        details = metadata.get("incomplete_details") or {}
        reason = details.get("reason") if isinstance(details, dict) else None
        if isinstance(reason, str) and reason.strip().lower() in _RESPONSES_INCOMPLETE_REASONS:
            return "incomplete_details.reason", reason
    return None


def warn_if_truncated(response, model: str):
    """回复因为撞到输出上限被截断时，明确说出来。

    截断的表现是报告写到一半戛然而止，而返回值本身完全合法——不喊出来就是静默
    失败，用户只会以为"模型没写完"，根本想不到去调 max_tokens（#91）。
    """
    metadata = getattr(response, "response_metadata", None) or {}
    hit = _truncation_field(metadata)
    if hit:
        field, value = hit
        logger.warning(
            "模型 %s 的这次回复因为达到输出上限被截断（%s=%s），报告会缺一截。"
            "请在 config 里调大 `max_tokens`（或设环境变量 "
            "TRADINGAGENTS_MAX_TOKENS），例如 max_tokens=16000。",
            model, field, value,
        )
    return response


def normalize_content(response):
    """Normalize LLM response content to a plain string.

    Multiple providers (OpenAI Responses API, Google Gemini 3) return content
    as a list of typed blocks, e.g. [{'type': 'reasoning', ...}, {'type': 'text', 'text': '...'}].
    Downstream agents expect response.content to be a string. This extracts
    and joins the text blocks, discarding reasoning/metadata blocks.
    """
    content = response.content
    if isinstance(content, list):
        texts = [
            item.get("text", "") if isinstance(item, dict) and item.get("type") == "text"
            else item if isinstance(item, str) else ""
            for item in content
        ]
        response.content = "\n".join(t for t in texts if t)
    return response


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    def get_provider_name(self) -> str:
        """Return the provider name used in warning messages."""
        provider = getattr(self, "provider", None)
        if provider:
            return str(provider)
        return self.__class__.__name__.removesuffix("Client").lower()

    def warn_if_unknown_model(self) -> None:
        """Warn when the model is outside the known list for the provider."""
        if self.validate_model():
            return

        warnings.warn(
            (
                f"Model '{self.model}' is not in the known model list for "
                f"provider '{self.get_provider_name()}'. Continuing anyway."
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    @abstractmethod
    def get_llm(self) -> Any:
        """Return the configured LLM instance."""
        pass

    @abstractmethod
    def validate_model(self) -> bool:
        """Validate that the model is supported by this client."""
        pass
