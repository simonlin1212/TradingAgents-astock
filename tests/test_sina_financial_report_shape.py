"""Regression tests for the Sina financial-statement response shape.

Sina moved the payload from ``result.data.<fzb|lrb|llb>`` (a flat list of rows)
to ``result.data.report_list{报告期: {..., data: [{item_title, item_value}]}}``.

The old parser only read the former, so all three statements silently came back
as "No ... data found" instead of raising — the agent then reported "this stock
has no financial statements" as a fact.
"""

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows import a_stock

# Shape returned by the API since ~2026-10.
NEW_SHAPE = {
    "result": {
        "status": {"code": 0},
        "data": {
            "report_count": "2",
            "report_date": [
                {
                    "date_value": "20260630",
                    "date_description": "2026半年报",
                    "date_type": 2,
                },
                {
                    "date_value": "20260331",
                    "date_description": "2026一季报",
                    "date_type": 1,
                },
            ],
            "report_list": {
                "20260630": {
                    "rType": "合并期末",
                    "data": [
                        {"item_field": "", "item_title": "流动资产", "item_value": ""},
                        {
                            "item_field": "CURFDS",
                            "item_title": "货币资金",
                            "item_value": "53518798979.08",
                        },
                    ],
                },
                "20260331": {
                    "rType": "合并期末",
                    "data": [
                        {
                            "item_field": "CURFDS",
                            "item_title": "货币资金",
                            "item_value": "50000000000.0",
                        },
                    ],
                },
            },
        },
    }
}

# Shape the parser was originally written against.
LEGACY_SHAPE = {
    "result": {
        "data": {
            "fzb": [
                {"报告日": "20260630", "货币资金": "53518798979.08"},
                {"报告日": "20260331", "货币资金": "50000000000.0"},
            ]
        }
    }
}


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_new_report_list_shape_is_parsed(mock_get):
    """The newer payload shape must produce real rows, not an empty table."""
    mock_get.return_value = _response(NEW_SHAPE)

    out = a_stock.get_balance_sheet("600519", "quarterly", "2026-09-30")

    assert "No balance sheet data found" not in out
    assert "货币资金" in out
    assert "53518798979.08" in out
    assert "2026-06-30" in out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_legacy_shape_still_parsed(mock_get):
    """Compatibility: the shape the parser was written for must keep working."""
    mock_get.return_value = _response(LEGACY_SHAPE)

    out = a_stock.get_balance_sheet("600519", "quarterly", "2026-09-30")

    assert "No balance sheet data found" not in out
    assert "53518798979.08" in out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_all_three_statements_parse_the_new_shape(mock_get):
    mock_get.return_value = _response(NEW_SHAPE)

    for getter, empty_msg in (
        (a_stock.get_balance_sheet, "No balance sheet data found"),
        (a_stock.get_cashflow, "No cash flow data found"),
        (a_stock.get_income_statement, "No income statement data found"),
    ):
        out = getter("600519", "quarterly", "2026-09-30")
        assert empty_msg not in out, out
        assert "货币资金" in out, out


@pytest.mark.unit
@patch("tradingagents.dataflows.a_stock._requests.get")
def test_unrecognised_shape_degrades_to_empty_table(mock_get):
    """An unknown payload must not raise; it degrades to "no data"."""
    mock_get.return_value = _response({"result": {"data": {"unexpected": []}}})

    out = a_stock.get_balance_sheet("600519", "quarterly", "2026-09-30")

    assert "No balance sheet data found" in out
