"""Tests for the shared rating heuristic and the SignalProcessor adapter.

The Portfolio Manager produces a typed PortfolioDecision via structured
output and renders it to markdown that always contains a ``**Rating**: X``
header.  The deterministic heuristic in ``tradingagents.agents.utils.rating``
is therefore sufficient to extract the rating downstream — no second LLM
call is needed — and SignalProcessor is now a thin adapter that delegates
to it.
"""

import pytest

from tradingagents.agents.utils.rating import RATINGS_5_TIER, parse_rating
from tradingagents.graph.signal_processing import SignalProcessor


# ---------------------------------------------------------------------------
# Heuristic parser
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseRating:
    def test_explicit_label_buy(self):
        assert parse_rating("Rating: Buy\nReasoning here.") == "Buy"

    def test_explicit_label_overweight(self):
        assert parse_rating("Rating: Overweight\nDetails.") == "Overweight"

    def test_explicit_label_with_markdown_bold_value(self):
        # Regression: Rating: **Sell** — markdown around the value.
        assert parse_rating("Rating: **Sell**\nExit immediately.") == "Sell"

    def test_explicit_label_with_markdown_bold_label(self):
        assert parse_rating("**Rating**: Underweight\nTrim exposure.") == "Underweight"

    def test_rendered_pm_markdown_shape(self):
        # The exact shape produced by render_pm_decision must always parse.
        text = (
            "**Rating**: Buy\n\n"
            "**Executive Summary**: Enter at $189-192, 6% portfolio cap.\n\n"
            "**Investment Thesis**: AI capex cycle intact; institutional flows constructive."
        )
        assert parse_rating(text) == "Buy"

    def test_explicit_label_wins_over_prose_with_markdown(self):
        text = (
            "The buy thesis is weakened by guidance.\n"
            "Rating: **Sell**\n"
            "Exit before earnings."
        )
        assert parse_rating(text) == "Sell"

    def test_no_rating_returns_default(self):
        assert parse_rating("No clear directional signal at this time.") == "Hold"

    def test_no_rating_custom_default(self):
        assert parse_rating("Plain prose.", default="Underweight") == "Underweight"

    def test_all_five_tiers_recognised(self):
        for r in RATINGS_5_TIER:
            assert parse_rating(f"Rating: {r}") == r


@pytest.mark.unit
class TestParseRatingChinese:
    """Chinese free-text path (issues #78 / #80).

    When output_language is Chinese and structured output falls back to
    free-text, the decision has no English ``Rating:`` header — only a
    Chinese label like ``最终评级：卖出``. These previously all defaulted
    to Hold.
    """

    def test_issue_78_exact_shape(self):
        # The exact decision shape from issue #78 that displayed HOLD.
        text = (
            "👔 最终投资建议\n"
            "研究经理：辩论复盘与最终投资计划书\n"
            "标的：贵州茅台\n"
            "辩论回合：牛熊充分交锋\n"
            "最终评级：卖出\n"
            "核心结论：熊方以详实的数据彻底拆解了牛方的黄金坑幻想。"
        )
        assert parse_rating(text) == "Sell"

    def test_cn_label_each_tier(self):
        cases = {
            "买入": "Buy", "增持": "Overweight", "持有": "Hold",
            "减持": "Underweight", "卖出": "Sell", "中性": "Hold",
        }
        for cn, en in cases.items():
            assert parse_rating(f"最终评级：{cn}\n理由若干。") == en

    def test_cn_label_with_english_rating_word(self):
        """中文标签 + 英文评级词（最终评级：Buy）。

        output_language 设为中文、模型却保留英文评级词时就是这个形状，而它躲过了
        原来每一条规则：英文标签规则要求出现 "rating"；中文标签规则只认中文评级
        词；裸英文词扫描按空白切分，"最终评级：Buy" 是一个 token，strip 又剥不掉
        全角冒号 —— 结果静默落到默认 Hold，决策评级被悄悄改写。
        """
        assert parse_rating("最终评级：Buy") == "Buy"
        assert parse_rating("最终评级：Sell\n理由若干。") == "Sell"
        assert parse_rating("投资建议：Overweight") == "Overweight"
        assert parse_rating("评级 - buy") == "Buy"

    def test_cn_label_with_english_word_all_tiers(self):
        for r in RATINGS_5_TIER:
            assert parse_rating(f"最终评级：{r}") == r

    def test_cn_label_still_prefers_chinese_term(self):
        """中文评级词仍然优先——新增的混排规则不能抢在它前面。"""
        assert parse_rating("最终评级：卖出（英文可写作 Buy）") == "Sell"

    def test_cn_label_variants(self):
        assert parse_rating("投资建议: **增持**\n分批建仓。") == "Overweight"
        assert parse_rating("评级：清仓") == "Sell"
        assert parse_rating("推荐评级 - 强烈买入") == "Buy"

    def test_cn_strong_beats_plain(self):
        # 强烈买入 must not be read as the shorter 买入 mapping (same tier here,
        # but the longest-match rule matters for correct term identification).
        assert parse_rating("最终评级：强烈卖出") == "Sell"

    def test_cn_label_wins_over_prose_term(self):
        # Prose mentions 大股东减持 (Underweight term) but the labelled rating
        # is 买入 — the label must win.
        text = (
            "分析：需警惕大股东减持压力与解禁风险。\n"
            "最终评级：买入\n"
            "综合判断上行空间显著。"
        )
        assert parse_rating(text) == "Buy"

    def test_cn_bare_term_last_resort(self):
        # No label at all, only a bare Chinese conclusion — better than Hold.
        assert parse_rating("综合来看应当卖出该标的。") == "Sell"

    def test_english_label_still_wins_in_mixed_text(self):
        # English structured render must be unaffected by the Chinese additions.
        assert parse_rating("**Rating**: Buy\n\n**投资论点**：AI 资本开支周期完好。") == "Buy"


# ---------------------------------------------------------------------------
# SignalProcessor: thin adapter over the heuristic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSignalProcessor:
    def test_returns_rating_from_pm_markdown(self):
        sp = SignalProcessor()
        md = "**Rating**: Overweight\n\n**Executive Summary**: Build gradually."
        assert sp.process_signal(md) == "Overweight"

    def test_makes_no_llm_calls(self):
        """SignalProcessor must not invoke the LLM it was constructed with —
        the rating is parseable from the rendered PM markdown directly."""
        from unittest.mock import MagicMock

        llm = MagicMock()
        sp = SignalProcessor(llm)
        sp.process_signal("Rating: Buy\nDetails.")
        llm.invoke.assert_not_called()
        llm.with_structured_output.assert_not_called()

    def test_default_when_no_rating_present(self):
        sp = SignalProcessor()
        assert sp.process_signal("Plain prose without a recommendation.") == "Hold"


@pytest.mark.unit
class TestParseRatingWordBoundary:
    """中文标签后跟英文散文时，不能把词首当成完整评级（codex 第五轮）。

    没有词边界的话 `最终评级：Buyer interest remains weak` 会被判成 Buy、
    `建议：Selling pressure is high` 判成 Sell。这类误判会写进记忆日志，
    再污染决策绩效统计——而且从报告里完全看不出来。
    """

    def test_english_prose_after_cn_label_is_not_a_rating(self):
        assert parse_rating("最终评级：Buyer interest remains weak") == "Hold"
        assert parse_rating("建议：Selling pressure is high") == "Hold"
        assert parse_rating("最终评级：Holder structure changed") == "Hold"

    def test_real_mixed_ratings_still_parse(self):
        """加了边界不能误伤正常的中英混排。"""
        assert parse_rating("最终评级：Buy") == "Buy"
        assert parse_rating("最终评级：Sell\n理由若干。") == "Sell"
        assert parse_rating("投资建议：Overweight") == "Overweight"
        assert parse_rating("评级 - buy") == "Buy"

    def test_chinese_terms_unaffected(self):
        assert parse_rating("最终评级：买入") == "Buy"
        assert parse_rating("最终评级：卖出") == "Sell"

    # 「中文标签 + 英文评级词」的边界规则前后改了三轮才收敛，每一轮都是"修了又漏"：
    #   1. 没有边界        → `Buyer interest` 判成 Buy
    #   2. `(?![A-Za-z])`  → `Sell-off risk`、`Buy2024` 仍过关
    #   3. 枚举收尾标点     → `Buy（基于风险收益比）` 反被误判成 Hold
    # 最终改成「不能延续成更长的词」这条判据。**改这条规则必须整张矩阵过一遍**，
    # 只补自己想到的那一两个用例就是上面三轮反复的成因。
    @pytest.mark.parametrize(
        "text,expected",
        [
            # —— 正常写法必须识别 ——
            ("最终评级：Buy", "Buy"),
            ("最终评级：Sell", "Sell"),
            ("投资建议：Overweight", "Overweight"),
            ("评级 - buy", "Buy"),
            ("最终评级：**Sell**", "Sell"),            # markdown 加粗
            ("最终评级：Buy。", "Buy"),                 # 中文句号
            ("最终评级：Sell，理由如下", "Sell"),        # 中文逗号
            ("最终评级：Buy：核心逻辑", "Buy"),          # 中文冒号
            ("最终评级：Buy（基于风险收益比）", "Buy"),   # 全角括号（第七轮）
            ("最终评级：Underweight(估值偏高)", "Underweight"),  # 半角括号（第七轮）
            ("最终评级：Hold【中性】", "Hold"),
            ("最终评级：Sell\n理由若干", "Sell"),       # 换行
            # —— 英文散文必须被拒（落回默认 Hold）——
            ("最终评级：Buyer interest remains weak", "Hold"),
            ("建议：Selling pressure is high", "Hold"),
            ("建议：Sell-off risk remains elevated", "Hold"),   # 连字符
            ("最终评级：Buy-side interest is weak", "Hold"),
            ("最终评级：Buy2024", "Hold"),                       # 数字后缀
            ("最终评级：Buy_target", "Hold"),                    # 下划线
            # 加粗 + 连字符：`\*{0,2}` 先消耗再判断会回溯——吃掉 `**` 被 `-` 判否后
            # 退一步只吃一个 `*`，剩下的 `*` 恰好满足边界，于是又判成 Sell（第八轮）
            ("建议：**Sell**-off risk remains elevated", "Hold"),
            ("最终评级：**Buy**-side interest is weak", "Hold"),
            ("最终评级：**Buy**2024", "Hold"),
            # 连字符要看后面：跟字母是构词（拒），跟空白只是分隔符（收，第九轮）
            ("最终评级：**Sell**- 退出", "Sell"),
            ("最终评级：Sell- 退出", "Sell"),
            # —— 中文评级词不受影响 ——
            ("最终评级：买入", "Buy"),
            ("最终评级：卖出", "Sell"),
            ("投资建议: **增持**", "Overweight"),
        ],
    )
    def test_rating_value_boundary_matrix(self, text, expected):
        assert parse_rating(text) == expected


@pytest.mark.unit
def test_rating_regex_stays_python310_compatible():
    """评级正则不能用 Python 3.11+ 才有的原子组 / 占有量词。

    pyproject 声明 `requires-python = ">=3.10"`，用 `(?>...)` 或 `*+` 会让 3.10
    用户在**导入时**就 re.error——比逻辑 bug 更硬的破坏。
    """
    import re

    from tradingagents.agents.utils import rating

    # 直接检查真正编译出来的 pattern，而不是源码文本——注释里提到这些写法是正常的
    patterns = [
        v.pattern for v in vars(rating).values() if isinstance(v, re.Pattern)
    ] + [
        v for k, v in vars(rating).items()
        if isinstance(v, str) and k.isupper() and k.endswith(("_RE", "_END", "_PREFIX", "_CONTINUATION"))
    ]
    assert patterns, "没取到任何正则，用例失去意义"

    for pat in patterns:
        assert "(?>" not in pat, f"原子组是 Python 3.11+ 特性：{pat}"
        for possessive in ("*+", "++", "?+", "}+"):
            assert possessive not in pat, f"占有量词 {possessive} 是 Python 3.11+ 特性：{pat}"
