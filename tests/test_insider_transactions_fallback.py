"""Tests for the east-money HTTP fallback of ``get_insider_transactions``.

mootdx F10 rides the TDX TCP 7709 channel, which several servers currently
answer with a 2-byte count stub (see issue #98) — so F10 used to be the only
core data item with **no** fallback: the 解禁监控师 always lost its
"内部人交易" input. These tests pin the fallback behaviour and the unit
handling (高管增减持以股计, 股东增减持以万股计).
"""

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows import a_stock

AJAX_PAYLOAD = {
    "sjkzr": [{"HOLDER_NAME": "贵州省人民政府国有资产监督管理委员会"}],
    "gdrs": [
        {
            "END_DATE": "2026-06-30 00:00:00",
            "HOLDER_TOTAL_NUM": 296404,
            "TOTAL_NUM_RATIO": 21.8972,
            "AVG_FREE_SHARES": 4217,
            "HOLD_FOCUS": "非常分散",
        }
    ],
    "sdgd": [
        {
            "END_DATE": "2026-06-30 00:00:00",
            "HOLDER_RANK": 1,
            "HOLDER_NAME": "中国贵州茅台酒厂(集团)有限责任公司",
            "HOLD_NUM": 681282935,
            "HOLD_NUM_RATIO": 54.5,
            "HOLD_NUM_CHANGE": None,
            "CHANGE_RATIO": None,
        }
    ],
    "sdltgd": [
        {
            "END_DATE": "2026-06-30 00:00:00",
            "HOLDER_RANK": 3,
            "HOLDER_NAME": "香港中央结算有限公司",
            "HOLD_NUM": 53711700,
            "FREE_HOLDNUM_RATIO": 4.3,
            "HOLD_NUM_CHANGE": -5021400,
            "CHANGE_RATIO": -8.55,
        }
    ],
}

EXEC_ROWS = [
    {
        "CHANGE_DATE": "2025-06-04 00:00:00",
        "EXECUTIVE_NAME": "邹伟民",
        "POSITION": "董事长",
        "CHANGE_NUM": -300000,  # 单位：股
        "CHANGE_RATIO": None,
        "AVERAGE_PRICE": 17.64,
        "CHANGE_REASON": "竞价交易",
    }
]

HOLDER_ROWS = [
    {
        "NOTICE_DATE": "2020-11-12 00:00:00",
        "HOLDER_NAME": "扬州承源投资咨询部(有限合伙)",
        "DIRECTION": "减持",
        "CHANGE_NUM": 44.35,  # 单位：万股，恒为正，方向看 DIRECTION
        "AFTER_HOLDER_NUM": 544.65,
        "HOLD_RATIO": 1.9,
        "TRADE_AVERAGE_PRICE": 17.13,
    }
]


def _ajax_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def _fake_datacenter(report_name, **kwargs):
    if report_name == "RPT_EXECUTIVE_HOLD_CHANGE":
        return EXEC_ROWS
    if report_name == "RPT_SHARE_HOLDER_INCREASE":
        return HOLDER_ROWS
    return []


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._eastmoney_datacenter", _fake_datacenter)
@patch("tradingagents.dataflows.a_stock._em_get")
@patch("tradingagents.dataflows.a_stock._mootdx_call")
def test_falls_back_to_eastmoney_when_mootdx_fails(mock_mootdx, mock_em_get):
    mock_mootdx.side_effect = RuntimeError("通达信服务器不可用")
    mock_em_get.return_value = _ajax_response(AJAX_PAYLOAD)

    out = a_stock.get_insider_transactions("600519")

    assert "东方财富" in out
    assert mock_mootdx.called
    # 每个分节都要有
    for section in ("实际控制人", "股东户数变化", "十大股东", "十大流通股东",
                    "高管增减持", "股东增减持"):
        assert section in out, section
    # 值与单位
    assert "贵州省人民政府国有资产监督管理委员会" in out
    assert "296404" in out
    assert "+21.90%" in out
    assert "6.81亿股" in out
    assert "54.50%" in out
    assert "减持 502.14万股" in out  # sdltgd HOLD_NUM_CHANGE 以股为单位
    assert "减持 30.00万股" in out  # 高管 -300000 股
    assert "减持 44.35万股" in out  # 股东增减持本来就是万股，不能再换算


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._em_get")
@patch("tradingagents.dataflows.a_stock._eastmoney_datacenter", _fake_datacenter)
@patch("tradingagents.dataflows.a_stock._mootdx_call")
def test_mootdx_text_is_preferred_when_available(mock_mootdx, mock_em_get):
    mock_mootdx.return_value = "【1.股东研究】\n中国贵州茅台酒厂(集团)有限责任公司"

    out = a_stock.get_insider_transactions("600519")

    assert "mootdx F10" in out
    assert "中国贵州茅台酒厂" in out
    mock_em_get.assert_not_called()


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._eastmoney_datacenter", _fake_datacenter)
@patch("tradingagents.dataflows.a_stock._em_get")
@patch("tradingagents.dataflows.a_stock._mootdx_call")
def test_empty_mootdx_text_also_falls_back(mock_mootdx, mock_em_get):
    """mootdx 返回空字符串（而不是抛异常）时同样要兜底。"""
    mock_mootdx.return_value = "   "
    mock_em_get.return_value = _ajax_response(AJAX_PAYLOAD)

    out = a_stock.get_insider_transactions("600519")

    assert "东方财富" in out
    assert "十大股东" in out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._eastmoney_datacenter", lambda *a, **k: [])
@patch("tradingagents.dataflows.a_stock._em_get")
@patch("tradingagents.dataflows.a_stock._mootdx_call")
def test_all_sections_missing_reports_no_data(mock_mootdx, mock_em_get):
    mock_mootdx.side_effect = RuntimeError("down")
    mock_em_get.return_value = _ajax_response({})

    out = a_stock.get_insider_transactions("600519")

    assert "No insider/shareholder data found" in out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._em_get")
@patch("tradingagents.dataflows.a_stock._mootdx_call")
def test_fallback_failure_is_reported_not_raised(mock_mootdx, mock_em_get):
    mock_mootdx.side_effect = RuntimeError("down")
    mock_em_get.side_effect = RuntimeError("proxy exploded")

    out = a_stock.get_insider_transactions("600519")

    assert "Error retrieving insider/shareholder data" in out
