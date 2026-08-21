"""Tests for the generic ``openai_compatible`` provider (#77 / #81).

A pass-through for any relay/gateway that speaks the OpenAI Chat Completions
API (9Router, AI Router, self-hosted proxy): the user supplies base_url +
model + a generic API key, with no hard-coded vendor defaults.
"""

import pytest

from tradingagents.llm_clients.factory import _OPENAI_COMPATIBLE, create_llm_client
from tradingagents.llm_clients.openai_client import (
    DeepSeekChatOpenAI,
    NormalizedChatOpenAI,
    OpenAIClient,
)


@pytest.mark.unit
class TestFactoryRouting:
    def test_openai_compatible_is_routed_to_openai_client(self):
        assert "openai_compatible" in _OPENAI_COMPATIBLE
        client = create_llm_client(
            "openai_compatible", "any-model", base_url="https://relay.example/v1"
        )
        assert isinstance(client, OpenAIClient)
        assert client.provider == "openai_compatible"


@pytest.mark.unit
class TestOpenAICompatibleClient:
    def test_missing_base_url_raises(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        client = OpenAIClient("m", base_url=None, provider="openai_compatible")
        with pytest.raises(RuntimeError, match="base_url"):
            client.get_llm()

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        client = OpenAIClient("m", base_url="https://relay.example/v1", provider="openai_compatible")
        with pytest.raises(RuntimeError, match="API Key"):
            client.get_llm()

    def test_uses_dedicated_env_key_and_base_url(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "relay-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        client = OpenAIClient(
            "my-model", base_url="https://relay.example/v1", provider="openai_compatible"
        )
        llm = client.get_llm()
        # Chat Completions (not OpenAI's Responses API) for max compatibility.
        assert isinstance(llm, NormalizedChatOpenAI)
        assert str(llm.openai_api_base) == "https://relay.example/v1"

    def test_falls_back_to_openai_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "fallback-key")
        client = OpenAIClient(
            "my-model", base_url="https://relay.example/v1", provider="openai_compatible"
        )
        # Must not raise — the OPENAI_API_KEY fallback supplies the credential.
        assert client.get_llm() is not None

    def test_custom_model_does_not_warn(self, monkeypatch, recwarn):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        client = OpenAIClient(
            "totally-custom-model", base_url="https://relay.example/v1",
            provider="openai_compatible",
        )
        client.get_llm()
        assert not [w for w in recwarn if "not in the known model list" in str(w.message)]

    def test_per_role_api_key_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "env-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # api_key passed via kwargs (role_llms spec) must take precedence.
        client = OpenAIClient(
            "my-model", base_url="https://relay.example/v1",
            provider="openai_compatible", api_key="role-key",
        )
        llm = client.get_llm()
        assert llm.client._client.api_key == "role-key"

    def test_role_api_key_absent_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "env-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        client = OpenAIClient(
            "my-model", base_url="https://relay.example/v1",
            provider="openai_compatible",
        )
        llm = client.get_llm()
        assert llm.client._client.api_key == "env-key"


@pytest.mark.unit
class TestOpenCodeGoStreaming:
    def test_opencode_go_deepseek_enables_streaming_and_subclass(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        client = OpenAIClient(
            "deepseek-v4-pro", base_url="https://opencode.ai/zen/go/v1",
            provider="openai_compatible",
        )
        llm = client.get_llm()
        assert llm.streaming is True
        assert isinstance(llm, DeepSeekChatOpenAI)

    def test_non_opencode_base_url_keeps_streaming_off(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        client = OpenAIClient(
            "deepseek-v4-pro", base_url="https://relay.example/v1",
            provider="openai_compatible",
        )
        llm = client.get_llm()
        assert llm.streaming is False
        assert not isinstance(llm, DeepSeekChatOpenAI)

    def test_opencode_go_non_deepseek_model_streams_but_no_subclass(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        client = OpenAIClient(
            "mimo-v2.5", base_url="https://opencode.ai/zen/go/v1",
            provider="openai_compatible",
        )
        llm = client.get_llm()
        assert llm.streaming is True
        assert not isinstance(llm, DeepSeekChatOpenAI)


@pytest.mark.unit
class TestDeepSeekStreamingReasoningCapture:
    def test_capture_reasoning_content_on_streaming_chunk(self):
        from langchain_core.messages import AIMessageChunk

        llm = DeepSeekChatOpenAI(model="deepseek-v4-pro", api_key="k")
        chunk = {
            "choices": [{"delta": {"reasoning_content": "让我想想", "content": "答案是2"}}]
        }
        gen_chunk = llm._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, {})
        assert gen_chunk is not None
        assert gen_chunk.message.additional_kwargs.get("reasoning_content") == "让我想想"

    def test_chunk_without_reasoning_is_left_untouched(self):
        from langchain_core.messages import AIMessageChunk

        llm = DeepSeekChatOpenAI(model="deepseek-v4-pro", api_key="k")
        chunk = {"choices": [{"delta": {"content": "普通回答"}}]}
        gen_chunk = llm._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, {})
        assert gen_chunk is not None
        assert "reasoning_content" not in gen_chunk.message.additional_kwargs
