from typing import Optional

from .base_client import BaseLLMClient

# Providers that use the OpenAI-compatible chat completions API.
# "openai_compatible" is the generic pass-through for any relay/gateway that
# speaks the OpenAI Chat Completions API (9Router, AI Router, self-hosted
# proxies, …): the user supplies base_url + model + a generic API key, with no
# hard-coded vendor defaults (#77 / #81).
_OPENAI_COMPATIBLE = (
    "openai", "xai", "deepseek", "qwen", "glm", "ollama", "openrouter", "minimax",
    "requesty", "openai_compatible",
)


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Provider modules are imported lazily so that simply importing this
    factory (e.g. during test collection) does not pull in heavy LLM SDKs
    or fail when their API keys are absent.

    Args:
        provider: LLM provider name
        model: Model name/identifier
        base_url: Optional base URL for API endpoint
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured BaseLLMClient instance

    Raises:
        ValueError: If provider is not supported
    """
    # strip 与 lower 一起做，且**这里是唯一的中央边界**：provider 来自用户手写的
    # config / role_llms / 降级配置，`" DeepSeek "` 这种带空格的写法此前会一路走到
    # 最后一行报 `Unsupported LLM provider`，而调用方（trading_graph）那几处判据都已
    # strip 过 —— 两边不一致 = 韧性参数算对了、客户端却建不出来。
    provider_lower = provider.strip().lower()

    if provider_lower in _OPENAI_COMPATIBLE:
        from .openai_client import OpenAIClient
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "claude_agent_sdk":
        from .claude_agent_sdk_client import ClaudeAgentSDKClient
        return ClaudeAgentSDKClient(model, base_url, **kwargs)

    if provider_lower == "google":
        from .google_client import GoogleClient
        return GoogleClient(model, base_url, **kwargs)

    if provider_lower == "azure":
        from .azure_client import AzureOpenAIClient
        return AzureOpenAIClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
