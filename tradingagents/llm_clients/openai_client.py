import os
from typing import Any, Optional

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .capabilities import get_capabilities
from .validators import validate_model


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

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    def with_structured_output(self, schema, *, method=None, **kwargs):
        capabilities = get_capabilities(self.model_name)
        if capabilities.preferred_structured_method == "none":
            raise NotImplementedError(
                f"{self.model_name} has no structured-output method available"
            )
        method = method or capabilities.preferred_structured_method
        # DeepSeek V4/reasoner and MiniMax M2.x accept the schema as a tool,
        # but reject LangChain's function-spec ``tool_choice`` parameter.
        if method == "function_calling" and not capabilities.supports_tool_choice:
            kwargs.setdefault("tool_choice", None)
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

class MinimaxChatOpenAI(NormalizedChatOpenAI):
    """MiniMax M2.x adapter.

    M2.x embeds reasoning in ``<think>`` blocks by default.  The provider's
    ``reasoning_split`` request flag keeps that internal trace out of the
    user-facing content that downstream agents store and render.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        payload.setdefault("reasoning_split", True)
        return payload

# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
)

# Provider base URLs and API key env vars
_PROVIDER_CONFIG = {
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "glm": ("https://api.z.ai/api/paas/v4/", "ZHIPU_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
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
            api_key = (
                os.environ.get("OPENAI_COMPATIBLE_API_KEY")
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

        # Native OpenAI: use Responses API for consistent behavior across
        # all model families. Third-party providers use Chat Completions.
        if self.provider == "openai":
            llm_kwargs["use_responses_api"] = True

        # DeepSeek's thinking-mode quirks live in their own subclass so the
        # base NormalizedChatOpenAI stays free of provider-specific branches.
        if self.provider == "deepseek":
            chat_cls = DeepSeekChatOpenAI
        elif self.provider == "minimax":
            chat_cls = MinimaxChatOpenAI
        else:
            chat_cls = NormalizedChatOpenAI
        return chat_cls(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
