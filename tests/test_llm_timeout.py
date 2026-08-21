"""llm_timeout / llm_max_retries / llm_retry_delay 透传与应用层重试回归测试。

风险辩论节点内同步 llm.invoke() 曾缺少超时保护：provider 请求挂起时节点永不返回，
进程 alive 但静默卡死。补丁分两层：
- SDK 层：timeout 兜底挂起，max_retries 恒 0（重试交给应用层）。
- 应用层：openai_client.invoke 捕获 5xx，按指数退避重试（5s, 10s, 20s...）。
"""

import time as _time
from unittest.mock import Mock

import pytest
from openai import InternalServerError, APITimeoutError

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph import trading_graph as tg
from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI, OpenAIClient


def _graph_with(config):
    graph = tg.TradingAgentsGraph.__new__(tg.TradingAgentsGraph)
    graph.config = config
    return graph


def _server_error(status=503):
    return InternalServerError(f"{status}", response=Mock(status_code=status), body=None)


def _timeout_error():
    return APITimeoutError(request=Mock())


@pytest.mark.unit
class TestProviderKwargs:
    def test_timeout_forwarded_and_sdk_retries_zeroed(self):
        g = _graph_with({"llm_timeout": 120, "llm_max_retries": 2, "llm_retry_delay": 5})
        kw = g._get_provider_kwargs()
        assert kw["timeout"] == 120
        assert kw["max_retries"] == 0        # SDK 层恒 0，重试交给应用层
        assert kw["app_retries"] == 2        # 应用层重试次数
        assert kw["app_retry_delay"] == 5    # 初始退避（秒）

    def test_app_retries_zero_is_not_dropped(self):
        # app_retries=0（不重试）是合法值，不能因为 falsy 被默认值覆盖。
        g = _graph_with({"llm_max_retries": 0})
        assert g._get_provider_kwargs()["app_retries"] == 0

    def test_defaults_when_keys_absent(self):
        g = _graph_with({"max_tokens": 8000})
        kw = g._get_provider_kwargs()
        assert kw["max_retries"] == 0        # 恒 0
        assert kw["app_retries"] == 3        # 默认 3
        assert kw["app_retry_delay"] == 5    # 默认 5


@pytest.mark.unit
class TestRetryParamsReachClient:
    def test_retry_params_reach_chatopenai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        client = OpenAIClient(
            "m", base_url="https://relay.example/v1", provider="openai_compatible",
            timeout=120, max_retries=0, app_retries=2, app_retry_delay=5,
        )
        llm = client.get_llm()
        assert llm.request_timeout == 120.0   # langchain 内部字段名
        assert llm.max_retries == 0           # SDK 层不重试
        assert llm.app_retries == 2
        assert llm.app_retry_delay == 5.0


@pytest.mark.unit
class TestAppLayerRetry:
    def test_retries_on_5xx_then_succeeds(self, monkeypatch):
        from langchain_openai import ChatOpenAI

        calls = {"n": 0}

        def fake_invoke(self, input, config=None, **kw):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise _server_error()
            return Mock(content="ok")

        monkeypatch.setattr(ChatOpenAI, "invoke", fake_invoke)
        monkeypatch.setattr(
            "tradingagents.llm_clients.openai_client.normalize_content", lambda r: "normalized"
        )
        monkeypatch.setattr(
            "tradingagents.llm_clients.openai_client.warn_if_truncated", lambda *a, **k: None
        )
        monkeypatch.setattr(_time, "sleep", lambda s: None)

        llm = NormalizedChatOpenAI(model="m", api_key="k", app_retries=2, app_retry_delay=5)
        assert llm.invoke("hi") == "normalized"
        assert calls["n"] == 3               # 2 次 5xx + 1 次成功

    def test_raises_after_retries_exhausted(self, monkeypatch):
        from langchain_openai import ChatOpenAI

        def fake_invoke(self, input, config=None, **kw):
            raise _server_error()

        monkeypatch.setattr(ChatOpenAI, "invoke", fake_invoke)
        monkeypatch.setattr(_time, "sleep", lambda s: None)

        llm = NormalizedChatOpenAI(model="m", api_key="k", app_retries=2, app_retry_delay=5)
        with pytest.raises(InternalServerError):
            llm.invoke("hi")

    def test_exponential_backoff_delays(self, monkeypatch):
        from langchain_openai import ChatOpenAI

        delays = []

        def fake_invoke(self, input, config=None, **kw):
            raise _server_error()

        monkeypatch.setattr(ChatOpenAI, "invoke", fake_invoke)
        monkeypatch.setattr(_time, "sleep", lambda s: delays.append(s))

        llm = NormalizedChatOpenAI(model="m", api_key="k", app_retries=2, app_retry_delay=5)
        with pytest.raises(InternalServerError):
            llm.invoke("hi")
        # 指数退避：第 1 次重试前 5s，第 2 次重试前 10s
        assert delays == [5.0, 10.0]

    def test_retries_on_timeout_then_succeeds(self, monkeypatch):
        from langchain_openai import ChatOpenAI

        calls = {"n": 0}

        def fake_invoke(self, input, config=None, **kw):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise _timeout_error()
            return Mock(content="ok")

        monkeypatch.setattr(ChatOpenAI, "invoke", fake_invoke)
        monkeypatch.setattr(
            "tradingagents.llm_clients.openai_client.normalize_content", lambda r: "normalized"
        )
        monkeypatch.setattr(
            "tradingagents.llm_clients.openai_client.warn_if_truncated", lambda *a, **k: None
        )
        monkeypatch.setattr(_time, "sleep", lambda s: None)

        llm = NormalizedChatOpenAI(model="m", api_key="k", app_retries=2, app_retry_delay=5)
        assert llm.invoke("hi") == "normalized"
        assert calls["n"] == 3               # 2 次超时 + 1 次成功

    def test_raises_after_timeout_retries_exhausted(self, monkeypatch):
        from langchain_openai import ChatOpenAI

        def fake_invoke(self, input, config=None, **kw):
            raise _timeout_error()

        monkeypatch.setattr(ChatOpenAI, "invoke", fake_invoke)
        monkeypatch.setattr(_time, "sleep", lambda s: None)

        llm = NormalizedChatOpenAI(model="m", api_key="k", app_retries=2, app_retry_delay=5)
        with pytest.raises(APITimeoutError):
            llm.invoke("hi")


@pytest.mark.unit
class TestDefaultConfig:
    def test_default_config_ships_retry_settings(self):
        assert DEFAULT_CONFIG["llm_timeout"] == 150
        assert DEFAULT_CONFIG["llm_max_retries"] == 3
        assert DEFAULT_CONFIG["llm_retry_delay"] == 5

    def test_max_tokens_default_is_none_without_env(self):
        # 未显式设置 TRADINGAGENTS_MAX_TOKENS 时，max_tokens 应为 None（用
        # provider 自己的默认值），不能默认 8192。全局 8192 会把能上 64000 的
        # Claude 等模型错误地砍到 8192，并加剧 #91“报告写到一半结束”。
        assert DEFAULT_CONFIG["max_tokens"] is None
