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
from typing import Literal, Optional


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
    supports_reasoning_split: bool = False
    default_max_tokens: Optional[int] = None


# DeepSeek V4 thinking 系的默认输出预算（reasoning + content 共用）。
#
# 来源：维护者在 PR #100 指出 8192 是“各家 Anthropic 兼容端点普遍支持的档位”
# （anthropic_client.py _THIRD_PARTY_DEFAULT_MAX_TOKENS = 8192，缘起 #91
# “报告写到一半结束”）。同一档位在 opencode-go 约 3 分钟 idle timeout 场景
# 下（#1204）可约束 V4 reasoning 链的无限输出——不设上限时后端的长 reasoning
# 链会导致网关空闲超时、进程挂起。PR #100 按维护者建议把**全局** 8192 撤回
# 为 None（provider 原生上限），8192 仅应作用于**经明确识别的 V4 模型**。
_DEEPSEEK_V4_DEFAULT_MAX_TOKENS = 8192

_DEEPSEEK_THINKING = ModelCapabilities(
    supports_tool_choice=False,
    supports_json_mode=True,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
    requires_reasoning_content_roundtrip=True,
    default_max_tokens=_DEEPSEEK_V4_DEFAULT_MAX_TOKENS,
)

_DEEPSEEK_CHAT = ModelCapabilities(
    supports_tool_choice=True,
    supports_json_mode=True,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
)

_MINIMAX_THINKING = ModelCapabilities(
    supports_tool_choice=True,
    supports_json_mode=False,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
    supports_reasoning_split=True,
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
    # 只匹配已实测的 V4 家族。`^deepseek-v\\d` 会连 deepseek-v3* 和未来所有版本一起
    # 吃掉，把「不接受 tool_choice」这个**只在 V4/reasoner 上验证过**的结论强加给
    # 未验证的型号——结构化输出会从强制 schema 工具调用降级为可选调用，反而更容易
    # 退回自由文本。与下方 MiniMax 同一把尺子：新家族实测过再加。
    (re.compile(r"^deepseek-v4(?:$|[.-])"), _DEEPSEEK_THINKING),
    (re.compile(r"^deepseek-reasoner"), _DEEPSEEK_THINKING),
    # ``reasoning_split`` is an M2.x capability; do not assume it for a
    # future MiniMax family (for example M3) until that API is verified.
    (re.compile(r"^MiniMax-M2(?:$|[.-])"), _MINIMAX_THINKING),
]


def get_capabilities(model_name: str) -> ModelCapabilities:
    """Resolve exact model IDs first, then forward-compatible patterns."""
    if model_name in _BY_ID:
        return _BY_ID[model_name]
    for pattern, capabilities in _BY_PATTERN:
        if pattern.match(model_name):
            return capabilities
    return _DEFAULT
