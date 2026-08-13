from typing import Optional

from .base_client import BaseLLMClient

# Providers that use the OpenAI-compatible chat completions API.
# "openai_compatible" is the generic pass-through for any relay/gateway that
# speaks the OpenAI Chat Completions API (9Router, AI Router, self-hosted
# proxies, …): the user supplies base_url + model + a generic API key, with no
# hard-coded vendor defaults (#77 / #81).
_OPENAI_COMPATIBLE = (
    "openai", "xai", "deepseek", "qwen", "glm", "ollama", "openrouter", "minimax",
    "openai_compatible",
)

# 火山方舟的订阅套餐，走 Anthropic 兼容端点但用方舟自己的 Key 和模型名，
# 单独一个 client（见 volcengine_client），端点表在 model_catalog.ARK_PLAN_ENDPOINTS。
_VOLCENGINE_ARK = ("ark_coding", "ark_agent")


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
    provider_lower = provider.lower()

    if provider_lower in _OPENAI_COMPATIBLE:
        from .openai_client import OpenAIClient
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower in _VOLCENGINE_ARK:
        from .volcengine_client import VolcengineArkClient
        return VolcengineArkClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        from .google_client import GoogleClient
        return GoogleClient(model, base_url, **kwargs)

    if provider_lower == "azure":
        from .azure_client import AzureOpenAIClient
        return AzureOpenAIClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
