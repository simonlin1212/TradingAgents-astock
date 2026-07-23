"""Unit tests for model-specific structured-output dispatch."""

import pytest
from pydantic import BaseModel

from tradingagents.llm_clients.capabilities import get_capabilities
from tradingagents.llm_clients.openai_client import MinimaxChatOpenAI


@pytest.mark.unit
def test_deepseek_v4_and_reasoner_reject_tool_choice():
    for model in ("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-reasoner"):
        capabilities = get_capabilities(model)
        assert capabilities.supports_tool_choice is False
        assert capabilities.requires_reasoning_content_roundtrip is True


@pytest.mark.unit
def test_minimax_m2_variants_reject_tool_choice():
    for model in ("MiniMax-M2", "MiniMax-M2.7", "MiniMax-M2.7-highspeed"):
        capabilities = get_capabilities(model)
        assert capabilities.supports_tool_choice is False
        assert capabilities.supports_json_mode is False


@pytest.mark.unit
def test_unknown_model_uses_permissive_defaults():
    capabilities = get_capabilities("some-future-model")
    assert capabilities.supports_tool_choice is True
    assert capabilities.preferred_structured_method == "function_calling"


@pytest.mark.unit
def test_minimax_payload_enables_reasoning_split():
    client = MinimaxChatOpenAI(
        model="MiniMax-M2.7",
        api_key="placeholder",
        base_url="https://api.minimax.chat/v1",
    )
    payload = client._get_request_payload([{"role": "user", "content": "hi"}])
    assert payload.get("reasoning_split") is True


@pytest.mark.unit
def test_minimax_structured_output_keeps_schema_but_omits_tool_choice():
    class _Sample(BaseModel):
        answer: str

    client = MinimaxChatOpenAI(
        model="MiniMax-M2.7",
        api_key="placeholder",
        base_url="https://api.minimax.chat/v1",
    )
    wrapped = client.with_structured_output(_Sample)
    first = wrapped.steps[0] if hasattr(wrapped, "steps") else wrapped
    kwargs = getattr(first, "kwargs", {})

    assert kwargs.get("tool_choice") is None or "tool_choice" not in kwargs
    assert any(
        tool.get("function", {}).get("name") == "_Sample"
        for tool in kwargs.get("tools", [])
    )
