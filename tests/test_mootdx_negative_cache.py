"""Tests for the mootdx probe fast-fail path.

Two costs are pinned here. Both were measured on a network where every TDX
server answers ``get_security_bars`` with a 2-byte count stub (#90 / #98), so
the probe always ends in "whole table is dead" — the worst case, and the one
users actually hit:

1. ``StdQuotes`` defaults to ``auto_retry=True``, whose backoff is
   ``0.1/0.5/1/2`` seconds. Per server that is ~4.2s instead of ~0.1s — 14
   reachable servers made the probe 59s of 63s. Probe clients must therefore be
   built with ``auto_retry=False``.
2. The "whole table is dead" verdict is persisted, so the next process fails
   fast instead of re-running the probe.
"""

import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows import a_stock


@pytest.fixture(autouse=True)
def _isolate_mootdx_state(tmp_path, monkeypatch):
    """Never touch the real cache dir, the real mootdx config, or the singleton."""
    state = tmp_path / "mootdx_unavailable.json"
    monkeypatch.setattr(a_stock, "_mootdx_state_path", lambda: str(state))
    monkeypatch.setattr(a_stock, "_mootdx_client", None)
    monkeypatch.setattr(a_stock, "_mootdx_unavailable_until", 0.0)

    @contextmanager
    def _noop_bestip_guard():
        # 真实的 _preserve_mootdx_bestip 会写用户的 mootdx 配置文件
        yield lambda: None

    monkeypatch.setattr(a_stock, "_preserve_mootdx_bestip", _noop_bestip_guard)
    return state


def _write_state(state_path, unavailable_until):
    state_path.write_text(
        json.dumps({"unavailable_until": unavailable_until, "checked_at": time.time()}),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# state file helpers
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_load_returns_zero_without_file(_isolate_mootdx_state):
    assert a_stock._load_mootdx_unavailable_until() == 0.0


@pytest.mark.unit
def test_load_returns_future_timestamp(_isolate_mootdx_state):
    until = time.time() + 120
    _write_state(_isolate_mootdx_state, until)

    assert a_stock._load_mootdx_unavailable_until() == pytest.approx(until)


@pytest.mark.unit
def test_load_ignores_expired_timestamp(_isolate_mootdx_state):
    _write_state(_isolate_mootdx_state, time.time() - 1)

    assert a_stock._load_mootdx_unavailable_until() == 0.0


@pytest.mark.unit
def test_load_ignores_corrupt_file(_isolate_mootdx_state):
    _isolate_mootdx_state.write_text("not json at all", encoding="utf-8")

    assert a_stock._load_mootdx_unavailable_until() == 0.0


@pytest.mark.unit
def test_clear_removes_state_file(_isolate_mootdx_state):
    _write_state(_isolate_mootdx_state, time.time() + 120)

    a_stock._clear_mootdx_unavailable_state()

    assert not _isolate_mootdx_state.exists()


@pytest.mark.unit
def test_clear_is_silent_when_no_state_file(_isolate_mootdx_state):
    a_stock._clear_mootdx_unavailable_state()  # must not raise


# --------------------------------------------------------------------------
# fail-fast behaviour
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_persisted_verdict_skips_the_whole_probe(_isolate_mootdx_state, monkeypatch):
    """有未过期的落盘结论时，连候选表都不该构建。"""
    _write_state(_isolate_mootdx_state, time.time() + 120)

    def _boom(*args, **kwargs):  # pragma: no cover - 被调用就说明没走快速失败
        raise AssertionError("探测不该被触发")

    monkeypatch.setattr(a_stock, "_candidate_tdx_servers", _boom)
    monkeypatch.setattr(a_stock, "_reachable_tdx_servers", _boom)

    with pytest.raises(RuntimeError, match="上一个进程"):
        a_stock._get_mootdx_client()


@pytest.mark.unit
def test_probe_clients_disable_mootdx_auto_retry(_isolate_mootdx_state, monkeypatch):
    """探测用的每个 client 都必须带 auto_retry=False，否则每台白等 3.6s。"""
    monkeypatch.setattr(a_stock, "_candidate_tdx_servers", lambda: [("1.2.3.4", 7709)])
    monkeypatch.setattr(
        a_stock, "_reachable_tdx_servers", lambda servers, **kw: list(servers)
    )

    with patch("mootdx.quotes.Quotes.factory") as factory:
        factory.return_value = MagicMock()
        with pytest.raises(RuntimeError):
            a_stock._get_mootdx_client()

    assert factory.call_count >= 2  # 逐台探测 + 裸 factory 兜底
    for call in factory.call_args_list:
        assert call.kwargs.get("auto_retry") is False, call


@pytest.mark.unit
def test_all_servers_dead_persists_the_verdict(_isolate_mootdx_state, monkeypatch):
    monkeypatch.setattr(a_stock, "_candidate_tdx_servers", lambda: [("1.2.3.4", 7709)])
    monkeypatch.setattr(
        a_stock, "_reachable_tdx_servers", lambda servers, **kw: list(servers)
    )

    with patch("mootdx.quotes.Quotes.factory", side_effect=OSError("reset")):
        with pytest.raises(RuntimeError, match="mootdx 通达信服务器不可用"):
            a_stock._get_mootdx_client()

    assert _isolate_mootdx_state.exists()
    saved = json.loads(_isolate_mootdx_state.read_text(encoding="utf-8"))
    assert saved["unavailable_until"] > time.time()
    assert saved["unavailable_until"] <= time.time() + a_stock._MOOTDX_RETRY_AFTER_S


@pytest.mark.unit
def test_selecting_a_server_clears_the_persisted_verdict(
    _isolate_mootdx_state, monkeypatch
):
    """选到可用服务器后要清掉落盘结论，别让旧结论压住已经恢复的网络。"""
    _write_state(_isolate_mootdx_state, time.time() - 1)  # 已过期
    monkeypatch.setattr(a_stock, "_candidate_tdx_servers", lambda: [("1.2.3.4", 7709)])
    monkeypatch.setattr(
        a_stock, "_reachable_tdx_servers", lambda servers, **kw: list(servers)
    )
    monkeypatch.setattr(a_stock, "_tdx_client_works", lambda client: True)

    with patch("mootdx.quotes.Quotes.factory") as factory:
        factory.return_value = MagicMock()
        client = a_stock._get_mootdx_client()

    assert client is not None
    assert not _isolate_mootdx_state.exists()


@pytest.mark.unit
def test_retry_after_is_configurable_by_env():
    """TTL 可由环境变量调大，让封了 7709 的网络把整表探测挪到很久一次。

    用子进程验证：模块级常量在 import 时求值，reload 会污染同进程里其它测试
    持有的模块对象与 monkeypatch，得不偿失。
    """
    env = dict(os.environ, TRADINGAGENTS_MOOTDX_RETRY_AFTER_S="3600")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import tradingagents.dataflows.a_stock as m; print(m._MOOTDX_RETRY_AFTER_S)",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "3600.0"
