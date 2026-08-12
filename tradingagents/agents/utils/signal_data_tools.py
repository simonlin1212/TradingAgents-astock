from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_profit_forecast(
    ticker: Annotated[str, "A-stock code (e.g. 688017)"],
    curr_date: Annotated[str, "Analysis date in YYYY-MM-DD format (required)"],
) -> str:
    """
    Retrieve consensus EPS forecasts with forward valuation metrics.
    Returns analyst coverage count, EPS range, forward PE, PEG, and PE digestion time.
    Uses the configured signal_data vendor.

    ⚠️ curr_date 是**必填**：一致预期只有"当前"版本，没有历史时点值。数据层靠这个
    参数判断是不是在复盘历史，并在正文顶部加未来函数告警。给默认值等于没设防——
    模型按 {"ticker": "600519"} 调用时 curr_date 为空串，判定为"非历史"，告警永远
    不触发，今天的预测就被当成分析日当天的事实（v0.5.5 加告警，v0.5.8 才真正生效）。

    Args:
        ticker (str): A-stock code
        curr_date (str): Analysis date, used to flag look-ahead when historical
    Returns:
        str: Consensus forecast report with valuation metrics
    """
    return route_to_vendor("get_profit_forecast", ticker, curr_date)


@tool
def get_hot_stocks(
    curr_date: Annotated[str, "Date in YYYY-MM-DD format, empty for today"] = "",
) -> str:
    """
    Retrieve today's strong stocks with topic attribution reason tags.
    Shows WHY stocks surged (e.g. '算力租赁+AI政务'), curated by 同花顺 editorial team.
    Includes theme frequency analysis.
    Uses the configured signal_data vendor.
    Args:
        curr_date (str): Date in YYYY-MM-DD format, empty string for today
    Returns:
        str: Hot stocks list with reason tags and theme frequency
    """
    return route_to_vendor("get_hot_stocks", curr_date)


@tool
def get_northbound_flow(
    curr_date: Annotated[str, "Date in YYYY-MM-DD format"],
    include_history: Annotated[
        bool, "Include historical daily data (last 20 trading days)"
    ] = False,
) -> str:
    """
    Retrieve northbound capital flow (沪深股通) data.
    Realtime: minute-level cumulative net buying for HGT + SGT.
    History (optional): daily-level data for trend analysis.
    Uses the configured signal_data vendor.
    Args:
        curr_date (str): Date in YYYY-MM-DD format
        include_history (bool): Whether to include historical daily data
    Returns:
        str: Northbound capital flow report with bullish/bearish signal
    """
    return route_to_vendor("get_northbound_flow", curr_date, include_history)


@tool
def get_concept_blocks(
    ticker: Annotated[str, "A-stock code (e.g. 688017)"],
) -> str:
    """
    Retrieve concept/sector/region blocks that a stock belongs to.
    Shows industry (申万), concept themes (e.g. 机器人概念, 减速器), and region.
    Each block includes current day's change percentage.
    Uses the configured signal_data vendor.
    Args:
        ticker (str): A-stock code
    Returns:
        str: Concept and sector block membership with daily changes
    """
    return route_to_vendor("get_concept_blocks", ticker)


@tool
def get_fund_flow(
    ticker: Annotated[str, "A-stock code"],
    curr_date: Annotated[str, "Date in YYYY-MM-DD format"],
    include_history: Annotated[
        bool, "Include historical daily fund flow (last 20 days)"
    ] = True,
) -> str:
    """
    Retrieve individual stock fund flow (main force vs retail investor).
    Realtime: minute-level super/large/medium/small order flow.
    History: daily net inflow by order size for 20 trading days.
    Uses the configured signal_data vendor.
    Args:
        ticker (str): A-stock code
        curr_date (str): Date in YYYY-MM-DD format
        include_history (bool): Include 20-day historical daily flow
    Returns:
        str: Fund flow report with main force signal
    """
    return route_to_vendor("get_fund_flow", ticker, curr_date, include_history)


@tool
def get_dragon_tiger_board(
    ticker: Annotated[str, "A-stock code (e.g. 000858)"],
    curr_date: Annotated[str, "Date in YYYY-MM-DD format"],
    look_back_days: Annotated[int, "Days to look back (default 30)"] = 30,
) -> str:
    """
    Retrieve dragon-tiger board (龙虎榜) data for a stock.
    Shows recent LHB appearances, top buyer/seller seats (营业部),
    and institutional involvement. Key signal for hot money tracking.
    Args:
        ticker (str): A-stock code
        curr_date (str): Date in YYYY-MM-DD format
        look_back_days (int): How many days back to search
    Returns:
        str: LHB appearances with seat details and institutional activity
    """
    return route_to_vendor("get_dragon_tiger_board", ticker, curr_date, look_back_days)


@tool
def get_lockup_expiry(
    ticker: Annotated[str, "A-stock code (e.g. 000858)"],
    curr_date: Annotated[str, "Date in YYYY-MM-DD format"],
    forward_days: Annotated[int, "Days forward to check (default 90)"] = 90,
) -> str:
    """
    Retrieve lockup expiry (限售解禁) schedule for a stock.
    Shows historical unlock records and upcoming expiry calendar
    with impact metrics (unlock quantity, market cap ratio).
    Args:
        ticker (str): A-stock code
        curr_date (str): Date in YYYY-MM-DD format
        forward_days (int): How many days forward to check
    Returns:
        str: Lockup expiry schedule with impact assessment
    """
    return route_to_vendor("get_lockup_expiry", ticker, curr_date, forward_days)


@tool
def get_industry_comparison(
    ticker: Annotated[str, "A-stock code (e.g. 000858)"],
    curr_date: Annotated[str, "Date in YYYY-MM-DD format"],
) -> str:
    """
    Retrieve industry sector performance comparison (行业横向对比).
    Shows all 90 THS industries ranked by performance with turnover,
    net capital flow, and leading stocks. Useful for sector rotation analysis.
    Args:
        ticker (str): A-stock code (used to identify relevant sector)
        curr_date (str): Date in YYYY-MM-DD format
    Returns:
        str: Industry performance ranking with key metrics
    """
    return route_to_vendor("get_industry_comparison", ticker, curr_date)
