"""mootdx 服务器选取（#90）。

现实里存在大量"TCP 三次握手成功、通达信协议握手立刻被 RST"的服务器。旧实现
只做 TCP 探测就把 client 钉进单例，于是之后每一次取数都失败降级、且永远不会
重选服务器。这些用例锁死修复后的三条行为：

1. TCP 通但取不到数的服务器必须被跳过，继续试下一台；
2. 全部失败后要抛错，并在冷却期内快速失败（不再逐台重探）；
3. 选中的服务器之后挂掉时，要弃用它，下次换一台。
"""

import pytest

from tradingagents.dataflows import a_stock


class FakeQuotesClient:
    """假的 mootdx client：可配置成"协议层直接炸"或"正常返回"。"""

    def __init__(self, ip, works: bool):
        self.ip = ip
        self.works = works
        self.calls = 0

    def bars(self, **kwargs):
        self.calls += 1
        if not self.works:
            raise ConnectionResetError("[Errno 54] Connection reset by peer")
        import pandas as pd

        return pd.DataFrame({"close": [1700.0]})


@pytest.fixture
def fake_tdx(monkeypatch):
    """把服务器表、TCP 探测、Quotes.factory 全部换成可控假件。"""
    import mootdx.quotes

    servers = [("1.1.1.1", 7709), ("2.2.2.2", 7709), ("3.3.3.3", 7709)]
    state = {
        "tcp_open": {ip for ip, _ in servers},  # TCP 端口开着的
        "protocol_ok": set(),                   # 协议层真能取数的
        "probe_calls": [],
        "clients": {},
    }

    monkeypatch.setattr(a_stock, "_TDX_SERVERS", servers)
    monkeypatch.setattr(a_stock, "_mootdx_client", None)
    monkeypatch.setattr(a_stock, "_mootdx_unavailable_until", 0.0)

    def fake_probe(ip, port, timeout=2.0):
        state["probe_calls"].append(ip)
        return ip in state["tcp_open"]

    monkeypatch.setattr(a_stock, "_probe_tdx", fake_probe)

    class FakeQuotes:
        @staticmethod
        def factory(market="std", server=None, **kwargs):
            ip = server[0] if server else "bestip"
            client = FakeQuotesClient(ip, works=ip in state["protocol_ok"])
            state["clients"][ip] = client
            return client

    monkeypatch.setattr(mootdx.quotes, "Quotes", FakeQuotes)
    return state


def test_skips_server_that_accepts_tcp_but_fails_protocol(fake_tdx):
    """1.1.1.1 端口开着却取不到数 → 必须跳过它，选到真正可用的 2.2.2.2。"""
    fake_tdx["protocol_ok"] = {"2.2.2.2"}

    client = a_stock._get_mootdx_client()

    assert client.ip == "2.2.2.2"
    # 坏服务器被真实取数验证挡下来了，而不是被采纳
    assert fake_tdx["clients"]["1.1.1.1"].works is False


def test_selected_client_is_cached(fake_tdx):
    """选中之后要复用，不能每次调用都重新逐台探测。"""
    fake_tdx["protocol_ok"] = {"1.1.1.1"}

    first = a_stock._get_mootdx_client()
    probes_after_first = len(fake_tdx["probe_calls"])
    second = a_stock._get_mootdx_client()

    assert first is second
    assert len(fake_tdx["probe_calls"]) == probes_after_first


def test_all_servers_dead_raises_then_fails_fast(fake_tdx):
    """全挂 → 抛错；冷却期内第二次调用直接失败，不再重探。"""
    fake_tdx["protocol_ok"] = set()

    with pytest.raises(RuntimeError, match="通达信"):
        a_stock._get_mootdx_client()
    probes_after_first = len(fake_tdx["probe_calls"])
    assert probes_after_first >= len(fake_tdx["tcp_open"])

    with pytest.raises(RuntimeError, match="不再重探|不再重试"):
        a_stock._get_mootdx_client()
    # 快速失败：没有再打一遍服务器表
    assert len(fake_tdx["probe_calls"]) == probes_after_first


def test_tcp_unreachable_servers_are_not_probed_for_data(fake_tdx):
    """TCP 不通的直接跳过，不去建 client。"""
    fake_tdx["tcp_open"] = {"3.3.3.3"}
    fake_tdx["protocol_ok"] = {"3.3.3.3"}

    client = a_stock._get_mootdx_client()

    assert client.ip == "3.3.3.3"
    assert "1.1.1.1" not in fake_tdx["clients"]
    assert "2.2.2.2" not in fake_tdx["clients"]


def test_mootdx_call_discards_client_after_failure(fake_tdx):
    """选中的服务器后来挂了 → 弃用它，下一次换一台，而不是一直降级。"""
    fake_tdx["protocol_ok"] = {"1.1.1.1", "2.2.2.2"}

    a_stock._mootdx_call("bars", symbol="600519")
    assert a_stock._mootdx_client is not None
    assert a_stock._mootdx_client.ip == "1.1.1.1"

    # 服务器挂掉：当前 client 的后续调用开始报错
    a_stock._mootdx_client.works = False
    with pytest.raises(ConnectionResetError):
        a_stock._mootdx_call("bars", symbol="600519")

    # 关键断言：坏 client 已被丢弃，而不是继续钉在单例里
    assert a_stock._mootdx_client is None

    # 下一次调用重新选服务器，落到还活着的那台
    fake_tdx["protocol_ok"] = {"2.2.2.2"}
    a_stock._mootdx_call("bars", symbol="600519")
    assert a_stock._mootdx_client.ip == "2.2.2.2"


def test_get_client_failure_does_not_clear_negative_cache(fake_tdx):
    """取 client 失败不该清掉负缓存，否则快速失败就失效了。"""
    fake_tdx["protocol_ok"] = set()

    with pytest.raises(RuntimeError):
        a_stock._mootdx_call("bars", symbol="600519")
    probes = len(fake_tdx["probe_calls"])

    with pytest.raises(RuntimeError):
        a_stock._mootdx_call("bars", symbol="600519")
    assert len(fake_tdx["probe_calls"]) == probes


# ---------------------------------------------------------------------------
# 协议层失败的真实形态：握手在 Quotes.factory 内部就炸，根本走不到取数验证。
# 只统计"取数失败"会让计数恒为 0，快速失败判断随之失效（实测踩过）。
# ---------------------------------------------------------------------------


@pytest.fixture
def handshake_fails(monkeypatch):
    """服务器 TCP 通，但 Quotes.factory 建连时握手被 RST —— 线上就是这个形态。"""
    import mootdx.quotes

    servers = [(f"10.0.0.{i}", 7709) for i in range(1, 9)]
    state = {"factory_calls": [], "bestip_used": False}

    monkeypatch.setattr(a_stock, "_TDX_SERVERS", servers)
    # 候选表 = 精选表 + mootdx 自带主机表；测试里只保留精选表，断言才可控
    monkeypatch.setattr(a_stock, "_candidate_tdx_servers", lambda: list(servers))
    monkeypatch.setattr(a_stock, "_mootdx_client", None)
    monkeypatch.setattr(a_stock, "_mootdx_unavailable_until", 0.0)
    monkeypatch.setattr(a_stock, "_probe_tdx", lambda ip, port, timeout=2.0: True)

    class FakeQuotes:
        @staticmethod
        def factory(market="std", server=None, **kwargs):
            if kwargs.get("bestip"):
                state["bestip_used"] = True
                raise ConnectionResetError("bestip 也连不上")
            state["factory_calls"].append(server[0] if server else "bare")
            raise ConnectionResetError("[Errno 54] Connection reset by peer")

    monkeypatch.setattr(mootdx.quotes, "Quotes", FakeQuotes)
    return state


def test_handshake_failure_counts_as_protocol_failure(handshake_fails):
    """握手期就炸的服务器要被算进协议失败（决定报错文案与是否跑 bestip）。

    ⚠️ 这里**必须把整张表试完**。曾经加过「连续 3 台失败就停手」，被 codex 指出：
    三台远端拒绝证明不了本地封了协议，列表靠后的服务器完全可能是好的，提前收手
    会让那台永远试不到、还顺手记 5 分钟负缓存。
    """
    with pytest.raises(RuntimeError, match="协议握手/取数被拒"):
        a_stock._get_mootdx_client()

    tried = [c for c in handshake_fails["factory_calls"] if c != "bare"]
    assert len(tried) == len(a_stock._TDX_SERVERS), (
        f"应当把整张服务器表试完，实际只试了 {len(tried)} 台"
    )


def test_later_working_server_is_still_found(handshake_fails, monkeypatch):
    """前几台协议失败不能妨碍后面那台可用服务器被选中（codex P2）。"""
    import mootdx.quotes
    import pandas as pd

    good_ip = a_stock._TDX_SERVERS[-1][0]

    class GoodClient:
        ip = good_ip

        def bars(self, **kwargs):
            return pd.DataFrame({"close": [1700.0]})

    class FakeQuotes:
        @staticmethod
        def factory(market="std", server=None, **kwargs):
            if server and server[0] == good_ip:
                return GoodClient()
            raise ConnectionResetError("[Errno 54] Connection reset by peer")

    monkeypatch.setattr(mootdx.quotes, "Quotes", FakeQuotes)

    assert a_stock._get_mootdx_client().ip == good_ip


def test_bestip_skipped_when_protocol_is_the_problem(handshake_fails):
    """bestip 会把内置主机表整个测速一遍（实测几分钟）。协议层被拦时它用的是
    同一套协议、同一批主机，不可能有别的结果，跑它只是让用户干等。"""
    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()

    assert handshake_fails["bestip_used"] is False


def test_candidate_list_includes_mootdx_own_hosts():
    """候选表必须覆盖 mootdx 自带主机表，而不只是精选的那 10 台。

    只试精选表的话，它们恰好都不可用时会被判成"全网不可达"并记 5 分钟负缓存，
    而 mootdx 自带表里可能还有活着的主机（codex 复审指出）。
    """
    candidates = a_stock._candidate_tdx_servers()

    assert len(candidates) > len(a_stock._TDX_SERVERS)
    assert candidates[:len(a_stock._TDX_SERVERS)] == list(a_stock._TDX_SERVERS), (
        "实测精选的服务器应排在前面，让常见情况第一台就命中"
    )
    assert len(candidates) == len(set(candidates)), "候选表不该有重复"


def test_bestip_is_never_used(handshake_fails):
    """不再用 bestip：它要把整张表测速一遍（实测几分钟），而候选表已逐台验证过，
    覆盖面相当且每台都是"真取到数才算通过"。"""
    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()

    assert handshake_fails["bestip_used"] is False


def test_probing_restores_mootdx_bestip_when_nothing_works(handshake_fails, monkeypatch):
    """探测不能把用户配好的服务器覆写掉（codex 第五轮）。

    mootdx 的 StdQuotes.__init__ 里有 `config.set('BESTIP', {'HQ': self.server})`
    ——每建一次带 server 的 client 都会持久化写入配置文件。逐台探测 38 个候选等于
    一路覆写，最后留下的是最后一台**失败的**服务器，裸 factory 兜底（读 BESTIP）
    再也救不回来，还会连累同机上其它用 mootdx 的程序。
    """
    from mootdx import config as mootdx_config

    original = {"HQ": ["1.2.3.4", 7709], "EX": "", "GP": ""}
    store = {"BESTIP": {"HQ": "", "EX": "", "GP": ""}}   # 未 setup 时的模块默认空值
    setup_called = {"n": 0}

    def fake_setup():
        # 复刻真实语义：setup() 之后才把持久化的值读进来
        setup_called["n"] += 1
        store["BESTIP"] = dict(original)

    monkeypatch.setattr(mootdx_config, "setup", fake_setup)
    monkeypatch.setattr(mootdx_config, "get", lambda k: store.get(k))
    monkeypatch.setattr(mootdx_config, "set", lambda k, v: store.__setitem__(k, v))

    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()

    assert setup_called["n"] >= 1, (
        "必须先 setup() 再快照——新进程里 config.get('BESTIP') 是模块默认空值，"
        "快照到空值的话'还原'反而会把用户真实配置抹掉"
    )
    assert store["BESTIP"] == original, "全部探测失败后应把 BESTIP 还原成原样"


def test_bestip_kept_when_a_server_works(fake_tdx, monkeypatch):
    """选出可用服务器时**不能**还原——那次覆写正是我们想要的结果。"""
    from mootdx import config as mootdx_config

    store = {"BESTIP": {"HQ": "", "EX": "", "GP": ""}}
    persisted = {"HQ": ["1.2.3.4", 7709], "EX": "", "GP": ""}
    monkeypatch.setattr(mootdx_config, "setup", lambda: store.__setitem__("BESTIP", dict(persisted)))
    monkeypatch.setattr(mootdx_config, "get", lambda k: store.get(k))
    monkeypatch.setattr(mootdx_config, "set", lambda k, v: store.__setitem__(k, v))

    fake_tdx["protocol_ok"] = {"2.2.2.2"}
    # 模拟 mootdx：建 client 时写 BESTIP
    original_factory = None
    import mootdx.quotes as mq
    real = mq.Quotes.factory

    class Wrapped:
        @staticmethod
        def factory(market="std", server=None, **kw):
            if server:
                store["BESTIP"] = {"HQ": list(server), "EX": "", "GP": ""}
            return real(market=market, server=server, **kw)

    monkeypatch.setattr(mq, "Quotes", Wrapped)

    client = a_stock._get_mootdx_client()

    assert client.ip == "2.2.2.2"
    assert store["BESTIP"]["HQ"] == ["2.2.2.2", 7709], (
        "选中的服务器应当留在配置里，而不是被还原掉"
    )


def test_bestip_restored_even_if_probing_raises(handshake_fails, monkeypatch):
    """探测中途抛异常也要还原——手动调还原函数时这条路径最容易漏。"""
    from mootdx import config as mootdx_config

    persisted = {"HQ": ["1.2.3.4", 7709], "EX": "", "GP": ""}
    store = {"BESTIP": {"HQ": "", "EX": "", "GP": ""}}
    monkeypatch.setattr(mootdx_config, "setup", lambda: store.__setitem__("BESTIP", dict(persisted)))
    monkeypatch.setattr(mootdx_config, "get", lambda k: store.get(k))
    monkeypatch.setattr(mootdx_config, "set", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(a_stock, "_reachable_tdx_servers",
                        lambda servers, timeout=2.0: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        a_stock._get_mootdx_client()

    assert store["BESTIP"] == persisted, "异常路径也必须还原"
