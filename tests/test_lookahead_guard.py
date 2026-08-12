"""未来函数防护（point-in-time）。

在历史日期上跑分析时，数据层不能把"今天"的数据当成"分析日当天"的事实交给模型
——报告里完全看不出来，但结论已经被污染了。上游 TradingAgents 把这类问题统称为
backtesting date fidelity（#475）。

本仓库审出三个函数收了日期参数却完全没用：`get_fund_flow`（今天的分钟资金流 +
从今天回溯 20 日）、`get_fundamentals`（腾讯实时估值）、`get_profit_forecast`
（当前一致预期）。前者能真正做时点截断；后两者的数据源根本不提供历史时点值，
补不上就必须**说出来**，而不是静默把今天的数字当历史事实。
"""

from datetime import datetime, timedelta

import pytest

from tradingagents.dataflows import a_stock


TODAY = datetime.now().strftime("%Y-%m-%d")
PAST = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 判定本身
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (PAST, True),
        (TODAY, False),
        ((datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"), False),
        ("", False),
        (None, False),
        ("not-a-date", False),          # 解析不了不能当成历史，否则误伤实时分析
        (f"{PAST} 09:30:00", True),     # 带时分秒也要认得
    ],
)
def test_is_historical(value, expected):
    assert a_stock._is_historical(value) is expected


def test_snapshot_notice_names_the_date_and_says_do_not_use():
    notice = a_stock._snapshot_notice(PAST, "估值")

    assert PAST in notice
    assert "实时快照" in notice
    assert "不得" in notice   # 必须给模型明确指令，光提示"这是实时的"不够


# ---------------------------------------------------------------------------
# get_fund_flow：真正的时点截断
# ---------------------------------------------------------------------------


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def fake_em(monkeypatch):
    """假的东财返回：历史段跨越分析日前后，用来验证截断。"""
    calls = []

    def fake_get(url, params=None, timeout=10):
        calls.append(url)
        if "push2his" in url:
            return FakeResp({"data": {"klines": [
                "2026-05-01,1000,0,0,0,0,0",
                f"{PAST},2000,0,0,0,0,0",
                "2099-01-01,999999,0,0,0,0,0",   # 分析日之后 → 必须被剔除
            ]}})
        return FakeResp({"data": {"klines": [
            "2099-01-01 09:31,111,0,0,0,0,0",     # 实时段 → 复盘时整段不该取
        ]}})

    monkeypatch.setattr(a_stock, "_em_get", fake_get)
    return calls


def test_fund_flow_drops_rows_after_analysis_date(fake_em):
    out = a_stock.get_fund_flow("600519", PAST)

    assert "2099-01-01" not in out, "分析日之后的资金流泄漏了（未来函数）"
    assert PAST in out


def test_fund_flow_skips_realtime_when_historical(fake_em):
    a_stock.get_fund_flow("600519", PAST)

    assert not any("push2.eastmoney.com/api/qt/stock/fflow/kline" in u for u in fake_em), (
        "复盘历史日期时不该再去取今天的分钟资金流"
    )


def test_fund_flow_says_why_realtime_is_missing(fake_em):
    """略去实时段要说明原因，否则用户以为接口坏了。"""
    out = a_stock.get_fund_flow("600519", PAST)

    assert "略去实时分钟资金流" in out


def test_fund_flow_keeps_realtime_for_today(fake_em):
    """当天分析仍然要有实时资金流——防护不能误伤正常用法。"""
    a_stock.get_fund_flow("600519", TODAY)

    assert any("fflow/kline" in u for u in fake_em)


# ---------------------------------------------------------------------------
# 只有实时快照的两个：补不上就必须明说
# ---------------------------------------------------------------------------


def test_fundamentals_warns_on_historical_date(monkeypatch):
    monkeypatch.setattr(a_stock, "_tencent_quote", lambda codes: {})
    monkeypatch.setattr(a_stock, "_mootdx_call", lambda *a, **k: None)
    monkeypatch.setattr(a_stock, "_em_get", lambda *a, **k: FakeResp({}))

    out = a_stock.get_fundamentals("600519", PAST)

    assert "未来函数警告" in out
    assert PAST in out


def test_fundamentals_silent_for_today(monkeypatch):
    monkeypatch.setattr(a_stock, "_tencent_quote", lambda codes: {})
    monkeypatch.setattr(a_stock, "_mootdx_call", lambda *a, **k: None)
    monkeypatch.setattr(a_stock, "_em_get", lambda *a, **k: FakeResp({}))

    out = a_stock.get_fundamentals("600519", TODAY)

    assert "未来函数警告" not in out


def test_profit_forecast_warns_on_historical_date(monkeypatch):
    import pandas as pd

    monkeypatch.setattr(
        a_stock, "_ths_eps_forecast",
        lambda code: pd.DataFrame({"年度": ["2026"], "预测每股收益": [1.23]}),
    )

    out = a_stock.get_profit_forecast("600519", PAST)

    assert "未来函数警告" in out


# ---------------------------------------------------------------------------
# codex 复审补：防护要在**生产调用路径**上真的生效
# ---------------------------------------------------------------------------


def test_profit_forecast_tool_exposes_curr_date():
    """工具不把 curr_date 传下去，数据层的未来函数告警就是死代码。

    v0.5.1 给 get_profit_forecast 加了告警，但 @tool 只暴露 ticker，
    curr_date 恒为 None → 告警永远不触发，模型照样把今天的一致预期当历史事实。
    """
    from tradingagents.agents.utils.agent_utils import get_profit_forecast

    assert "curr_date" in get_profit_forecast.args


def test_every_date_aware_tool_forwards_its_date():
    """凡是数据层按 curr_date 做时点处理的工具，@tool 都必须暴露并转发它。"""
    import inspect

    from tradingagents.agents.utils import signal_data_tools

    src = inspect.getsource(signal_data_tools)
    for name in ("get_profit_forecast", "get_fund_flow"):
        call = f'route_to_vendor("{name}", '
        idx = src.find(call)
        assert idx != -1, f"找不到 {name} 的路由调用"
        line = src[idx:src.find(")", idx)]
        assert "curr_date" in line, f"{name} 没有把 curr_date 转发给数据层"


def test_fund_flow_widens_window_for_older_dates(fake_em, monkeypatch):
    """分析日早于最近 20 个交易日时，必须放大回溯窗口。

    接口只提供"从今天回溯 lmt 天"，仍只要 20 天的话过滤后一行不剩——
    把"数据不对"变成"没有数据"，比不过滤更糟（codex P2）。
    """
    captured = {}
    orig = a_stock._em_get

    def spy(url, params=None, timeout=10):
        if "push2his" in url:
            captured["lmt"] = params.get("lmt")
        return orig(url, params=params, timeout=timeout)

    monkeypatch.setattr(a_stock, "_em_get", spy)
    a_stock.get_fund_flow("600519", PAST)      # PAST = 90 天前

    assert captured["lmt"] > 20, f"回溯窗口没有放大，仍是 {captured.get('lmt')}"


def test_fund_flow_says_when_history_is_unavailable(monkeypatch):
    """过滤后为空要说明原因，不能让正文凭空少一段。"""
    def empty_hist(url, params=None, timeout=10):
        return FakeResp({"data": {"klines": []}})

    monkeypatch.setattr(a_stock, "_em_get", empty_hist)
    out = a_stock.get_fund_flow("600519", PAST)

    assert "未能取到" in out


def test_profit_forecast_curr_date_is_required():
    """给默认值等于没设防：模型按 {"ticker": "600519"} 调用时 curr_date 为空串，
    判定为"非历史"，告警永远不触发（codex 终轮指出）。"""
    from tradingagents.agents.utils.agent_utils import get_profit_forecast

    required = get_profit_forecast.args_schema.model_json_schema().get("required", [])
    assert "curr_date" in required


def test_fundamentals_prompt_tells_the_model_to_pass_the_date():
    """工具签名要求了还不够——提示词不提，模型也不会主动传。"""
    import inspect

    from tradingagents.agents.analysts import fundamentals_analyst

    src = inspect.getsource(fundamentals_analyst.create_fundamentals_analyst)
    assert "get_profit_forecast(ticker, curr_date)" in src
    assert "curr_date 必须传" in src


def test_fund_flow_history_trimmed_to_twenty_rows(monkeypatch):
    """窗口为够回溯才放大，过滤后要裁回承诺的 20 个交易日（codex 终轮指出）。

    不裁的话复盘 90 天前会返回约 40 行，既改变了请求的趋势窗口，又把返回体撑大一倍。
    """
    rows = [f"2026-{m:02d}-{d:02d},1000,0,0,0,0,0"
            for m in (3, 4, 5) for d in range(1, 16)]   # 45 行，全部早于 PAST

    def fake_get(url, params=None, timeout=10):
        if "push2his" in url:
            return FakeResp({"data": {"klines": rows}})
        return FakeResp({"data": {"klines": []}})

    monkeypatch.setattr(a_stock, "_em_get", fake_get)
    out = a_stock.get_fund_flow("600519", PAST)

    kept = [ln for ln in out.splitlines() if ln.strip().startswith("2026-")]
    assert len(kept) == 20, f"应裁到 20 行，实际 {len(kept)} 行"


def test_is_historical_uses_market_timezone_not_host(monkeypatch):
    """"今天"必须按 A 股市场时区算，不能用主机本地时区（codex 第四轮）。

    主机在 UTC+9 以东（如新西兰 UTC+13）时，当地已过零点而上海还在前一天——
    当天的分析会被判成"复盘历史"，实时资金流被略去、快照工具打出莫须有的
    未来函数警告。
    """
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    class FakeDatetime(_dt):
        @classmethod
        def now(cls, tz=None):
            # 奥克兰已是 8-10 凌晨，上海仍是 8-09 晚间
            aware = _dt(2026, 8, 9, 23, 30, tzinfo=_tz(_td(hours=8)))
            return aware.astimezone(tz) if tz else aware.astimezone(_tz(_td(hours=13))).replace(tzinfo=None)

    monkeypatch.setattr(a_stock, "datetime", FakeDatetime)

    assert a_stock._market_today().isoformat() == "2026-08-09"
    # 市场当天不该被判成历史，哪怕主机日历已经翻页
    assert a_stock._is_historical("2026-08-09") is False
    assert a_stock._is_historical("2026-08-08") is True
