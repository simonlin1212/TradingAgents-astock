"""Model name validators for each provider."""

from .model_catalog import get_known_models


# Providers whose model names are user-supplied and free-form, so any model
# string is accepted without warning.
# 方舟订阅套餐（ark_coding / ark_agent）也在内：方舟会持续上下线模型，硬校验
# 会对刚上线的模型误报。model_catalog 里给了常用项做下拉，但不限制取值。
_ANY_MODEL_PROVIDERS = (
    "ollama", "openrouter", "openai_compatible", "ark_coding", "ark_agent",
)

VALID_MODELS = {
    provider: models
    for provider, models in get_known_models().items()
    if provider not in _ANY_MODEL_PROVIDERS
}


def validate_model(provider: str, model: str) -> bool:
    """Check if model name is valid for the given provider.

    For ollama, openrouter, openai_compatible - any model is accepted.
    """
    provider_lower = provider.lower()

    if provider_lower in _ANY_MODEL_PROVIDERS:
        return True

    if provider_lower not in VALID_MODELS:
        return True

    return model in VALID_MODELS[provider_lower]
