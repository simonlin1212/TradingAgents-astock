"""Unit tests for DeepSeek V4 capability-based max_tokens bounding.

This bounds the output budget only for explicitly identified DeepSeek V4
thinking models via capabilities.py — not as a global DEFAULT_CONFIG cap.
See #100 review, #1204 and PR #100 boundary note.

Must cover:
1) V4 models (flash/pro/reasoner and pattern variants) get 8192
2) non-V4 models keep provider default (None)
3) V3.x not mis-matched
4) explicit max_tokens overrides the capability default
5) provider kwargs / request level receives correct value
6) existing capability/tool_choice/json_mode behaviours untouched
"""

import os

import pytest

from tradingagents.llm_clients.capabilities import (
    _DEEPSEEK_V4_DEFAULT_MAX_TOKENS,
    get_capabilities,
)
from tradingagents.llm_clients.openai_client import OpenAIClient
from tradingagents.graph.trading_graph import TradingAgentsGraph


@pytest.mark.unit
class TestV4GetsMaxTokens:
    def test_v4_exact_ids_get_8192(self):
        for model in ("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-reasoner"):
            cap = get_capabilities(model)
            assert cap.default_max_tokens == _DEEPSEEK_V4_DEFAULT_MAX_TOKENS

    def test_v4_pattern_variants_get_8192(self):
        for model in ("deepseek-v4", "deepseek-v4.1", "deepseek-v4-turbo"):
            assert get_capabilities(model).default_max_tokens == _DEEPSEEK_V4_DEFAULT_MAX_TOKENS

    def test_reasoner_pattern_gets_8192(self):
        assert get_capabilities("deepseek-reasoner-v2").default_max_tokens == _DEEPSEEK_V4_DEFAULT_MAX_TOKENS

    def test_constant_is_8192(self):
        # Single source of truth — matches anthropic third-party fallback (#91).
        assert _DEEPSEEK_V4_DEFAULT_MAX_TOKENS == 8192


@pytest.mark.unit
class TestNonV4NoCap:
    def test_v3_family_has_no_cap(self):
        for model in ("deepseek-v3", "deepseek-v3.2", "deepseek-chat"):
            assert get_capabilities(model).default_max_tokens is None

    def test_other_models_have_no_cap(self):
        for model in ("gpt-5.4", "MiniMax-M2.7", "mimo-v2.5", "unknown-model", "claude-sonnet-4"):
            assert get_capabilities(model).default_max_tokens is None

    def test_future_minimax_has_no_cap(self):
        assert get_capabilities("MiniMax-M3").default_max_tokens is None


@pytest.mark.unit
class TestExplicitOverridesCapability:
    def test_explicit_max_tokens_wins_on_openai_client(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        client = OpenAIClient(
            "deepseek-v4-pro",
            base_url="https://relay.example/v1",
            provider="openai_compatible",
            max_tokens=16000,
        )
        llm = client.get_llm()
        assert llm.max_tokens == 16000

    def test_no_explicit_gives_capability_default(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        client = OpenAIClient(
            "deepseek-v4-pro",
            base_url="https://relay.example/v1",
            provider="openai_compatible",
        )
        llm = client.get_llm()
        assert llm.max_tokens == _DEEPSEEK_V4_DEFAULT_MAX_TOKENS


@pytest.mark.unit
class TestProviderKwargsLevel:
    def test_graph_provider_kwargs_cap_flows_to_llm(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        # Config has no explicit max_tokens -> _get_provider_kwargs won't set it.
        g = TradingAgentsGraph.__new__(TradingAgentsGraph)
        g.config = {"max_tokens": None, "llm_provider": "openai_compatible"}
        kw = g._get_provider_kwargs()
        assert "max_tokens" not in kw
        # Yet OpenAIClient fills it for V4 via capabilities
        llm = OpenAIClient("deepseek-v4-pro", base_url="https://relay.example/v1", provider="openai_compatible", **kw).get_llm()
        assert llm.max_tokens == _DEEPSEEK_V4_DEFAULT_MAX_TOKENS

    def test_explicit_graph_max_tokens_wins(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        g = TradingAgentsGraph.__new__(TradingAgentsGraph)
        g.config = {"max_tokens": 12345, "llm_provider": "openai_compatible"}
        kw = g._get_provider_kwargs()
        assert kw["max_tokens"] == 12345
        llm = OpenAIClient("deepseek-v4-pro", base_url="https://relay.example/v1", provider="openai_compatible", **kw).get_llm()
        assert llm.max_tokens == 12345

    def test_non_v4_graph_no_cap_stays_none(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        g = TradingAgentsGraph.__new__(TradingAgentsGraph)
        g.config = {"max_tokens": None, "llm_provider": "openai_compatible"}
        kw = g._get_provider_kwargs()
        llm = OpenAIClient("deepseek-v3", base_url="https://relay.example/v1", provider="openai_compatible", **kw).get_llm()
        assert llm.max_tokens is None


@pytest.mark.unit
class TestNoRegressionOnExistingCapabilities:
    def test_v4_tool_choice_still_rejected(self):
        assert get_capabilities("deepseek-v4-pro").supports_tool_choice is False

    def test_v3_tool_choice_still_permissive(self):
        assert get_capabilities("deepseek-v3").supports_tool_choice is True

    def test_minimax_still_no_tool_choice_regression(self):
        cap = get_capabilities("MiniMax-M2.7")
        assert cap.supports_tool_choice is True
        assert cap.supports_reasoning_split is True

    def test_default_still_permissive(self):
        cap = get_capabilities("some-future-model")
        assert cap.supports_tool_choice is True
        assert cap.default_max_tokens is None
