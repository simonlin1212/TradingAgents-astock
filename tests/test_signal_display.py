"""Keep intermediate proposals distinct from the final five-tier rating."""

from web.signal_display import final_rating_display, trader_action_display


def test_underweight_is_not_displayed_as_hold():
    color, label, meaning = final_rating_display("Underweight")
    assert label == "低配 / 减仓"
    assert "降低仓位" in meaning
    assert color != final_rating_display("Hold")[0]


def test_unknown_rating_is_not_displayed_as_hold():
    assert final_rating_display("N/A")[1] == "评级未识别"


def test_trader_action_uses_explicit_action_not_reasoning():
    report = "**Action**: Sell\n\n**Reasoning**: 买入情景仍有不确定性。"
    assert trader_action_display(report) == "卖出 / 减仓"
    assert trader_action_display("Reasoning: some investors say Sell") is None
