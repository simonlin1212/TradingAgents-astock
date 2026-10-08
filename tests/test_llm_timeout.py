"""llm_timeout / llm_max_retries / llm_retry_delay 透传与应用层重试回归测试。

风险辩论节点内同步 llm.invoke() 曾缺少超时保护：provider 请求挂起时节点永不返回，
进程 alive 但静默卡死。补丁分两层：
- SDK 层：timeout 兜底挂起，max_retries 恒 0（重试交给应用层）。
- 应用层：openai_client.invoke 捕获 5xx，按指数退避重试（5s, 10s, 20s...）。
"""

import time as _time
from unittest.mock import Mock, patch

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI

from tradingagents.dataflows import config as _dataflows_config
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph import trading_graph as tg
from tradingagents.llm_clients.factory import create_llm_client as real_create_llm_client
from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI, OpenAIClient

# 超时/重试三件套 + timeout，四个键一起看：少看一个就会漏掉"只修了一半"。
_RESILIENCE_KEYS = ("timeout", "max_retries", "app_retries", "app_retry_delay")

# 状态码 → SDK 真正会抛的那个异常类型。自己 Mock(status_code=...) 造不出
# 408 是裸 APIStatusError、409 是 ConflictError 这种真实形状，而按类型判还是按
# 状态码判恰恰是这里的关键分歧，所以走 SDK 自己的映射函数。
_STATUS_ERROR_SOURCE = OpenAI(api_key="test-key-not-used")


def _graph_with(config):
    graph = tg.TradingAgentsGraph.__new__(tg.TradingAgentsGraph)
    graph.config = config
    return graph


def _status_error(code):
    return _STATUS_ERROR_SOURCE._make_status_error_from_response(
        httpx.Response(code, request=httpx.Request("POST", "https://example.invalid/v1"))
    )


def _server_error(status=503):
    return InternalServerError(f"{status}", response=Mock(status_code=status), body=None)


def _timeout_error():
    return APITimeoutError(request=Mock())


@pytest.fixture
def clean_global_config():
    """`TradingAgentsGraph.__init__` 会 set_config() 改全局配置（原地 update，不可逆）。

    不还原的话，本文件建过图之后，同一次 pytest 里后面的用例会读到被污染的
    `get_config()` —— 那种失败看起来像"另一个模块坏了"，最难查。
    """
    saved = None if _dataflows_config._config is None else dict(_dataflows_config._config)
    try:
        yield
    finally:
        _dataflows_config._config = saved


def _build_graph(tmp_path, overrides, selected_analysts=("market",)):
    """真的把 `TradingAgentsGraph` 建出来，抓每一次 `create_llm_client` 的入参。

    返回 ``(每一次 create_llm_client 的入参列表, fallback_spec)``。

    第一个返回值包含**所有**客户端，订阅客户端（provider="claude_agent_sdk"）也在内
    ——它本身也需要超时，而 `fallback_spec` 里那份只在降级**之后**才生效。
    各用例一律按 provider / model 过滤自己关心的那条。

    🔴 不在测试里照抄一遍那份 kwargs —— 抄出来的断言改真代码也不会红，等于没测。
       仓库里就有一条那样的（test_agent_sdk_provider.test_fallback_spec_carries_callbacks
       自己把 spec 字典拼了一遍）。这里走的是生产路径本身。
    """
    seen = {"main": [], "fallback": None}

    def fake_create(**kw):
        seen["main"].append(kw)
        if "fallback_spec" in kw:
            seen["fallback"] = kw["fallback_spec"]
        return Mock(get_llm=Mock(return_value=Mock()))

    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
    })
    config.update(overrides)
    with patch.object(tg, "create_llm_client", fake_create):
        tg.TradingAgentsGraph(
            selected_analysts=list(selected_analysts), debug=False, config=config
        )
    return seen["main"], seen["fallback"]


@pytest.mark.unit
class TestProviderKwargs:
    def test_timeout_forwarded_and_sdk_retries_zeroed(self):
        g = _graph_with({"llm_provider": "openai", "llm_timeout": 120, "llm_max_retries": 2, "llm_retry_delay": 5})
        kw = g._get_provider_kwargs()
        assert kw["timeout"] == 120
        assert kw["max_retries"] == 0        # SDK 层恒 0，重试交给应用层
        assert kw["app_retries"] == 2        # 应用层重试次数
        assert kw["app_retry_delay"] == 5    # 初始退避（秒）

    def test_app_retries_zero_is_not_dropped(self):
        # app_retries=0（不重试）是合法值，不能因为 falsy 被默认值覆盖。
        g = _graph_with({"llm_provider": "openai", "llm_max_retries": 0})
        assert g._get_provider_kwargs()["app_retries"] == 0

    def test_defaults_when_keys_absent(self):
        g = _graph_with({"llm_provider": "openai"})
        kw = g._get_provider_kwargs()
        assert kw["max_retries"] == 0        # 恒 0
        assert kw["app_retries"] == 3        # 默认 3
        assert kw["app_retry_delay"] == 5    # 默认 5

    def test_anthropic_and_google_do_not_zero_max_retries(self):
        # 针对 PR #100 review 回归防护：只有走 OpenAIClient 的 provider 才会
        # 关闭 SDK 重试并注入应用层退避参数。Anthropic / Google 等原生 SDK 具有
        # 自己的重试逻辑，不能注入 max_retries=0 破坏其弹性，也不能注入未使用的 app_retries。
        #
        # 🔴 但 `timeout` **必须照给**，这两件事是分开的。
        #    "另几家 SDK 自带 600 秒读超时" 只对**裸 SDK** 成立，本项目一次都没
        #    走过裸 SDK：langchain 的三个封装层在用户没给超时时都把 None
        #    **显式**传下去，httpx 收到显式 None = 不设超时。实测构造出来的对象：
        #      ChatAnthropic()          -> sdk client.timeout=None（无限等）
        #      ChatAnthropic(timeout=150) -> 150.0
        #      AzureChatOpenAI 同形状。
        #    不给超时就是给它们重开 #100 那个"进程活着、零输出、永不返回"的洞。
        for provider in ("anthropic", "google", "azure", "claude_agent_sdk"):
            g = _graph_with({"llm_provider": provider, "llm_timeout": 120})
            kw = g._get_provider_kwargs()
            assert kw.get("timeout") == 120, f"{provider} 少了超时 = 可能永久挂起"
            assert "max_retries" not in kw
            assert "app_retries" not in kw
            assert "app_retry_delay" not in kw

    def test_resilience_kwargs_normalizes_its_own_input(self):
        # `_resilience_kwargs` 是三个调用点共用的判据，它**自己**归一化入参，
        # 这样第四个调用点不必记得先 strip/lower。三个现有调用点都已各自归一化
        # （它们还要拿归一化结果去比 base_url、算缓存键），所以这条契约只能在
        # 这一层直接钉，否则它是一段谁也证伪不了的代码。
        g = _graph_with({"llm_provider": "anthropic", "llm_timeout": 120})
        for raw in (" DeepSeek ", "DEEPSEEK", "deepseek\n"):
            assert g._resilience_kwargs(raw)["max_retries"] == 0, raw
        for raw in (" Anthropic ", None, "", 123):
            assert "max_retries" not in g._resilience_kwargs(raw), raw

    def test_provider_comparison_is_case_and_space_insensitive(self):
        # 用户把 provider 写成 "DeepSeek" / " deepseek " 是常事（README 里就写着
        # DeepSeek）。大小写敏感的比较会让这一整套韧性参数**静默**不生效。
        for spelling in ("DeepSeek", " deepseek ", "DEEPSEEK"):
            kw = _graph_with({"llm_provider": spelling, "llm_timeout": 120})._get_provider_kwargs()
            assert kw["max_retries"] == 0, f"{spelling!r} 没被认成 OpenAI 兼容 provider"
            assert kw["app_retries"] == 3


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
class TestRetryCoversWhatTheSdkUsedToRetry:
    """SDK 层 max_retries 被置 0 之后，应用层必须接住 SDK 原本会重试的那些错误。

    SDK 的可重试集合实测是 408 / 409 / 429 / >=500 + 连接类异常
    （openai/_base_client.py::_should_retry）。少接一类，这一版对用户就是**净损失**：
    从前 SDK 会重试 2 次，现在第一次就炸。
    """

    def _attempts(self, monkeypatch, exc_factory, app_retries=2):
        from langchain_openai import ChatOpenAI

        calls = {"n": 0}

        def fake_invoke(self, input, config=None, **kw):
            calls["n"] += 1
            raise exc_factory()

        monkeypatch.setattr(ChatOpenAI, "invoke", fake_invoke)
        monkeypatch.setattr(_time, "sleep", lambda s: None)
        llm = NormalizedChatOpenAI(
            model="m", api_key="k", app_retries=app_retries, app_retry_delay=5
        )
        with pytest.raises(Exception):
            llm.invoke("hi")
        return calls["n"]

    @pytest.mark.parametrize("code", [408, 409, 429, 500, 503])
    def test_sdk_retryable_status_codes_are_retried(self, monkeypatch, code):
        # 429 最要紧：RateLimitError **不是** InternalServerError 的子类
        # （实测 issubclass=False），只捕 5xx 的话高峰期一个 429 就让整轮分析当场死掉。
        # 408 / 409 没有专属异常类型（408 是裸 APIStatusError、409 是 ConflictError），
        # 所以实现必须按 status_code 判 —— 按类型判就会漏掉 408。
        assert self._attempts(monkeypatch, lambda: _status_error(code)) == 3

    def test_connection_error_is_retried(self, monkeypatch):
        # 连接被重置：一轮几十次调用里不算罕见，SDK 从前也会重试。
        assert self._attempts(monkeypatch, lambda: APIConnectionError(request=Mock())) == 3

    def test_timeout_still_retried_via_parent_class(self, monkeypatch):
        # APITimeoutError 是 APIConnectionError 的子类，捕父类即覆盖它。
        # 这条钉住"为了少列一个类型而漏掉读超时"不会发生。
        assert self._attempts(monkeypatch, _timeout_error) == 3

    @pytest.mark.parametrize("code", [400, 401, 404, 422])
    def test_non_retryable_api_errors_raise_on_first_attempt(self, monkeypatch, code):
        # 🔴 阴性对照，且是**真的 OpenAI 状态错误**（都是 APIStatusError 的子类）。
        #    用 ValueError 当阴性对照杀不掉"干脆 except APIStatusError 一把梭"这个
        #    变异 —— 而那个变异会让"你的 key 不对"也要干等三轮退避才报出来。
        assert self._attempts(monkeypatch, lambda: _status_error(code)) == 1

    def test_negative_app_retries_cannot_return_none(self, monkeypatch):
        # app_retries 是普通 int 字段、没有下界。有人按"-1 = 无限"的惯例去配时，
        # range(0) 让循环一次都不执行 —— 旧代码在这里 return None，调用方会在很远
        # 的地方炸在 `result.tool_calls` 上，根因完全看不出来。
        from langchain_openai import ChatOpenAI

        monkeypatch.setattr(ChatOpenAI, "invoke", lambda self, i, c=None, **k: Mock(content="ok"))
        monkeypatch.setattr(
            "tradingagents.llm_clients.openai_client.normalize_content", lambda r: "normalized"
        )
        monkeypatch.setattr(
            "tradingagents.llm_clients.openai_client.warn_if_truncated", lambda *a, **k: None
        )
        llm = NormalizedChatOpenAI(model="m", api_key="k", app_retries=-1, app_retry_delay=5)
        assert llm.invoke("hi") == "normalized", "负数要夹到 0（仍执行一次），不能返回 None"


@pytest.mark.unit
@pytest.mark.usefixtures("clean_global_config")
class TestResilienceFollowsTargetProvider:
    """超时/重试按**目标 provider** 算，不是共享 llm_kwargs 的一个属性。

    这份 kwargs 有三个消费方（主客户端 / 订阅降级 fallback_spec / role_llms），
    每个都可能指向不同的 provider。按 `llm_provider` 一刀切，必然有两个消费方拿错。
    下面每条都走真实构造路径。
    """

    def test_subscription_client_itself_carries_timeout(self, tmp_path):
        # v0.5.19 只给**降级**客户端带了超时，订阅**主路径**自己一个都没有 ——
        # 而挂死恰恰发生在降级之前：Agent SDK 的子进程卡住，async for 永远悬着。
        # 下面一并做阴性对照：订阅客户端不走 OpenAIClient，那三个应用层重试键
        # 它根本不读，注入进去只会污染 **kwargs。
        main, _ = _build_graph(tmp_path, {
            "llm_provider": "deepseek",
            "deep_think_provider_override": "claude_agent_sdk",
            "quick_think_provider_override": "claude_agent_sdk",
            "agent_sdk_fallback_provider": "deepseek",
            "agent_sdk_fallback_model": "deepseek-chat",
            "llm_timeout": 150, "llm_max_retries": 3, "llm_retry_delay": 5,
        })
        sdk_clients = [kw for kw in main if kw["provider"] == "claude_agent_sdk"]
        assert len(sdk_clients) == 2, (
            f"deep+quick 都开了订阅，应建两个订阅客户端：{[k['provider'] for k in main]}"
        )
        for kw in sdk_clients:
            assert kw["timeout"] == 150, "订阅主路径没拿到 llm_timeout ⇒ 卡住就永不返回"
            for key in ("max_retries", "app_retries", "app_retry_delay"):
                assert key not in kw, f"订阅客户端不该带 {key}：{kw.get(key)}"

    def test_openai_compatible_fallback_carries_timeout_and_retries(self, tmp_path):
        # 降级是**撞额度那一刻**才走到的路径，目标往往就是 OpenAI 兼容网关 ——
        # 正是"显式 None ⇒ 永不超时"那个洞所在。漏带 = #100 修的挂死在最需要它
        # 工作的时候原样复现。
        _, spec = _build_graph(tmp_path, {
            "llm_provider": "deepseek",
            "deep_think_provider_override": "claude_agent_sdk",
            "agent_sdk_fallback_provider": "deepseek",
            "agent_sdk_fallback_model": "deepseek-chat",
            "llm_timeout": 150, "llm_max_retries": 3, "llm_retry_delay": 5,
        })
        assert spec["timeout"] == 150
        assert spec["max_retries"] == 0
        assert spec["app_retries"] == 3
        assert spec["app_retry_delay"] == 5

    def test_anthropic_fallback_gets_timeout_but_not_retry_overrides(self, tmp_path):
        # 阴性对照 + 正向断言各一半：
        #   · timeout 要给 —— ChatAnthropic 不给超时就是显式 None ⇒ 无限等。
        #   · max_retries / app_retries 一个都不能给 —— 前者会静默关掉 Anthropic SDK
        #     自己的重试，后者它根本不读。
        _, spec = _build_graph(tmp_path, {
            "llm_provider": "deepseek",
            "deep_think_provider_override": "claude_agent_sdk",
            "agent_sdk_fallback_provider": "anthropic",
            "agent_sdk_fallback_model": "claude-sonnet-4-5-20250929",
            "llm_timeout": 150, "llm_max_retries": 3, "llm_retry_delay": 5,
        })
        assert spec["timeout"] == 150
        for key in ("max_retries", "app_retries", "app_retry_delay"):
            assert key not in spec, f"anthropic 降级不该带 {key}：{spec.get(key)}"

    def test_codex_fallback_preserves_cli_authentication(self, tmp_path):
        _, spec = _build_graph(tmp_path, {
            "llm_provider": "codex_cli",
            "deep_think_provider_override": "claude_agent_sdk",
            "codex_cli_auth_mode": "api_key",
            "codex_cli_path": "/custom/codex",
            "codex_cli_reasoning_effort": "high",
            "llm_timeout": 42,
        })
        assert spec["provider"] == "codex_cli"
        assert spec["auth_mode"] == "api_key"
        assert spec["cli_path"] == "/custom/codex"
        assert spec["reasoning_effort"] == "high"
        assert spec["timeout"] == 42

    @pytest.mark.parametrize("model", [None, ""])
    def test_explicit_codex_fallback_accepts_default_model(self, tmp_path, model):
        _, spec = _build_graph(tmp_path, {
            "llm_provider": "deepseek",
            "deep_think_provider_override": "claude_agent_sdk",
            "agent_sdk_fallback_provider": "codex_cli",
            "agent_sdk_fallback_model": model,
        })
        assert spec["provider"] == "codex_cli"
        assert spec["model"] == ""

    def test_fallback_provider_spelling_does_not_change_behaviour(self, tmp_path):
        # 全仓唯一一处**没有** .lower() 的 provider 比较就在这儿：写成 "DeepSeek"
        # 时同一家被判成跨厂商 ⇒ backend_url 被扔掉，降级请求发去官方默认端点
        # （自建网关的 key 拿去官方认证 = 401），同时韧性参数也静默不注入。
        _, spec = _build_graph(tmp_path, {
            "llm_provider": "deepseek",
            "backend_url": "https://relay.example/v1",
            "deep_think_provider_override": "claude_agent_sdk",
            "agent_sdk_fallback_provider": "DeepSeek",
            "agent_sdk_fallback_model": "deepseek-chat",
            "llm_timeout": 150,
        })
        assert spec["base_url"] == "https://relay.example/v1", "同一家却被当成跨厂商"
        assert spec["max_retries"] == 0
        assert spec["app_retries"] == 3

    def test_role_llm_on_openai_compatible_gets_app_retries_under_anthropic_main(self, tmp_path):
        # 主 anthropic + bull=deepseek：deepseek 角色的 SDK 重试会被我们置 0，
        # 所以它**必须**拿到应用层退避重试。按 llm_provider 一刀切时它一个都拿不到。
        main, _ = _build_graph(tmp_path, {
            "llm_provider": "anthropic",
            "deep_think_llm": "claude-sonnet-4-5", "quick_think_llm": "claude-sonnet-4-5",
            "llm_timeout": 150,
            "role_llms": {"bull": {"provider": "deepseek", "model": "deepseek-chat"}},
        })
        role = [kw for kw in main if kw["provider"] == "deepseek"]
        assert len(role) == 1, f"没建出 deepseek 角色模型：{[k['provider'] for k in main]}"
        assert role[0]["timeout"] == 150
        assert role[0]["max_retries"] == 0
        assert role[0]["app_retries"] == 3

    @pytest.mark.parametrize("spelling", ["DeepSeek", " DeepSeek ", "deepseek\t"])
    def test_role_llm_provider_spelling_does_not_change_behaviour(self, tmp_path, spelling):
        # role_llms 里的 provider 是**用户手写**的自由字符串，且 README 通篇写作
        # "DeepSeek"。大小写/空格敏感时这个角色会静默拿不到应用层重试，
        # 而它的 SDK 重试已经被置 0。
        main, _ = _build_graph(tmp_path, {
            "llm_provider": "anthropic",
            "deep_think_llm": "claude-sonnet-4-5", "quick_think_llm": "claude-sonnet-4-5",
            "llm_timeout": 150, "backend_url": None,
            "role_llms": {"bull": {"provider": spelling, "model": "deepseek-chat"}},
        })
        role = [kw for kw in main
                if str(kw["provider"]).strip().lower() == "deepseek"]
        assert len(role) == 1, f"没建出 deepseek 角色模型：{[k['provider'] for k in main]}"
        assert role[0]["max_retries"] == 0, f"{spelling!r} 静默拿不到韧性参数"
        assert role[0]["app_retries"] == 3

        # 🔴 上面整段 patch 掉了 create_llm_client，所以"kwargs 算对了"**不等于生产
        #    能跑通**：真工厂此前只做 .lower()，拿到 ' DeepSeek ' 会一路走到最后
        #    抛 `Unsupported LLM provider`。把捕获到的原样字符串喂给**真工厂**，
        #    这一步才是真实边界（没有它，这条用例就是假绿）。
        client = real_create_llm_client(provider=role[0]["provider"], model="deepseek-chat")
        assert type(client).__name__ == "OpenAIClient"

    def test_same_provider_spelled_differently_keeps_the_relay_endpoint(self, tmp_path):
        # 归一化口径不一致的第二个后果（比韧性参数更直接）：同一家被判成跨厂商，
        # `backend_url` 就被扔掉 —— 这个角色拿着自建网关的 key 去官方端点认证，401。
        main, _ = _build_graph(tmp_path, {
            "llm_provider": "deepseek",
            "backend_url": "https://relay.example/v1",
            "llm_timeout": 150,
            "role_llms": {"bull": {"provider": " DeepSeek ", "model": "deepseek-other"}},
        })
        role = [kw for kw in main if kw["model"] == "deepseek-other"]
        assert len(role) == 1, f"没建出该角色模型：{[k['model'] for k in main]}"
        assert role[0]["base_url"] == "https://relay.example/v1", "同一家却被当成跨厂商"

    def test_spelling_variants_of_one_provider_share_one_instance(self, tmp_path):
        # 缓存键必须和工厂的归一化口径一致：不一致时 `" DeepSeek "` 与 `"deepseek"`
        # 被当成两家，同一个 (模型, 端点) 白建第二条连接。
        main, _ = _build_graph(
            tmp_path,
            {
                "llm_provider": "deepseek", "backend_url": None, "llm_timeout": 150,
                "role_llms": {
                    "bull": {"provider": " DeepSeek ", "model": "deepseek-shared"},
                    "bear": {"provider": "deepseek", "model": "deepseek-shared"},
                },
            },
            selected_analysts=("market",),
        )
        shared = [kw for kw in main if kw["model"] == "deepseek-shared"]
        assert len(shared) == 1, f"两个角色本该复用同一个实例，实际建了 {len(shared)} 个"

    def test_role_llm_on_anthropic_keeps_its_own_sdk_retries(self, tmp_path):
        # 反方向阴性对照：主 deepseek + bull=anthropic，anthropic 角色只该拿超时。
        main, _ = _build_graph(tmp_path, {
            "llm_provider": "deepseek", "llm_timeout": 150,
            "role_llms": {"bull": {"provider": "anthropic", "model": "claude-sonnet-4-5"}},
        })
        role = [kw for kw in main if kw["provider"] == "anthropic"]
        assert len(role) == 1
        assert role[0]["timeout"] == 150
        for key in ("max_retries", "app_retries", "app_retry_delay"):
            assert key not in role[0], f"anthropic 角色不该带 {key}：{role[0].get(key)}"
        # 主 provider 那两个客户端不能被角色重算连累（共享的 llm_kwargs 被就地
        # pop 掉韧性键就会这样）。先断条数，否则一条都没匹配上时这个循环是空跑、
        # 断言等于没执行。
        mains = [kw for kw in main if kw["provider"] == "deepseek"]
        assert len(mains) == 2, f"主 provider 应建 quick+deep 两个：{len(mains)}"
        for kw in mains:
            assert kw["max_retries"] == 0 and kw["app_retries"] == 3


@pytest.mark.unit
class TestFactoryNormalizesProvider:
    """`create_llm_client` 是 provider 字符串的**中央边界** —— 归一化只此一处。

    trading_graph 那几处判据（base_url / 专属参数 / 韧性参数 / 缓存键）都按
    strip().lower() 算；工厂如果只 .lower()，就会出现"参数全算对了、客户端却
    建不出来"：`role_llms: {"bull": {"provider": " DeepSeek "}}` 直接 ValueError。
    """

    @pytest.mark.parametrize("spelling", ["deepseek", "DeepSeek", " DeepSeek ", "\tdeepseek\n"])
    def test_openai_compatible_spellings_all_build(self, spelling):
        assert type(real_create_llm_client(
            provider=spelling, model="deepseek-chat")).__name__ == "OpenAIClient"

    @pytest.mark.parametrize("spelling", ["anthropic", "Anthropic", " anthropic "])
    def test_non_openai_spellings_route_to_their_own_client(self, spelling):
        # 归一化不能只照顾 OpenAI 兼容那一支：路由分支用的是同一个变量。
        assert type(real_create_llm_client(
            provider=spelling, model="claude-sonnet-4-5")).__name__ == "AnthropicClient"

    @pytest.mark.parametrize("spelling", ["deepsek", "  ", "", "gpt"])
    def test_genuinely_unknown_provider_still_raises(self, spelling):
        # 阴性对照：strip 只去空白，不能顺手把拼错的 provider 也"救"成可用，
        # 否则用户写错一个字母会静默落到某个默认分支上。
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            real_create_llm_client(provider=spelling, model="m")


@pytest.mark.unit
class TestStreamingKeepsUsageStats:
    def test_opencode_streaming_enables_stream_usage(self, monkeypatch):
        # 静默失败：流式下 langchain 不自带 usage_metadata，而它的自动开启逻辑在
        # 设了 openai_api_base 时直接跳过 —— opencode 这条路恒定设了 base_url。
        # 不显式开 stream_usage，整轮跑完统计面板写 tokens_in=0 / tokens_out=0，
        # 看起来像"这次没花钱"，零告警。
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        llm = OpenAIClient("deepseek-chat", base_url="https://opencode.ai/zen/go/v1",
                           provider="deepseek", timeout=150).get_llm()
        assert llm.streaming is True
        # 判据挂在真正决定"带不带用量"的那个方法上，不只挂字段存在。
        assert llm._should_stream_usage(None) is True

    def test_explicit_stream_usage_false_is_respected(self, monkeypatch):
        # setdefault 的逃生口要真的存在：stream_usage 已进 _PASSTHROUGH_KWARGS，
        # 用户显式关掉时以用户的为准（否则 setdefault 只是看着像可覆盖）。
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        llm = OpenAIClient("deepseek-chat", base_url="https://opencode.ai/zen/go/v1",
                           provider="deepseek", stream_usage=False).get_llm()
        assert llm._should_stream_usage(None) is False

    def test_non_streaming_path_unchanged(self, monkeypatch):
        # 非流式本来就带用量，不该被动到。
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "k")
        llm = OpenAIClient("deepseek-chat", base_url="https://api.deepseek.com",
                           provider="deepseek", timeout=150).get_llm()
        assert llm.streaming is False


@pytest.mark.unit
class TestDefaultConfig:
    def test_default_config_ships_retry_settings(self):
        assert DEFAULT_CONFIG["llm_timeout"] == 150
        assert DEFAULT_CONFIG["llm_max_retries"] == 3
        assert DEFAULT_CONFIG["llm_retry_delay"] == 5
