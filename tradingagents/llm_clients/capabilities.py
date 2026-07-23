"""Declarative capabilities for OpenAI-compatible model adapters.

Different OpenAI-compatible providers do not expose an identical API.  In
particular, some reasoning models accept a ``tools`` array but reject the
``tool_choice`` value emitted by LangChain's structured-output binding.  Keep
those quirks in a small, immutable table so the client adapter does not grow
model-name conditionals every time a provider adds a model variant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


StructuredMethod = Literal[
    "function_calling",
    "json_mode",
    "json_schema",
    "none",
]


@dataclass(frozen=True)
class ModelCapabilities:
    """API features relevant to structured agent output."""

    supports_tool_choice: bool
    supports_json_mode: bool
    supports_json_schema: bool
    preferred_structured_method: StructuredMethod
    requires_reasoning_content_roundtrip: bool = False


_DEEPSEEK_THINKING = ModelCapabilities(
    supports_tool_choice=False,
    supports_json_mode=True,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
    requires_reasoning_content_roundtrip=True,
)

_DEEPSEEK_CHAT = ModelCapabilities(
    supports_tool_choice=True,
    supports_json_mode=True,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
)

_MINIMAX_THINKING = ModelCapabilities(
    supports_tool_choice=False,
    supports_json_mode=False,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
)

_DEFAULT = ModelCapabilities(
    supports_tool_choice=True,
    supports_json_mode=True,
    supports_json_schema=True,
    preferred_structured_method="function_calling",
)


_BY_ID: dict[str, ModelCapabilities] = {
    "deepseek-chat": _DEEPSEEK_CHAT,
    "deepseek-reasoner": _DEEPSEEK_THINKING,
    "deepseek-v4-flash": _DEEPSEEK_THINKING,
    "deepseek-v4-pro": _DEEPSEEK_THINKING,
    "MiniMax-M2": _MINIMAX_THINKING,
    "MiniMax-M2.1": _MINIMAX_THINKING,
    "MiniMax-M2.1-highspeed": _MINIMAX_THINKING,
    "MiniMax-M2.5": _MINIMAX_THINKING,
    "MiniMax-M2.5-highspeed": _MINIMAX_THINKING,
    "MiniMax-M2.7": _MINIMAX_THINKING,
    "MiniMax-M2.7-highspeed": _MINIMAX_THINKING,
}

_BY_PATTERN: list[tuple[re.Pattern[str], ModelCapabilities]] = [
    (re.compile(r"^deepseek-v\d"), _DEEPSEEK_THINKING),
    (re.compile(r"^deepseek-reasoner"), _DEEPSEEK_THINKING),
    (re.compile(r"^MiniMax-M\d"), _MINIMAX_THINKING),
]


def get_capabilities(model_name: str) -> ModelCapabilities:
    """Resolve exact model IDs first, then forward-compatible patterns."""
    if model_name in _BY_ID:
        return _BY_ID[model_name]
    for pattern, capabilities in _BY_PATTERN:
        if pattern.match(model_name):
            return capabilities
    return _DEFAULT
