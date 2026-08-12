"""分角色模型（#39）。

同一个模型分饰多角时倾向于互相附和，多空辩论就失去意义。`role_llms` 允许给
单个角色指定另一家模型。

**默认必须完全维持原行为**——大多数用户只有一家模型，不配这一项时不能有任何
变化。下面第一组用例就是锁这一点的。
"""

import pytest

from tradingagents.graph.setup import DEEP_ROLES, ROLE_KEYS, GraphSetup


class FakeLLM:
    def __init__(self, tag):
        self.tag = tag

    def __repr__(self):  # pragma: no cover - 只为断言失败时好读
        return f"FakeLLM({self.tag})"


@pytest.fixture
def llms():
    return FakeLLM("quick"), FakeLLM("deep")


def make_setup(quick, deep, resolve=None):
    return GraphSetup(quick, deep, tool_nodes={}, conditional_logic=None, resolve_llm=resolve)


# ---------------------------------------------------------------------------
# 默认行为不变
# ---------------------------------------------------------------------------


def test_without_role_llms_quick_roles_use_quick(llms):
    quick, deep = llms
    setup = make_setup(quick, deep)

    for role in ROLE_KEYS:
        if role not in DEEP_ROLES:
            assert setup.llm_for(role) is quick, role


def test_without_role_llms_deep_roles_use_deep(llms):
    quick, deep = llms
    setup = make_setup(quick, deep)

    for role in DEEP_ROLES:
        assert setup.llm_for(role) is deep, role


def test_empty_resolver_falls_back(llms):
    """resolve_llm 存在但对该角色返回 None → 回落，而不是把 None 传给 agent。"""
    quick, deep = llms
    setup = make_setup(quick, deep, resolve={}.get)

    assert setup.llm_for("bull") is quick
    assert setup.llm_for("portfolio_manager") is deep


# ---------------------------------------------------------------------------
# 配置生效
# ---------------------------------------------------------------------------


def test_configured_role_overrides_default(llms):
    quick, deep = llms
    bear_llm = FakeLLM("bear-other-vendor")
    setup = make_setup(quick, deep, resolve={"bear": bear_llm}.get)

    assert setup.llm_for("bear") is bear_llm
    assert setup.llm_for("bull") is quick  # 没配的角色不受影响


def test_configured_deep_role_overrides_deep(llms):
    quick, deep = llms
    pm_llm = FakeLLM("pm-other-vendor")
    setup = make_setup(quick, deep, resolve={"portfolio_manager": pm_llm}.get)

    assert setup.llm_for("portfolio_manager") is pm_llm
    assert setup.llm_for("research_manager") is deep


def test_all_roles_are_addressable(llms):
    """ROLE_KEYS 里的每个名字都必须真的能指到一个角色。"""
    quick, deep = llms
    for role in ROLE_KEYS:
        marker = FakeLLM(role)
        setup = make_setup(quick, deep, resolve={role: marker}.get)
        assert setup.llm_for(role) is marker, role


def test_role_keys_cover_bull_and_bear():
    """#39 的核心诉求就是多空分开，这两个键必须在。"""
    assert "bull" in ROLE_KEYS
    assert "bear" in ROLE_KEYS


# ---------------------------------------------------------------------------
# 配置解析：写错要当场报错，相同配置要复用实例
# ---------------------------------------------------------------------------


def build(config, monkeypatch, subscription_on=False):
    """只跑 _build_role_llms，不做整图初始化（那要真 API key）。"""
    from tradingagents.graph import trading_graph as tg

    created = []

    class FakeClient:
        def __init__(self, provider, model, base_url):
            self.spec = (provider, model, base_url)

        def get_llm(self):
            return FakeLLM(self.spec)

    def fake_create(provider, model, base_url=None, **kwargs):
        created.append((provider, model, base_url))
        return FakeClient(provider, model, base_url)

    monkeypatch.setattr(tg, "create_llm_client", fake_create)
    graph = tg.TradingAgentsGraph.__new__(tg.TradingAgentsGraph)
    graph.config = config
    return graph._build_role_llms({}, subscription_on), created


def test_no_config_builds_nothing(monkeypatch):
    resolved, created = build({"llm_provider": "openai", "role_llms": {}}, monkeypatch)

    assert resolved == {}
    assert created == []   # 一个客户端都不该建


def test_unknown_role_name_raises(monkeypatch):
    """角色名写错必须当场报错——静默忽略会让人以为配置生效了。"""
    with pytest.raises(ValueError, match="无法识别的角色名"):
        build(
            {"llm_provider": "openai", "role_llms": {"bulls": {"model": "m"}}},
            monkeypatch,
        )


def test_spec_without_model_raises(monkeypatch):
    with pytest.raises(ValueError, match="必须是带 model 的字典"):
        build(
            {"llm_provider": "openai", "role_llms": {"bull": {"provider": "qwen"}}},
            monkeypatch,
        )


def test_identical_specs_share_one_instance(monkeypatch):
    """两个角色配同一个模型，只该建一个实例，不该开两条连接。"""
    cfg = {
        "llm_provider": "openai",
        "role_llms": {
            "bull": {"provider": "deepseek", "model": "deepseek-chat"},
            "bear": {"provider": "deepseek", "model": "deepseek-chat"},
        },
    }
    resolved, created = build(cfg, monkeypatch)

    assert resolved["bull"] is resolved["bear"]
    assert len(created) == 1


def test_different_vendors_build_separate_instances(monkeypatch):
    cfg = {
        "llm_provider": "openai",
        "role_llms": {
            "bull": {"provider": "deepseek", "model": "deepseek-chat"},
            "bear": {"provider": "qwen", "model": "qwen-plus"},
        },
    }
    resolved, created = build(cfg, monkeypatch)

    assert resolved["bull"] is not resolved["bear"]
    assert len(created) == 2


def test_backend_url_not_leaked_across_vendors(monkeypatch):
    """主 provider 的端点不能带给另一家，否则请求发到别人的网关。"""
    cfg = {
        "llm_provider": "openai",
        "backend_url": "https://my-openai-relay.example/v1",
        "role_llms": {"bear": {"provider": "deepseek", "model": "deepseek-chat"}},
    }
    _, created = build(cfg, monkeypatch)

    assert created[0][2] is None


def test_backend_url_kept_for_same_vendor(monkeypatch):
    """同一家 provider 换模型，端点应当继续沿用。"""
    cfg = {
        "llm_provider": "openai",
        "backend_url": "https://my-openai-relay.example/v1",
        "role_llms": {"bear": {"model": "gpt-5.4-mini"}},
    }
    _, created = build(cfg, monkeypatch)

    assert created[0] == ("openai", "gpt-5.4-mini", "https://my-openai-relay.example/v1")


def test_explicit_backend_url_wins(monkeypatch):
    cfg = {
        "llm_provider": "openai",
        "backend_url": "https://main.example/v1",
        "role_llms": {
            "bear": {"provider": "qwen", "model": "qwen-plus",
                     "backend_url": "https://my-qwen.example/v1"},
        },
    }
    _, created = build(cfg, monkeypatch)

    assert created[0][2] == "https://my-qwen.example/v1"


def test_warns_when_bypassing_subscription(monkeypatch, caplog):
    """订阅覆盖开着时，绕开它去计费的角色必须被点名，不能悄悄花钱。"""
    import logging

    cfg = {
        "llm_provider": "openai",
        "role_llms": {"bear": {"provider": "deepseek", "model": "deepseek-chat"}},
    }
    with caplog.at_level(logging.WARNING):
        build(cfg, monkeypatch, subscription_on=True)

    assert any("bear" in r.getMessage() and "计费" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# codex 复审补的两条
# ---------------------------------------------------------------------------


def test_provider_specific_kwargs_not_leaked_to_other_vendors(monkeypatch):
    """openai 的 reasoning_effort 不能带给 qwen —— 别家可能直接拒收这个参数。"""
    from tradingagents.graph import trading_graph as tg

    created = []

    class FakeClient:
        def __init__(self, **kw): pass
        def get_llm(self): return FakeLLM("x")

    def fake_create(provider, model, base_url=None, **kwargs):
        created.append((provider, kwargs))
        return FakeClient()

    monkeypatch.setattr(tg, "create_llm_client", fake_create)
    graph = tg.TradingAgentsGraph.__new__(tg.TradingAgentsGraph)
    graph.config = {
        "llm_provider": "openai",
        "role_llms": {
            "bull": {"provider": "qwen", "model": "qwen-plus"},
            "bear": {"model": "gpt-5.4-mini"},          # 同一家，应保留
        },
    }
    graph._build_role_llms({"reasoning_effort": "high", "max_tokens": 8000}, False)

    by_provider = {p: kw for p, kw in created}
    assert "reasoning_effort" not in by_provider["qwen"], "别家 provider 收到了 openai 专属参数"
    assert by_provider["qwen"]["max_tokens"] == 8000, "通用参数不该被一起过滤掉"
    assert by_provider["openai"]["reasoning_effort"] == "high", "同一家应保留专属参数"


def test_unselected_analyst_roles_are_not_instantiated(monkeypatch):
    """没选中的分析师不会进图，就不该为它建模型。

    否则一个**永远不执行**的节点会因为缺 API key 或缺可选依赖，把一次本来完全
    正常的分析在启动时就打断（codex 终轮指出）。
    """
    from tradingagents.graph import trading_graph as tg

    created = []

    class FakeClient:
        def __init__(self, **kw): pass
        def get_llm(self): return FakeLLM("x")

    monkeypatch.setattr(tg, "create_llm_client",
                        lambda provider, model, base_url=None, **kw: (
                            created.append(provider) or FakeClient()))
    graph = tg.TradingAgentsGraph.__new__(tg.TradingAgentsGraph)
    graph.config = {
        "llm_provider": "openai",
        "role_llms": {
            "market": {"provider": "qwen", "model": "qwen-plus"},
            "policy": {"provider": "glm", "model": "glm-4.6"},   # 未选中
        },
    }

    resolved = graph._build_role_llms({}, False, selected_analysts=["market"])

    assert "market" in resolved
    assert "policy" not in resolved
    assert "glm" not in created, "未选中的分析师角色不该建模型"


def test_non_analyst_roles_are_always_built(monkeypatch):
    """多空/风险/Manager 这些角色不受 selected_analysts 控制，必须照常建。"""
    from tradingagents.graph import trading_graph as tg

    class FakeClient:
        def __init__(self, **kw): pass
        def get_llm(self): return FakeLLM("x")

    monkeypatch.setattr(tg, "create_llm_client",
                        lambda provider, model, base_url=None, **kw: FakeClient())
    graph = tg.TradingAgentsGraph.__new__(tg.TradingAgentsGraph)
    graph.config = {
        "llm_provider": "openai",
        "role_llms": {"bull": {"provider": "qwen", "model": "qwen-plus"}},
    }

    resolved = graph._build_role_llms({}, False, selected_analysts=["market"])
    assert "bull" in resolved
