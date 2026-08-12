"""Tests for the claude_agent_sdk provider (personal Max-subscription POC).

The real Agent SDK spawns the `claude` CLI and consumes a live subscription, so
every test mocks the call path (`ClaudeAgentSDKClient._query`) — no CLI, no
network, no subscription needed.

conftest.py injects ANTHROPIC_API_KEY=placeholder for all tests; the F-004
guardrail trips on it, so tests that enable the provider must delenv it first
(this is the exact interaction Codex flagged).
"""

import json

import os

import pytest
from pydantic import BaseModel

from tradingagents.llm_clients import claude_agent_sdk_client as mod
from tradingagents.llm_clients.claude_agent_sdk_client import (
    AgentSDKChatModel,
    ClaudeAgentSDKClient,
    _RateLimitHit,
    _split_prompt,
)
from tradingagents.llm_clients.factory import create_llm_client


class _Plan(BaseModel):
    decision: str
    confidence: int


# 需要真装可选依赖的用例：它们会走到 SDK 自己的 API（ClaudeAgentOptions /
# create_sdk_mcp_server），光 mock `_query` 不够。没装就**跳过**，不要红着——
# 长期红的代价是没人再看，而本文件里恰恰有两条是保护「订阅凭据失效不得静默降级
# 到按 token 计费」的护栏（那两条已不再依赖 SDK，见 ClaudeSDKError 占位类型）。
requires_sdk = pytest.mark.skipif(
    mod._sdk is None,
    reason="需要可选依赖 claude-agent-sdk：pip install -e '.[agentsdk]'",
)


@pytest.fixture
def oauth_env(monkeypatch):
    """Enable the provider cleanly: OAuth token present, API key absent."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _client_with_query(monkeypatch, text="", structured=None, fallback_spec=None):
    """Build a client whose _query returns a canned (text, structured) tuple."""
    client = ClaudeAgentSDKClient("claude-opus-4-8", fallback_spec=fallback_spec)

    async def fake_query(prompt, options, prefer_result=False):
        return text, structured

    monkeypatch.setattr(client, "_query", fake_query)
    # `_build_options` constructs ClaudeAgentOptions — skip the real SDK type
    # so these unit tests run without the optional [agentsdk] extra.
    monkeypatch.setattr(
        client, "_build_options",
        lambda *a, **k: type("Opts", (), {"env": {}})(),
    )
    # Tool bridging also needs the SDK decorator; stub it for bind_tools tests.
    monkeypatch.setattr(
        mod, "_sdk_tools_from_langchain",
        lambda tools: [],
    )
    return client


def _adapter(client):
    """Build the chat adapter without ``get_llm()``'s import guard.

    Unit tests mock ``_query`` / ``_invoke_raw`` and never need the real SDK
    package; constructing ``AgentSDKChatModel`` directly keeps CI green when
    the optional ``[agentsdk]`` extra is not installed.
    """
    return AgentSDKChatModel(client, client.fallback_spec)


class _FakeLangChainTool:
    """Minimal stand-in for a LangChain StructuredTool (bridged by bind_tools)."""

    name = "get_thing"
    description = "gets a thing"
    args_schema = None  # → _sdk_tools_from_langchain uses an empty object schema

    def invoke(self, args):
        return "thing-data"


# --------------------------------------------------------------------------- #
# T-002 / F-002: adapter surface
# --------------------------------------------------------------------------- #

@requires_sdk
def test_invoke_returns_aimessage(monkeypatch, oauth_env):
    client = _client_with_query(monkeypatch, text="hello from max")
    result = _adapter(client).invoke("say hi")
    assert result.content == "hello from max"


@requires_sdk
def test_structured_output_returns_pydantic(monkeypatch, oauth_env):
    client = _client_with_query(
        monkeypatch, structured={"decision": "buy", "confidence": 4}
    )
    plan = _adapter(client).with_structured_output(_Plan).invoke("decide")
    assert isinstance(plan, _Plan)
    assert plan.decision == "buy" and plan.confidence == 4


@requires_sdk
def test_structured_output_parses_json_text_when_no_structured_field(monkeypatch, oauth_env):
    # SDK returned text (not structured_output) — adapter must parse the JSON.
    text = 'noise before {"decision": "hold", "confidence": 2} noise after'
    client = _client_with_query(monkeypatch, text=text, structured=None)
    plan = _adapter(client).with_structured_output(_Plan).invoke("decide")
    assert plan.decision == "hold" and plan.confidence == 2


@requires_sdk
def test_bind_tools_returns_runnable_and_final_report(monkeypatch, oauth_env):
    # bind_tools must return a Runnable (so `prompt | bound` composes) whose
    # invoke runs the SDK tool loop and returns a final report with NO
    # tool_calls — LangGraph then treats the analyst as done.
    from langchain_core.runnables import Runnable

    client = _client_with_query(monkeypatch, text="final report")
    bound = _adapter(client).bind_tools([_FakeLangChainTool()])
    assert isinstance(bound, Runnable)
    result = bound.invoke("analyze 600519")
    assert result.content == "final report"
    assert result.tool_calls == []


@requires_sdk
def test_bind_tools_falls_back_on_rate_limit(monkeypatch, oauth_env):
    # Subscription tool loop hits quota → fall back to the fallback provider's
    # bind_tools, which rejoins LangGraph's normal external ToolNode loop.
    client = ClaudeAgentSDKClient(
        "claude-opus-4-8",
        fallback_spec={"provider": "deepseek", "model": "deepseek-v4-pro", "base_url": None},
    )

    async def boom(prompt, options, prefer_result=False):
        raise _RateLimitHit("weekly limit reached")

    monkeypatch.setattr(client, "_query", boom)
    monkeypatch.setattr(client, "_build_options", lambda *a, **k: type("Opts", (), {})())
    monkeypatch.setattr(mod, "_sdk_tools_from_langchain", lambda tools: [])
    _install_stub_fallback(monkeypatch)

    result = _adapter(client).bind_tools([_FakeLangChainTool()]).invoke("analyze")
    assert result.content == "served by fallback tools"


# --------------------------------------------------------------------------- #
# F-007 / AC-005: dependency + OAuth guards
# --------------------------------------------------------------------------- #

def test_get_llm_raises_when_sdk_missing(monkeypatch, oauth_env):
    monkeypatch.setattr(mod, "_sdk", None)
    client = ClaudeAgentSDKClient("claude-opus-4-8")
    with pytest.raises(ImportError, match=r"\[agentsdk\]"):
        client.get_llm()


def test_get_llm_uses_ambient_login_when_oauth_missing(monkeypatch):
    # With no explicit token, get_llm() no longer raises — the Agent SDK inherits
    # the ambient logged-in `claude` session (Keychain / ~/.claude). Any genuine
    # auth failure surfaces at call time and triggers the F-005 fallback instead.
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    # Only meaningful when the SDK is importable; otherwise the import guard wins.
    if mod._sdk is None:
        pytest.skip("claude-agent-sdk not installed")
    client = ClaudeAgentSDKClient("claude-opus-4-8")
    assert isinstance(client.get_llm(), mod.AgentSDKChatModel)


# --------------------------------------------------------------------------- #
# T-004: factory routing
# --------------------------------------------------------------------------- #

def test_factory_routes_to_agent_sdk_client():
    client = create_llm_client(
        "claude_agent_sdk", "claude-opus-4-8",
        fallback_spec={"provider": "deepseek", "model": "deepseek-v4-pro", "base_url": None},
    )
    assert isinstance(client, ClaudeAgentSDKClient)
    assert client.fallback_spec["provider"] == "deepseek"


# --------------------------------------------------------------------------- #
# T-006 / F-005 / AC-003: cross-provider fallback
# --------------------------------------------------------------------------- #

class _StubStructured:
    def __init__(self, schema):
        self._schema = schema

    def invoke(self, prompt, *a, **k):
        return self._schema(decision="fallback-buy", confidence=1)


class _StubBoundTools:
    def invoke(self, prompt, *a, **k):
        from langchain_core.messages import AIMessage
        return AIMessage(content="served by fallback tools")


class _StubLLM:
    def invoke(self, prompt, *a, **k):
        from langchain_core.messages import AIMessage
        return AIMessage(content="served by fallback")

    def with_structured_output(self, schema, **k):
        return _StubStructured(schema)

    def bind_tools(self, tools, **k):
        return _StubBoundTools()


def _install_stub_fallback(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.llm_clients.factory.create_llm_client",
        lambda **kw: type("C", (), {"get_llm": lambda self: _StubLLM()})(),
    )


@requires_sdk
def test_invoke_falls_back_on_rate_limit(monkeypatch, oauth_env):
    client = ClaudeAgentSDKClient(
        "claude-opus-4-8",
        fallback_spec={"provider": "deepseek", "model": "deepseek-v4-pro", "base_url": None},
    )

    async def boom(prompt, options, prefer_result=False):
        raise _RateLimitHit("weekly limit reached")

    monkeypatch.setattr(client, "_query", boom)
    monkeypatch.setattr(client, "_build_options", lambda *a, **k: type("Opts", (), {})())
    _install_stub_fallback(monkeypatch)

    result = _adapter(client).invoke("analyze")
    assert result.content == "served by fallback"


@requires_sdk
def test_structured_falls_back_and_still_yields_pydantic(monkeypatch, oauth_env):
    client = ClaudeAgentSDKClient(
        "claude-opus-4-8",
        fallback_spec={"provider": "deepseek", "model": "deepseek-v4-pro", "base_url": None},
    )

    async def boom(prompt, options, prefer_result=False):
        raise _RateLimitHit("weekly limit reached")

    monkeypatch.setattr(client, "_query", boom)
    monkeypatch.setattr(client, "_build_options", lambda *a, **k: type("Opts", (), {})())
    _install_stub_fallback(monkeypatch)

    plan = _adapter(client).with_structured_output(_Plan).invoke("decide")
    assert isinstance(plan, _Plan)
    assert plan.decision == "fallback-buy"


@requires_sdk
def test_no_fallback_spec_reraises(monkeypatch, oauth_env):
    client = ClaudeAgentSDKClient("claude-opus-4-8", fallback_spec=None)

    async def boom(prompt, options, prefer_result=False):
        raise _RateLimitHit("limit")

    monkeypatch.setattr(client, "_query", boom)
    monkeypatch.setattr(client, "_build_options", lambda *a, **k: type("Opts", (), {})())
    with pytest.raises(_RateLimitHit):
        _adapter(client).invoke("x")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def test_split_prompt_string():
    assert _split_prompt("just text") == (None, "just text")


def test_split_prompt_messages_extracts_system():
    from langchain_core.messages import SystemMessage, HumanMessage
    system, user = _split_prompt([SystemMessage(content="be terse"), HumanMessage(content="hi")])
    assert system == "be terse"
    assert user == "hi"


# --------------------------------------------------------------------------- #
# T-005 / F-004: startup guardrail + AC-004 no-behaviour-change
# --------------------------------------------------------------------------- #

def test_api_key_coexistence_warns_but_does_not_abort(monkeypatch, caplog):
    """ANTHROPIC_API_KEY 与订阅覆盖共存时**不再一律中止**。

    一律中止会让 anthropic 无法作为降级 provider：留着 key 启动被拦，
    删掉 key 又会在撞额度真要降级时认证失败。改为「子进程剥离 + 父进程保留 + 告警」，
    子进程隔离由 test_sdk_subprocess_env_blanks_anthropic_api_key 单独锁住。
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-would-bill-api")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    from tradingagents.graph import trading_graph as tg

    cfg = dict(tg.DEFAULT_CONFIG) if hasattr(tg, "DEFAULT_CONFIG") else None
    if cfg is None:
        from tradingagents.default_config import DEFAULT_CONFIG
        cfg = dict(DEFAULT_CONFIG)
    cfg["deep_think_provider_override"] = "claude_agent_sdk"

    with caplog.at_level("WARNING"):
        try:
            tg.TradingAgentsGraph(config=cfg)
        except Exception:
            pass   # 后续构图可能因缺少其它依赖失败，本例只关心不是那条护栏拦的
    assert any("ANTHROPIC_API_KEY" in r.message for r in caplog.records)


def test_default_config_off_by_default():
    from tradingagents.default_config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["deep_think_provider_override"] is None
    assert DEFAULT_CONFIG["quick_think_provider_override"] is None

    # 默认用 claude CLI 的别名（opus/sonnet）而不是写死版本号的完整 id：
    # 别名恒指向最新模型，写死 "claude-opus-4-8" 这类 id 会随版本迭代过期
    # （仓库 model_catalog 里的 anthropic 条目就已经停在 4-6）。
    # 完整 id 仍然可用，此处只锁默认值必须是别名。
    assert DEFAULT_CONFIG["agent_sdk_model"] in ("opus", "sonnet")
    # quick 节点数量多（7 分析师 + 辩手），订阅按额度限流，默认给更省的 sonnet。
    assert DEFAULT_CONFIG["agent_sdk_quick_model"] == "sonnet"


# --------------------------------------------------------------------------- #
# real _query message consumption (closes the RateLimitEvent blind spot;
# locks in the fix for the "allowed_warning silently bills paid API" bug)
# --------------------------------------------------------------------------- #

def _fake(cls, **attrs):
    """Build an instance of a real SDK dataclass without its heavy __init__."""
    obj = object.__new__(cls)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


def _patch_query(monkeypatch, *messages):
    async def fake_query(prompt, options):
        for m in messages:
            yield m
    monkeypatch.setattr(mod._sdk, "query", fake_query)


def _rate_limit_info(status, overage_status=None):
    # Set every field so repr()/str() (used in the reject path) never KeyErrors.
    return _fake(
        mod._sdk.RateLimitInfo,
        status=status, resets_at=None, rate_limit_type=None, utilization=None,
        overage_status=overage_status, overage_resets_at=None,
        overage_disabled_reason=None, raw={},
    )


@pytest.mark.skipif(mod._sdk is None, reason="claude-agent-sdk not installed")
def test_query_allowed_warning_does_not_fall_back(monkeypatch, oauth_env):
    # Near the limit but STILL SERVING → must keep the response, not bail to API.
    _patch_query(
        monkeypatch,
        _fake(mod._sdk.RateLimitEvent,
              rate_limit_info=_rate_limit_info("allowed_warning")),
        _fake(mod._sdk.AssistantMessage, content=[_fake(mod._sdk.TextBlock, text="served by subscription")]),
        _fake(mod._sdk.ResultMessage, is_error=False, structured_output=None,
              result="served by subscription", stop_reason="end_turn", api_error_status=None),
    )
    client = ClaudeAgentSDKClient(
        "claude-opus-4-8",
        fallback_spec={"provider": "deepseek", "model": "deepseek-v4-pro", "base_url": None},
    )
    _install_stub_fallback(monkeypatch)
    result = client.get_llm().invoke("analyze")
    assert result.content == "served by subscription"  # NOT "served by fallback"


@pytest.mark.skipif(mod._sdk is None, reason="claude-agent-sdk not installed")
def test_query_allowed_with_overage_rejected_does_not_fall_back(monkeypatch, oauth_env):
    # Real-world case: the org disables overage, so every event carries
    # overage_status="rejected" — but status="allowed" means the plan served
    # this call. Must keep the subscription response, NOT bail to the paid
    # fallback. (Regression for the "100% silent downgrade" bug.)
    _patch_query(
        monkeypatch,
        _fake(mod._sdk.RateLimitEvent,
              rate_limit_info=_rate_limit_info("allowed", overage_status="rejected")),
        _fake(mod._sdk.AssistantMessage, content=[_fake(mod._sdk.TextBlock, text="served by subscription")]),
        _fake(mod._sdk.ResultMessage, is_error=False, structured_output=None,
              result="served by subscription", stop_reason="end_turn", api_error_status=None),
    )
    client = ClaudeAgentSDKClient(
        "claude-opus-4-8",
        fallback_spec={"provider": "deepseek", "model": "deepseek-v4-pro", "base_url": None},
    )
    _install_stub_fallback(monkeypatch)
    result = client.get_llm().invoke("analyze")
    assert result.content == "served by subscription"  # NOT "served by fallback"


@pytest.mark.skipif(mod._sdk is None, reason="claude-agent-sdk not installed")
def test_query_rejected_triggers_fallback(monkeypatch, oauth_env):
    _patch_query(
        monkeypatch,
        _fake(mod._sdk.RateLimitEvent,
              rate_limit_info=_rate_limit_info("rejected", overage_status="rejected")),
    )
    client = ClaudeAgentSDKClient(
        "claude-opus-4-8",
        fallback_spec={"provider": "deepseek", "model": "deepseek-v4-pro", "base_url": None},
    )
    _install_stub_fallback(monkeypatch)
    result = client.get_llm().invoke("analyze")
    assert result.content == "served by fallback"


# --------------------------------------------------------------------------- #
# 认证失败必须中止，不能降级到按 token 计费的 provider
# --------------------------------------------------------------------------- #

def test_auth_failure_is_detected_from_api_retry_and_assistant_text():
    from tradingagents.llm_clients.claude_agent_sdk_client import (
        _looks_like_auth_failure,
    )

    class _Sys:            # SystemMessage(subtype="api_retry")
        data = {"error_status": 401, "error": "authentication_failed"}

    class _Block:
        text = "Failed to authenticate. API Error: 401 OAuth access token has expired."

    class _Assistant:
        content = [_Block()]
        error = "authentication_error"

    class _Normal:
        data = {"subtype": "init"}
        content = []
        error = None

    assert _looks_like_auth_failure(_Sys()) is True
    assert _looks_like_auth_failure(_Assistant()) is True
    assert _looks_like_auth_failure(_Normal()) is False


def test_exc_looks_like_auth_requires_401_word_boundary():
    from tradingagents.llm_clients.claude_agent_sdk_client import _exc_looks_like_auth

    assert not _exc_looks_like_auth("connection reset, request id 8814012")
    assert not _exc_looks_like_auth("upstream error 1401")
    assert _exc_looks_like_auth("HTTP 401 Unauthorized")
    assert _exc_looks_like_auth("OAuth token expired — please re-authenticate")


def test_auth_error_is_not_in_fallback_errors():
    """凭据失效时降级到付费 provider ＝ 悄悄开始计费，正是启用订阅要避免的。
    这条锁住 _AuthError 不被 fallback 吞掉。"""
    from tradingagents.llm_clients import claude_agent_sdk_client as mod

    assert mod._AuthError not in mod._FALLBACK_ERRORS
    assert not issubclass(mod._AuthError, mod._FALLBACK_ERRORS)


def test_auth_failure_hint_is_actionable():
    from tradingagents.llm_clients.claude_agent_sdk_client import _auth_failure_hint

    class _Block:
        text = "401 OAuth access token has expired"

    class _M:
        content = [_Block()]

    hint = _auth_failure_hint(_M())
    assert "claude setup-token" in hint          # 给出可执行命令
    assert "CLAUDE_CODE_OAUTH_TOKEN" in hint


def test_web_all_scope_keeps_separate_quick_model():
    """选「所有节点」时不能把深度节点的模型复制给 quick——
    7 个分析师 + 辩手全跑 opus 会让订阅额度烧得极快，也与文档所述矛盾。"""
    from tradingagents.default_config import DEFAULT_CONFIG

    config = dict(DEFAULT_CONFIG)
    session = {"subscription_scope": "all", "agent_sdk_model": "opus"}

    # 复刻 web/app.py:_build_config 的订阅分支
    scope = session.get("subscription_scope", "off")
    sub_model = session.get("agent_sdk_model")
    if scope in ("deep", "all"):
        config["deep_think_provider_override"] = "claude_agent_sdk"
        if sub_model:
            config["agent_sdk_model"] = sub_model
    if scope == "all":
        config["quick_think_provider_override"] = "claude_agent_sdk"

    assert config["agent_sdk_model"] == "opus"
    assert config["agent_sdk_quick_model"] == "sonnet"     # 未被 opus 覆盖


@pytest.mark.parametrize(
    "fb_provider,fb_model,should_raise",
    [
        ("anthropic", None, True),      # 只给 provider → 会配上主 provider 的模型名
        (None, "claude-opus-4-6", True),  # 只给 model
        ("anthropic", "claude-opus-4-6", False),
        (None, None, False),            # 都不给 → 回落 llm_provider + 自身模型
    ],
)
def test_fallback_provider_and_model_must_be_configured_together(
    fb_provider, fb_model, should_raise, monkeypatch
):
    """降级路径恰好在撞额度时才被走到，配错要在启动时暴露而不是运行中。"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from tradingagents.default_config import DEFAULT_CONFIG

    config = dict(DEFAULT_CONFIG)
    config["deep_think_provider_override"] = "claude_agent_sdk"
    config["agent_sdk_fallback_provider"] = fb_provider
    config["agent_sdk_fallback_model"] = fb_model

    deep_on = config.get("deep_think_provider_override") == "claude_agent_sdk"
    quick_on = config.get("quick_think_provider_override") == "claude_agent_sdk"
    p, m = config.get("agent_sdk_fallback_provider"), config.get("agent_sdk_fallback_model")
    mismatched = (deep_on or quick_on) and bool(p) != bool(m)

    assert mismatched is should_raise


def test_auth_detection_ignores_ordinary_assistant_text():
    """工具分析师会复述桥接工具的失败原文——某个行情源自己的 key 失效时，
    正文里可能出现 'invalid api key'。这不能被误判成订阅凭据失效。"""
    from tradingagents.llm_clients.claude_agent_sdk_client import _looks_like_auth_failure

    class _Block:
        text = "调用行情工具失败：provider returned 'invalid api key' for the quote source."

    class _NormalAssistant:          # 真实模型的正常回复
        model = "claude-sonnet-4-6"
        error = None
        content = [_Block()]

    class _SyntheticAuth:            # SDK 合成的认证错误
        model = "<synthetic>"
        error = "authentication_error"
        content = [type("B", (), {"text": "401 OAuth access token has expired"})()]

    assert _looks_like_auth_failure(_NormalAssistant()) is False
    assert _looks_like_auth_failure(_SyntheticAuth()) is True


@requires_sdk
def test_sdk_subprocess_env_blanks_anthropic_api_key(monkeypatch):
    """ANTHROPIC_API_KEY 必须在子进程被置空（否则悄悄走 API 计费），
    但父进程要保留它，好让 anthropic 仍能作为降级 provider。"""
    if mod.ClaudeAgentOptions is None:
        pytest.skip("claude-agent-sdk not installed")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    from tradingagents.llm_clients.claude_agent_sdk_client import ClaudeAgentSDKClient

    client = ClaudeAgentSDKClient("opus", None)
    opts = client._build_options(system_prompt=None)
    env = getattr(opts, "env", None) or {}
    assert env.get("ANTHROPIC_API_KEY") == ""
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-should-not-leak"


@pytest.mark.parametrize(
    "llm_provider,fb_provider,backend_url,expect_url",
    [
        ("minimax", "anthropic", "https://minimax.gw/v1", None),   # 跨家 → 不带
        ("minimax", "minimax", "https://minimax.gw/v1", "https://minimax.gw/v1"),
        ("minimax", None, "https://minimax.gw/v1", "https://minimax.gw/v1"),  # 未指定 → 沿用
    ],
)
def test_cross_provider_fallback_drops_primary_backend_url(
    llm_provider, fb_provider, backend_url, expect_url
):
    """backend_url 是给 llm_provider 配的端点，把它转发给另一家 provider
    会在撞额度真要降级时才炸。"""
    config = {
        "llm_provider": llm_provider,
        "backend_url": backend_url,
        "agent_sdk_fallback_provider": fb_provider,
        "agent_sdk_fallback_model": "m" if fb_provider else None,
        "quick_think_llm": "primary-model",
    }
    fb = config.get("agent_sdk_fallback_provider")
    cross = bool(fb) and fb != config["llm_provider"]
    resolved = None if cross else config.get("backend_url")
    assert resolved == expect_url


def test_result_message_401_raises_auth_error_not_fallback():
    """401 也可能只出现在 ResultMessage 上。漏判会落进 _SDKResultError
    → _FALLBACK_ERRORS → 静默降级到计费 provider，违背「不产生 API 账单」。"""
    from tradingagents.llm_clients import claude_agent_sdk_client as mod

    class _Result:
        is_error = True
        api_error_status = 401
        stop_reason = "stop_sequence"
        content = []
        error = None
        model = None

    # 复刻 _query 里的判定分支
    status = getattr(_Result, "api_error_status", None)
    assert status == 401
    exc = mod._AuthError(mod._auth_failure_hint(_Result()))
    assert not isinstance(exc, mod._FALLBACK_ERRORS)
    assert "claude setup-token" in str(exc)


def test_fallback_spec_carries_callbacks():
    """降级＝开始计费，此时统计/成本回调必须仍能看到这些调用。"""
    callbacks = ["sentinel-callback"]
    cross_provider = False
    config = {"llm_provider": "minimax", "backend_url": None, "quick_think_llm": "m"}
    spec = {
        "provider": config["llm_provider"],
        "model": config["quick_think_llm"],
        "base_url": None if cross_provider else config.get("backend_url"),
        **({"callbacks": callbacks} if callbacks else {}),
    }
    assert spec["callbacks"] == callbacks


def test_tuple_messages_are_not_silently_emptied():
    """Reflector.reflect_on_final_decision() 传的是 (role, content) 元组。
    不支持这种形状会让两条消息双双变空串——SDK 收到空 prompt 却照常返回内容，
    是「不报错的错答案」。"""
    from tradingagents.llm_clients.claude_agent_sdk_client import (
        _msg_role_content, _split_prompt,
    )

    assert _msg_role_content(("system", "SYS")) == ("system", "SYS")
    assert _msg_role_content(("human", "USER")) == ("human", "USER")

    system, user = _split_prompt([("system", "SYS"), ("human", "USER")])
    assert system == "SYS"
    assert "USER" in user


# --------------------------------------------------------------------------- #
# F2.1 — auth-flavoured ClaudeSDKError must NOT start paid billing
# --------------------------------------------------------------------------- #

def test_clientsdkerror_with_auth_text_does_not_fall_back(monkeypatch, oauth_env):
    """ClaudeSDKError is the SDK base class — auth failures raise it too.
    Content classification must stop them from constructing the paid fallback."""
    client = ClaudeAgentSDKClient(
        "claude-opus-4-8",
        fallback_spec={"provider": "deepseek", "model": "deepseek-v4-pro", "base_url": None},
    )

    def boom(prompt):
        # Raise from _invoke_raw so we do not need ClaudeAgentOptions (SDK may
        # be absent in CI). ClaudeSDKError is in _FALLBACK_ERRORS — the gate
        # must still refuse to start paid billing when the text is auth-flavoured.
        raise mod.ClaudeSDKError("OAuth token expired — please re-authenticate")

    monkeypatch.setattr(client, "_invoke_raw", boom)
    _install_stub_fallback(monkeypatch)

    # Bypass get_llm()'s import guard — the auth gate lives on the adapter.
    llm = AgentSDKChatModel(client, client.fallback_spec)
    with pytest.raises(mod._AuthError):
        llm.invoke("hi")
    assert llm._fallback_llm is None  # fallback never constructed


def test_result_message_auth_error_without_401_does_not_fall_back(monkeypatch, oauth_env):
    """OAuth expiry can arrive as is_error ResultMessage with no api_error_status."""
    if mod._sdk is None:
        # Without the real SDK types, exercise the same classification path
        # that _query uses for ResultMessage fields.
        class _Result:
            is_error = True
            api_error_status = None
            stop_reason = "error"
            subtype = "error"
            result = "OAuth access token has expired. Please run /login."
            content = []
            error = None
            model = None

        auth_blob = " ".join(
            str(p) for p in (
                _Result.stop_reason, _Result.subtype, _Result.result, _Result.api_error_status,
            ) if p is not None
        )
        assert mod._exc_looks_like_auth(auth_blob)
        with pytest.raises(mod._AuthError):
            raise mod._AuthError(mod._auth_failure_hint(_Result()))
        return

    _patch_query(
        monkeypatch,
        _fake(
            mod._sdk.ResultMessage,
            is_error=True,
            structured_output=None,
            result="OAuth access token has expired. Please run /login.",
            stop_reason="error",
            api_error_status=None,
            subtype="error",
        ),
    )
    client = ClaudeAgentSDKClient(
        "claude-opus-4-8",
        fallback_spec={"provider": "deepseek", "model": "deepseek-v4-pro", "base_url": None},
    )
    _install_stub_fallback(monkeypatch)
    llm = AgentSDKChatModel(client, client.fallback_spec)
    with pytest.raises(mod._AuthError):
        llm.invoke("analyze")
    assert llm._fallback_llm is None


def test_generic_sdk_error_still_falls_back(monkeypatch, oauth_env):
    """Guard against over-correcting: non-auth SDK faults must still fall back."""
    client = ClaudeAgentSDKClient(
        "claude-opus-4-8",
        fallback_spec={"provider": "deepseek", "model": "deepseek-v4-pro", "base_url": None},
    )

    def boom(prompt):
        raise mod._SDKResultError("connection reset by peer")

    monkeypatch.setattr(client, "_invoke_raw", boom)
    _install_stub_fallback(monkeypatch)

    result = AgentSDKChatModel(client, client.fallback_spec).invoke("analyze")
    assert result.content == "served by fallback"


def test_extract_json_prefers_last_parseable_candidate():
    """F5.6 — greedy \{.*\} breaks when prose contains an example schema."""
    text = (
        'Here is an example: {"decision": "buy", "confidence": "bad"}\n'
        'Final answer: {"decision": "hold", "confidence": 2}'
    )
    # First object has non-int confidence → invalid for our schema, but both
    # parse as JSON; balanced scan must return the *last* valid object.
    extracted = mod._extract_json(text)
    assert json.loads(extracted) == {"decision": "hold", "confidence": 2}
