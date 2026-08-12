import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError as exc:  # pragma: no cover - depends on optional install
    # No `[google]` extra exists any more (#87): langchain-google-genai needs
    # httpx>=0.28.1 while mootdx pins httpx<0.26, so the two cannot be locked
    # together. Give the actual install command instead of a bare
    # ModuleNotFoundError that leaves the user guessing.
    raise ImportError(
        "Gemini support requires langchain-google-genai, which conflicts with "
        "mootdx's httpx pin and therefore is not installed by default (#87).\n"
        "Install it explicitly (mootdx talks TDX over TCP and does not import "
        "httpx at runtime, so bumping httpx is safe in practice):\n"
        '  pip install --no-deps "langchain-google-genai>=4.0.0"\n'
        '  pip install "google-genai>=1.53.0" "httpx>=0.28.1"\n'
        "Or use a separate environment for Gemini. "
        "Any other provider (OpenAI / DeepSeek / Qwen / GLM / OpenAI-compatible) "
        "works without this."
    ) from exc

from .base_client import BaseLLMClient, normalize_content, warn_if_truncated
from .validators import validate_model


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output.

    Gemini 3 models return content as list of typed blocks.
    This normalizes to string for consistent downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        response = super().invoke(input, config, **kwargs)
        warn_if_truncated(response, self.model)
        return normalize_content(response)


class GoogleClient(BaseLLMClient):
    """Client for Google Gemini models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatGoogleGenerativeAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in ("timeout", "max_retries", "max_tokens", "callbacks", "http_client", "http_async_client"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Unified api_key maps to provider-specific google_api_key
        google_api_key = self.kwargs.get("api_key") or self.kwargs.get("google_api_key")
        if google_api_key:
            llm_kwargs["google_api_key"] = google_api_key

        # Map thinking_level to appropriate API param based on model
        # Gemini 3 Pro: low, high
        # Gemini 3 Flash: minimal, low, medium, high
        # Gemini 2.5: thinking_budget (0=disable, -1=dynamic)
        thinking_level = self.kwargs.get("thinking_level")
        if thinking_level:
            model_lower = self.model.lower()
            if "gemini-3" in model_lower:
                # Gemini 3 Pro doesn't support "minimal", use "low" instead
                if "pro" in model_lower and thinking_level == "minimal":
                    thinking_level = "low"
                llm_kwargs["thinking_level"] = thinking_level
            else:
                # Gemini 2.5: map levels to thinking_budget (0=off, -1=dynamic).
                # Do not silently collapse minimal/low/medium to 0 (F7.8).
                _GEMINI_25_BUDGETS = {
                    "minimal": 512,
                    "low": 1024,
                    "medium": 8192,
                    "high": -1,
                }
                level_key = str(thinking_level).lower()
                if level_key in _GEMINI_25_BUDGETS:
                    llm_kwargs["thinking_budget"] = _GEMINI_25_BUDGETS[level_key]
                else:
                    logger.warning(
                        "Unsupported google_thinking_level %r for Gemini 2.5; "
                        "expected one of %s. Leaving thinking_budget unset.",
                        thinking_level,
                        sorted(_GEMINI_25_BUDGETS),
                    )

        return NormalizedChatGoogleGenerativeAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Google."""
        return validate_model("google", self.model)
