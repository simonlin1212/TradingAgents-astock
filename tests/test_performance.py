"""决策绩效统计（#61）。

决策与真实收益一直都在记忆日志里，缺的只是汇总。这些用例除了验算术，更重要的是
锁死三条"不许骗人"的规则：

1. 解析不出收益的记录必须**跳过**，不能当成 0%——那会把统计悄悄拉向中性；
2. 样本太小要**自己说出来**，不能让人把 3 条记录的胜率当结论；
3. 报告必须写明**这不是回测**，且未结算时不能显示一堆 0%。
"""

import pytest

from tradingagents.performance import (
    MIN_MEANINGFUL_SAMPLE,
    format_report,
    load_records,
    summarize,
)


def entry(date, ticker, rating, raw=None, alpha=None, holding="5d", pending=False):
    return {
        "date": date, "ticker": ticker, "rating": rating,
        "pending": pending, "raw": raw, "alpha": alpha, "holding": holding,
        "decision": "", "reflection": "",
    }


def many(n, rating="Buy", raw="+5.0%", alpha="+2.0%", ticker="600519"):
    return [entry(f"2026-01-{i+1:02d}", ticker, rating, raw, alpha) for i in range(n)]


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def test_pending_entries_are_excluded():
    records = load_records([
        entry("2026-01-01", "600519", "Buy", pending=True),
        entry("2026-01-02", "600519", "Buy", "+3.0%", "+1.0%"),
    ])
    assert len(records) == 1
    assert records[0].date == "2026-01-02"


def test_unparseable_return_is_skipped_not_zeroed():
    """把解析失败当成 0% 会把统计悄悄拉向中性——必须跳过。"""
    records = load_records([
        entry("2026-01-01", "600519", "Buy", "n/a", "n/a"),
        entry("2026-01-02", "600519", "Buy", "", ""),
        entry("2026-01-03", "600519", "Buy", "+3.0%", "+1.0%"),
    ])
    assert len(records) == 1


def test_percent_parsing():
    r = load_records([entry("2026-01-01", "600519", "Buy", "+5.0%", "-1.5%")])[0]
    assert r.raw_return == pytest.approx(0.05)
    assert r.alpha_return == pytest.approx(-0.015)


def test_missing_alpha_is_none_not_zero():
    """alpha 缺失和 alpha 为 0 是两回事，不能混。"""
    r = load_records([entry("2026-01-01", "600519", "Buy", "+5.0%", None)])[0]
    assert r.alpha_return is None


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


def test_up_rate_and_averages():
    s = summarize([
        entry("2026-01-01", "600519", "Buy", "+10.0%", "+5.0%"),
        entry("2026-01-02", "600519", "Buy", "-4.0%", "-2.0%"),
        entry("2026-01-03", "600519", "Buy", "+6.0%", "+3.0%"),
    ])
    o = s["overall"]
    assert o["count"] == 3
    assert o["up_rate"] == pytest.approx(2 / 3)
    assert o["avg_return"] == pytest.approx(0.04)
    assert o["best"] == pytest.approx(0.10)
    assert o["worst"] == pytest.approx(-0.04)


def test_outperform_rate_ignores_records_without_alpha():
    s = summarize([
        entry("2026-01-01", "600519", "Buy", "+10.0%", "+5.0%"),
        entry("2026-01-02", "600519", "Buy", "+1.0%", None),
    ])
    # 只有 1 条有 alpha，且为正
    assert s["overall"]["outperform_rate"] == pytest.approx(1.0)


def test_grouping_by_rating_and_ticker():
    s = summarize([
        entry("2026-01-01", "600519", "Buy", "+10.0%", "+5.0%"),
        entry("2026-01-02", "000001", "Sell", "-4.0%", "-2.0%"),
    ])
    assert s["by_rating"]["Buy"]["count"] == 1
    assert s["by_rating"]["Sell"]["count"] == 1
    assert set(s["by_ticker"]) == {"600519", "000001"}


def test_empty_rating_groups_are_dropped():
    """没有样本的评级不该出现在报表里凑行数。"""
    s = summarize([entry("2026-01-01", "600519", "Buy", "+1.0%", "+1.0%")])
    assert set(s["by_rating"]) == {"Buy"}


# ---------------------------------------------------------------------------
# 评级区分度
# ---------------------------------------------------------------------------


def test_monotonic_needs_every_tier():
    """只有两三档有样本时不给结论——那样判断单调性没有意义。"""
    s = summarize(many(5, "Buy") + many(5, "Sell", "-5.0%", "-3.0%"))
    assert s["rating_monotonic"] is None


def test_monotonic_true_when_ratings_rank_correctly():
    entries = []
    for rating, alpha in [
        ("Buy", "+5.0%"), ("Overweight", "+3.0%"), ("Hold", "+1.0%"),
        ("Underweight", "-1.0%"), ("Sell", "-3.0%"),
    ]:
        entries += many(3, rating, "+1.0%", alpha)
    assert summarize(entries)["rating_monotonic"] is True


def test_monotonic_false_when_ratings_are_inverted():
    entries = []
    for rating, alpha in [
        ("Buy", "-3.0%"), ("Overweight", "+3.0%"), ("Hold", "+1.0%"),
        ("Underweight", "-1.0%"), ("Sell", "+5.0%"),
    ]:
        entries += many(3, rating, "+1.0%", alpha)
    assert summarize(entries)["rating_monotonic"] is False


# ---------------------------------------------------------------------------
# 不许骗人
# ---------------------------------------------------------------------------


def test_small_sample_is_flagged():
    s = summarize(many(3))
    assert s["sample_is_meaningful"] is False
    assert "噪音" in format_report(s)


def test_large_sample_is_not_flagged():
    s = summarize(many(MIN_MEANINGFUL_SAMPLE))
    assert s["sample_is_meaningful"] is True
    assert "噪音" not in format_report(s)


def test_report_without_resolved_entries_says_so():
    """一条都没结算时要说明怎么才会结算，而不是显示一堆 0%。"""
    report = format_report(summarize([
        entry("2026-01-01", "600519", "Buy", pending=True),
    ]))
    assert "暂无可统计" in report
    assert "0.0%" not in report


def test_report_states_it_is_not_a_backtest():
    """必须写明这不是回测、不是策略业绩，否则很容易被当成收益承诺。"""
    report = format_report(summarize(many(MIN_MEANINGFUL_SAMPLE)))
    assert "不是回测" in report
    assert "不构成任何投资建议" in report


def test_report_highlights_alpha_over_raw_return():
    """A 股 beta 强，光看绝对收益会高估判断力——报告要点破这一点。"""
    report = format_report(summarize(many(MIN_MEANINGFUL_SAMPLE)))
    assert "alpha" in report


# ---------------------------------------------------------------------------
# codex 审计补的两条
# ---------------------------------------------------------------------------


def test_bearish_call_that_fell_counts_as_correct():
    """给 Sell 之后股价跌了＝判断正确。

    原实现只看"收益是否为正"，会把这种正确判断记成失败、把随后的上涨记成成功，
    于是所谓"胜率"根本不是决策准确率（codex P2）。
    """
    s = summarize([
        entry("2026-01-01", "600519", "Sell", "-8.0%", "-5.0%"),
        entry("2026-01-02", "000001", "Sell", "+8.0%", "+5.0%"),
    ])
    o = s["overall"]
    assert o["direction_accuracy"] == pytest.approx(0.5)
    assert o["up_rate"] == pytest.approx(0.5)      # 标的涨跌各一，与判断对错无关


def test_bullish_and_bearish_both_correct():
    s = summarize([
        entry("2026-01-01", "600519", "Buy", "+8.0%", "+5.0%"),
        entry("2026-01-02", "000001", "Sell", "-8.0%", "-5.0%"),
    ])
    assert s["overall"]["direction_accuracy"] == pytest.approx(1.0)


def test_hold_is_excluded_from_direction_accuracy():
    """Hold 没有表态，不该被判对错。"""
    s = summarize([
        entry("2026-01-01", "600519", "Hold", "+8.0%", "+5.0%"),
        entry("2026-01-02", "000001", "Buy", "+8.0%", "+5.0%"),
    ])
    o = s["overall"]
    assert o["directional_count"] == 1
    assert o["direction_accuracy"] == pytest.approx(1.0)


def test_direction_accuracy_is_none_without_directional_ratings():
    s = summarize([entry("2026-01-01", "600519", "Hold", "+8.0%", "+5.0%")])
    assert s["overall"]["direction_accuracy"] is None


def test_holding_days_with_d_suffix_is_parsed():
    """记忆日志写的是 `5d`，直接 int() 会抛 → 平均持有期永远缺失（codex P2）。"""
    s = summarize([
        entry("2026-01-01", "600519", "Buy", "+1.0%", "+1.0%", holding="5d"),
        entry("2026-01-02", "600519", "Buy", "+1.0%", "+1.0%", holding="7d"),
    ])
    assert s["avg_holding_days"] == pytest.approx(6.0)


def test_report_shows_average_holding_days():
    s = summarize(many(MIN_MEANINGFUL_SAMPLE))
    assert "平均持有" in format_report(s)


def test_report_warns_that_up_rate_is_not_accuracy():
    """报告必须点破：上涨占比不是判断准确率，否则读者会看反。"""
    report = format_report(summarize(many(MIN_MEANINGFUL_SAMPLE)))
    assert "方向正确率" in report
    assert "判断正确" in report


def test_direction_accuracy_significance_uses_its_own_denominator():
    """总样本够、但有方向的评级只有 1 条时，必须单独警告。

    `direction_accuracy` 排除了 Hold，拿"已结算总数"做显著性判据会高估——
    20 条已结算里只有 1 条有方向时，提示被抑制，报告却敢显示"方向正确率 100%"
    （codex 终轮指出）。
    """
    entries = many(MIN_MEANINGFUL_SAMPLE - 1, "Hold", "+1.0%", "+1.0%")
    entries += [entry("2026-02-01", "600519", "Buy", "+5.0%", "+3.0%")]

    s = summarize(entries)
    assert s["sample_is_meaningful"] is True          # 总数够
    assert s["direction_sample_is_meaningful"] is False  # 但有方向的只有 1 条
    assert s["overall"]["direction_accuracy"] == pytest.approx(1.0)

    report = format_report(s)
    assert "有方向的评级只有 1 条" in report
    assert "方向正确率" in report


def test_no_direction_warning_when_directional_sample_is_enough():
    s = summarize(many(MIN_MEANINGFUL_SAMPLE, "Buy", "+5.0%", "+2.0%"))

    assert s["direction_sample_is_meaningful"] is True
    assert "有方向的评级只有" not in format_report(s)
