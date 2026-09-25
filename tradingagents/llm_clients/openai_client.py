import logging
import os
import time
from typing import Any, Optional

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from openai import (
    APIConnectionError,
    APIStatusError,
    InternalServerError,
    RateLimitError,
)

from .base_client import BaseLLMClient, normalize_content, warn_if_truncated
from .capabilities import get_capabilities
from .validators import validate_model

logger = logging.getLogger(__name__)

# SDK 层 max_retries 被我们置 0（见 trading_graph._resilience_kwargs），所以应用层
# 必须**至少覆盖 SDK 原本会重试的那一套**，否则"接管重试"就是净损失。
# openai/_base_client.py::_should_retry 实测：408 / 409 / 429 / >=500 + 连接类异常。
#   · >=500 → InternalServerError
#   · 429   → RateLimitError（**不是** InternalServerError 的子类，实测 issubclass=False）
#   · 连接类 → APIConnectionError（APITimeoutError 是它的子类，读超时一并覆盖）
#   · 408 / 409 没有专属异常类型，只能按状态码认：408 → 裸 APIStatusError，
#     409 → ConflictError。所以这里按 status_code 判，不按类型判。
_RETRY_STATUS_CODES = frozenset({408, 409})


def _is_retryable(exc: Exception) -> bool:
    """这个异常是不是 SDK 原本会重试的那一类。

    阴性侧同样要紧：400 / 401 / 404 这些重试也没用的错误必须**第一次就抛**，
    否则用户要干等三轮退避才看到"你的 key 不对"。所以这里不能图省事直接捕
    `APIStatusError` —— 那会把鉴权错误也一起重试掉。
    """
    if isinstance(exc, (APIConnectionError, InternalServerError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in _RETRY_STATUS_CODES
    return False


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output.

    The Responses API returns content as a list of typed blocks
    (reasoning, text, etc.). ``invoke`` normalizes to string for
    consistent downstream handling. ``with_structured_output`` defaults
    to function-calling so the Responses-API parse path is avoided
    (langchain-openai's parse path emits noisy
    PydanticSerializationUnexpectedValue warnings per call without
    affecting correctness).

    Provider-specific quirks (e.g. DeepSeek's thinking mode) live in
    purpose-built subclasses below so this base class stays small.
    """

    # 应用层重试参数（由 get_llm 从配置注入；SDK 层 max_retries 恒 0）。
    app_retries: int = 0
    app_retry_delay: float = 5.0   # 初始退避（秒），指数翻倍：5s, 10s, 20s...

    def invoke(self, input, config=None, **kwargs):
        # 应用层重试：SDK 层 max_retries 恒 0（见 trading_graph._resilience_kwargs），
        # 错误直接抛到这里，由本层按指数退避重试（5s, 10s, 20s...），而非 SDK 的 0.5s。
        # 可重试判据见模块级 `_is_retryable`：必须覆盖 SDK 原本会重试的那一套，
        # 否则"关掉 SDK 重试、改由应用层接管"对用户是净损失。
        #
        # `attempts` 夹到非负：app_retries 是普通 int 字段、没有下界，有人按
        # "-1 = 无限"的惯例去配时 range(0) 会让循环一次都不执行。
        attempts = max(0, self.app_retries)
        for attempt in range(attempts + 1):
            try:
                response = super().invoke(input, config, **kwargs)
                warn_if_truncated(response, self.model_name)
                return normalize_content(response)
            except (APIConnectionError, APIStatusError) as exc:
                if not _is_retryable(exc) or attempt >= attempts:
                    raise
                # 指数退避：app_retry_delay * 2^attempt（5s, 10s, 20s...）。
                delay = self.app_retry_delay * (2 ** attempt)
                if isinstance(exc, APIStatusError):
                    logger.warning(
                        "LLM 请求失败（HTTP %s），%s 秒后重试（%d/%d）",
                        exc.status_code, delay, attempt + 1, attempts,
                    )
                else:
                    logger.warning(
                        "LLM 连接失败（%s），%s 秒后重试（%d/%d）",
                        type(exc).__name__, delay, attempt + 1, attempts,
                    )
                time.sleep(delay)
        # 走不到：attempts >= 0 ⇒ 循环至少跑一轮，要么 return 要么 raise。
        # 但**不写 return None** —— 真走到了，调用方会在很远的地方炸在
        # `result.tool_calls` 上，根因完全看不出来（旧代码就是这样）。
        raise RuntimeError(  # pragma: no cover - 防御性，正常不可达
            f"LLM 重试循环未执行：app_retries={self.app_retries!r}"
        )

    def with_structured_output(self, schema, *, method=None, **kwargs):
        capabilities = get_capabilities(self.model_name)
        if capabilities.preferred_structured_method == "none":
            raise NotImplementedError(
                f"{self.model_name} has no structured-output method available"
            )
        method = method or capabilities.preferred_structured_method
        # DeepSeek V4/reasoner accept the schema as a tool, but reject
        # LangChain's function-spec ``tool_choice`` parameter.
        # Use pop-and-override rather than setdefault: with setdefault an
        # explicitly passed tool_choice survives and the API call still fails,
        # so the declared capability would not actually be enforced.
        if method == "function_calling" and not capabilities.supports_tool_choice:
            caller_value = kwargs.pop("tool_choice", None)
            if caller_value is not None:
                logger.warning(
                    "Dropping tool_choice=%r for %s: this model rejects the "
                    "parameter (see llm_clients/capabilities.py).",
                    caller_value, self.model_name,
                )
            kwargs["tool_choice"] = None
        return super().with_structured_output(schema, method=method, **kwargs)


def _input_to_messages(input_: Any) -> list:
    """Normalise a langchain LLM input to a list of message objects.

    Accepts a list of messages, a ``ChatPromptValue`` (from a
    ChatPromptTemplate), or anything else (treated as no messages).
    Used by providers that need to walk the outgoing message history;
    in particular DeepSeek thinking-mode propagation must work for
    both bare-list invocations and ChatPromptTemplate-driven ones, so
    treating only ``list`` here would silently skip half the call sites.
    """
    if isinstance(input_, list):
        return input_
    if hasattr(input_, "to_messages"):
        return input_.to_messages()
    return []


class DeepSeekChatOpenAI(NormalizedChatOpenAI):
    """DeepSeek-specific overrides on top of the OpenAI-compatible client.

    Two quirks that don't apply to other OpenAI-compatible providers:

    1. **Thinking-mode round-trip.** When DeepSeek's thinking models return
       a response with ``reasoning_content``, that field must be echoed
       back as part of the assistant message on the next turn or the API
       fails with HTTP 400. ``_create_chat_result`` captures the field on
       receive and ``_get_request_payload`` re-attaches it on send.

    2. **DeepSeek reasoning models reject ``tool_choice``.** Their schema is
       still bound as a tool, while the capability-aware base class suppresses
       only the incompatible request parameter.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        outgoing = payload.get("messages", [])
        for message_dict, message in zip(outgoing, _input_to_messages(input_)):
            if not isinstance(message, AIMessage):
                continue
            reasoning = message.additional_kwargs.get("reasoning_content")
            if reasoning is not None:
                message_dict["reasoning_content"] = reasoning
        return payload

    def _create_chat_result(self, response, generation_info=None):
        chat_result = super()._create_chat_result(response, generation_info)
        response_dict = (
            response
            if isinstance(response, dict)
            else response.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}}
            )
        )
        for generation, choice in zip(
            chat_result.generations, response_dict.get("choices", [])
        ):
            reasoning = choice.get("message", {}).get("reasoning_content")
            if reasoning is not None:
                generation.message.additional_kwargs["reasoning_content"] = reasoning
        return chat_result

    def _convert_chunk_to_generation_chunk(
        self, chunk, default_chunk_class, base_generation_info
    ):
        # langchain-openai's streaming path drops ``reasoning_content`` from
        # deltas. Rescue it into ``additional_kwargs`` so the round-trip on
        # the next turn — see ``_get_request_payload`` — still has it. Chunk
        # aggregation in langchain-core concatenates string additional_kwargs,
        # yielding the complete reasoning_content on the final AIMessage.
        gen_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen_chunk is None:
            return None
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
        if choices:
            reasoning = (choices[0].get("delta") or {}).get("reasoning_content")
            if reasoning:
                gen_chunk.message.additional_kwargs["reasoning_content"] = reasoning
        return gen_chunk

class MinimaxChatOpenAI(NormalizedChatOpenAI):
    """MiniMax M2.x adapter.

    M2.x embeds reasoning in ``<think>`` blocks by default.  The provider's
    ``reasoning_split`` request flag keeps that internal trace out of the
    user-facing content that downstream agents store and render.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        capabilities = get_capabilities(self.model_name)
        if capabilities.supports_reasoning_split:
            payload.setdefault("reasoning_split", True)
        return payload

# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort", "max_tokens",
    "api_key", "callbacks", "http_client", "http_async_client",
    "stream_usage",
)

# Provider base URLs and API key env vars
_PROVIDER_CONFIG = {
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "glm": ("https://open.bigmodel.cn/api/paas/v4/", "ZHIPU_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "requesty": ("https://router.requesty.ai/v1", "REQUESTY_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    "minimax": ("https://api.minimax.chat/v1", "MINIMAX_API_KEY"),
}


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI, Ollama, OpenRouter, and xAI providers.

    For native OpenAI models, uses the Responses API (/v1/responses) which
    supports reasoning_effort with function tools across all model families
    (GPT-4.1, GPT-5). Third-party compatible providers (xAI, OpenRouter,
    Ollama) use standard Chat Completions.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        # Generic OpenAI-compatible relay (#77 / #81): the user supplies the
        # base_url and model themselves, and the API key comes from a generic
        # env var. No vendor defaults — this is the escape hatch for any
        # gateway (9Router, AI Router, self-hosted proxy) that speaks the
        # OpenAI Chat Completions API.
        if self.provider == "openai_compatible":
            if not self.base_url:
                raise RuntimeError(
                    "openai_compatible 需要填写 base_url。请在 Web 侧栏「API Base URL」"
                    "或配置 `backend_url` 里填写你的 OpenAI 兼容网关地址"
                    "（例如 https://your-relay.example/v1）。"
                )
            llm_kwargs["base_url"] = self.base_url
            # Per-role api_key (from role_llms spec) wins over env vars, so
            # several OpenAI-compatible gateways with different keys can run
            # side by side (e.g. opencode-go + a local proxy relay).
            api_key = (
                self.kwargs.get("api_key")
                or os.environ.get("OPENAI_COMPATIBLE_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
            )
            if api_key:
                llm_kwargs["api_key"] = api_key
            elif "api_key" not in self.kwargs:
                raise RuntimeError(
                    "未找到 openai_compatible 的 API Key。请在 .env 文件或环境变量中设置 "
                    "`OPENAI_COMPATIBLE_API_KEY=你的key`（也接受 `OPENAI_API_KEY`），"
                    "设置后重启程序。"
                )
        # Provider-specific base URL and auth. An explicit base_url on the
        # client (e.g. a corporate proxy) takes precedence over the
        # provider default so users can route through their own gateway.
        elif self.provider in _PROVIDER_CONFIG:
            default_base, api_key_env = _PROVIDER_CONFIG[self.provider]
            llm_kwargs["base_url"] = self.base_url or default_base
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
                elif "api_key" not in self.kwargs:
                    # Without this, ChatOpenAI fails downstream with a confusing
                    # "OPENAI_API_KEY must be set" — but deepseek/qwen/glm/minimax
                    # each need their OWN env var. Name the exact one (#42).
                    raise RuntimeError(
                        f"未找到 {self.provider} 的 API Key。请在 .env 文件或环境变量中设置 "
                        f"`{api_key_env}`（例如 `{api_key_env}=你的key`），设置后重启程序。"
                        f"注意：{self.provider} 用的是 {api_key_env}，不是 OPENAI_API_KEY。"
                    )
            else:
                llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # Forward user-provided kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Model-specific output budget via capabilities.py — not a global cap.
        # DeepSeek V4 reasoning 链不设上限会撞 opencode-go 约 3 分钟 idle timeout
        #（#1204），但全局 8192 会误伤 Claude/Gemini 等（见 PR #100 review）。
        # 仅当用户未显式设 max_tokens 时，按 capabilities 的 default_max_tokens
        # 兜底，且 matcher 严格限于 V4 家族（capabilities.py: ^deepseek-v4）。
        if "max_tokens" not in llm_kwargs:
            cap = get_capabilities(self.model)
            if cap.default_max_tokens is not None:
                llm_kwargs["max_tokens"] = cap.default_max_tokens

        # 应用层重试参数（不进 _PASSTHROUGH_KWARGS，但需传给 NormalizedChatOpenAI）。
        llm_kwargs["app_retries"] = self.kwargs.get("app_retries", 0)
        llm_kwargs["app_retry_delay"] = self.kwargs.get("app_retry_delay", 5.0)

        # Native OpenAI: use Responses API for consistent behavior across
        # all model families. Third-party providers use Chat Completions.
        if self.provider == "openai":
            llm_kwargs["use_responses_api"] = True

        # The OpenCode Go gateway (opencode.ai) drops the connection on long
        # non-streamed responses (~3 min idle timeout, #782/#1204). Streaming
        # keeps the socket active; langchain aggregates chunks back to a single
        # AIMessage so callers see no difference.
        base_url_for_check = llm_kwargs.get("base_url", "") or ""
        is_opencode_go = "opencode.ai" in base_url_for_check
        if is_opencode_go:
            llm_kwargs.setdefault("streaming", True)
            # 开流式就必须一起开 stream_usage，否则 token 统计**静默归零**：
            # langchain 只在非流式回复上自带 usage_metadata，流式下要显式
            # stream_options.include_usage 才带得回来；而它的自动开启逻辑在设了
            # openai_api_base 时直接跳过（ChatOpenAI._should_stream_usage）——
            # opencode 这条路恒定设了 base_url，所以永远轮不到自动开启。
            # 后果不报错：cli/stats_handler.py 只认 usage_metadata，整轮跑完面板
            # 写 tokens_in=0 / tokens_out=0，看起来像"这次没花钱"。
            # 用 setdefault 是为了留逃生口：stream_usage 在 _PASSTHROUGH_KWARGS 里，
            # 用户显式传 False 时以用户的为准。
            llm_kwargs.setdefault("stream_usage", True)

        # DeepSeek's thinking-mode quirks live in their own subclass so the
        # base NormalizedChatOpenAI stays free of provider-specific branches.
        # On the OpenCode Go gateway, DeepSeek models also need the subclass
        # (streaming reasoning_content round-trip).
        is_deepseek_model = "deepseek" in self.model.lower()
        if self.provider == "deepseek" or (is_opencode_go and is_deepseek_model):
            chat_cls = DeepSeekChatOpenAI
        elif self.provider == "minimax":
            chat_cls = MinimaxChatOpenAI
        else:
            chat_cls = NormalizedChatOpenAI
        return chat_cls(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
