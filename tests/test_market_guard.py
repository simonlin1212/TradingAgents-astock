"""非 A 股代码必须当场报错，不能拿去查 A 股数据源（#43）。

港股代码是 4~5 位数字或带 `.HK`，此前会被 `_normalize_ticker` **原样放行**，
然后拿去问 mootdx / 腾讯 / 东财。这些源对不存在的代码往往不报错，只返回空值或
僵尸报价（北交所 920 号段踩过同类问题），于是模型会拿着一份看起来正常、实际
属于别的市场的数据写完整篇报告——报告里完全看不出来。

这里锁的是两侧：非 A 股必须被拦下，A 股的各种写法一个都不能被误伤。
"""

import pytest

from tradingagents.dataflows.a_stock import _normalize_ticker


# ---------------------------------------------------------------------------
# A 股照常工作（防止防护误伤）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("600519", "600519"),        # 沪市主板
        ("000001", "000001"),        # 深市主板
        ("300750", "300750"),        # 创业板
        ("688017", "688017"),        # 科创板
        ("920002", "920002"),        # 北交所新号段
        ("SH600519", "600519"),
        ("600519.SH", "600519"),
        ("sz000001", "000001"),
        ("BJ920002", "920002"),
        ("  600519  ", "600519"),
    ],
)
def test_a_share_forms_still_pass(raw, expected):
    assert _normalize_ticker(raw) == expected


# ---------------------------------------------------------------------------
# 港股被拦下，并且说清楚去哪
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["00700", "0700.HK", "00700.HK", "9988", "09988", "0700.hk"])
def test_hk_codes_are_rejected(raw):
    with pytest.raises(ValueError) as exc:
        _normalize_ticker(raw)
    assert "港股" in str(exc.value)


def test_hk_error_points_to_the_alternative():
    """光说"不支持"不够，要告诉用户现在能用什么。"""
    with pytest.raises(ValueError) as exc:
        _normalize_ticker("00700")
    message = str(exc.value)
    assert "global-stock-data" in message
    assert "#43" in message


# ---------------------------------------------------------------------------
# 美股与畸形输入
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["AAPL", "TSLA", "BABA"])
def test_us_tickers_are_rejected(raw):
    with pytest.raises(ValueError, match="不是 A 股代码"):
        _normalize_ticker(raw)


@pytest.mark.parametrize("raw", ["700", "12", "1234567"])
def test_wrong_length_numeric_is_rejected(raw):
    """位数不对的纯数字既不是 A 股也不该被猜成别的市场，直接报错。"""
    with pytest.raises(ValueError):
        _normalize_ticker(raw)


def test_error_names_the_original_input():
    """报错要带上用户原本传进来的东西，否则不知道是哪一步出的问题。"""
    with pytest.raises(ValueError) as exc:
        _normalize_ticker("0700.HK")
    assert "0700.HK" in str(exc.value)
