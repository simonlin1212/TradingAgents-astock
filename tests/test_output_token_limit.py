"""输出上限与 Anthropic 兼容端点配置（#91 / #89）。

#91「报告输出到一半结束」：走 anthropic 通道跑第三方模型（Kimi 等）时，
langchain-anthropic 认不出模型名，会落到一个很小的兜底输出上限，报告写不完就
被截断——而返回值本身完全合法，没有任何报错。

#89「调用 kimi 失败 401」：用第三方模型名走 anthropic 通道却没配端点，请求会被
发到 api.anthropic.com，拿第三方 token 认证，报一句看不懂的 invalid x-api-key。
"""

import logging

import pytest

from tradingagents.llm_clients.anthropic_client import (
    _THIRD_PARTY_DEFAULT_MAX_TOKENS,
    AnthropicClient,
)
from tradingagents.llm_clients.base_client import warn_if_truncated
from tradingagents.llm_clients.openai_client import OpenAIClient


class FakeResponse:
    """够用的 AIMessage 替身：只需要 response_metadata。"""

    def __init__(self, metadata):
        self.response_metadata = metadata
        self.content = "写到一半就断了的报告"


# ---------------------------------------------------------------------------
# #91 输出上限
# ---------------------------------------------------------------------------


def test_third_party_model_gets_explicit_max_tokens():
    """Kimi 这类第三方模型必须拿到显式上限，不能听凭 langchain 的小兜底值。"""
    client = AnthropicClient(
        "kimi-k2-0905-preview", base_url="https://api.kimi.com/coding/"
    )
    llm = client.get_llm()

    assert llm.max_tokens == _THIRD_PARTY_DEFAULT_MAX_TOKENS


def test_real_claude_model_keeps_provider_default():
    """真 Claude 模型不要动——它的上限比我们的默认值大得多。"""
    llm = AnthropicClient("claude-sonnet-4-6").get_llm()

    assert llm.max_tokens > _THIRD_PARTY_DEFAULT_MAX_TOKENS


def test_dated_claude_model_id_is_not_treated_as_third_party():
    """带日期的正规 Claude ID 不在我们的目录里，但绝不能被砍到第三方默认值。"""
    llm = AnthropicClient("claude-sonnet-4-5-20250929").get_llm()

    assert llm.max_tokens > _THIRD_PARTY_DEFAULT_MAX_TOKENS


def test_explicit_max_tokens_wins():
    """用户显式配置的上限优先于任何默认值。"""
    client = AnthropicClient(
        "kimi-k2-0905-preview",
        base_url="https://api.kimi.com/coding/",
        max_tokens=32000,
    )

    assert client.get_llm().max_tokens == 32000


def test_openai_client_forwards_max_tokens():
    """OpenAI 兼容通道同样要能配上限，否则这个配置项对半数用户是死的。"""
    client = OpenAIClient(
        "deepseek-chat", provider="deepseek", api_key="test-key", max_tokens=12345
    )

    assert client.get_llm().max_tokens == 12345


@pytest.mark.parametrize(
    "metadata",
    [
        {"stop_reason": "max_tokens"},                       # Anthropic
        {"finish_reason": "length"},                         # OpenAI 兼容 Chat
        {"finish_reason": "MAX_TOKENS"},                     # Gemini（大写）
        # OpenAI Responses API —— `openai` 是**默认 provider** 且走这条路径，
        # 漏掉它等于默认配置下这个告警根本不会响（codex P1）
        {"status": "incomplete",
         "incomplete_details": {"reason": "max_output_tokens"}},
    ],
)
def test_truncated_response_is_reported(metadata, caplog):
    """被截断必须喊出来——否则用户只会以为模型没写完（#91 的真正痛点）。"""
    with caplog.at_level(logging.WARNING):
        warn_if_truncated(FakeResponse(metadata), "some-model")

    assert any("max_tokens" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "metadata",
    [
        {"stop_reason": "end_turn"},
        {"finish_reason": "stop"},
        {"finish_reason": "STOP"},
        # 因为别的原因 incomplete（如内容过滤）不是输出上限，不该报 max_tokens
        {"status": "incomplete", "incomplete_details": {"reason": "content_filter"}},
        {"status": "completed"},
        {},
    ],
)
def test_normal_response_is_not_reported(metadata, caplog):
    """正常收尾不要报警，否则告警变噪音就没人看了。"""
    with caplog.at_level(logging.WARNING):
        warn_if_truncated(FakeResponse(metadata), "some-model")

    assert not caplog.records


# ---------------------------------------------------------------------------
# #89 Anthropic 兼容端点
# ---------------------------------------------------------------------------


def test_third_party_model_without_endpoint_fails_loudly(monkeypatch):
    """没配端点就用第三方模型名 → 当场说清楚，而不是让 Anthropic 回一句 401。"""
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    with pytest.raises(RuntimeError) as exc:
        AnthropicClient("kimi-k2-0905-preview").get_llm()

    message = str(exc.value)
    assert "backend_url" in message
    assert "ANTHROPIC_API_KEY" in message
    # 必须点破这个常见误配：ANTHROPIC_AUTH_TOKEN 是 Claude Code CLI 的写法
    assert "ANTHROPIC_AUTH_TOKEN" in message


def test_anthropic_base_url_env_is_honoured(monkeypatch):
    """端点也允许走环境变量给，不是只能写 config。"""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.kimi.com/coding/")

    llm = AnthropicClient("kimi-k2-0905-preview").get_llm()

    assert "kimi" in str(llm.anthropic_api_url)


def test_claude_model_without_endpoint_still_works(monkeypatch):
    """真 Claude 模型不配端点是完全正常的用法，不能被新校验误伤。"""
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    assert AnthropicClient("claude-sonnet-4-6").get_llm() is not None
