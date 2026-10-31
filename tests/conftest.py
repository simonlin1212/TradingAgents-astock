"""Shared pytest fixtures that prevent CI hangs when API keys are absent."""

import os
from unittest.mock import MagicMock, patch

import pytest


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")


_API_KEY_ENV_VARS = (
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "ZHIPU_API_KEY",
    "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
)


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    for env_var in _API_KEY_ENV_VARS:
        monkeypatch.setenv(env_var, os.environ.get(env_var, "placeholder"))


@pytest.fixture(autouse=True)
def _isolate_mootdx_negative_cache(tmp_path, monkeypatch):
    """把 mootdx 的「整张服务器表都验不过」结论重定向到临时目录。

    该结论是**落盘**的（供后续进程复用，见 `a_stock._mootdx_state_path`），所以必须
    逐用例隔离，否则会同时坏掉两件事：

    1. 测试会往用户真实的 cache 目录（默认 `~/.tradingagents/cache`）写文件；
    2. 某个用例留下的一条未过期结论，会让同一轮里后面那些「模拟出可用服务器」的
       用例直接命中快速失败路径——测试结果取决于跑之前这台机器上发生过什么。
    """
    from tradingagents.dataflows import a_stock

    monkeypatch.setattr(
        a_stock,
        "_mootdx_state_path",
        lambda: str(tmp_path / "mootdx_unavailable.json"),
    )
    monkeypatch.setattr(a_stock, "_mootdx_unavailable_until", 0.0)


@pytest.fixture()
def mock_llm_client():
    client = MagicMock()
    client.get_llm.return_value = MagicMock()
    with patch(
        "tradingagents.llm_clients.factory.create_llm_client",
        return_value=client,
    ):
        yield client
