"""LangChain tools for KOL radar data."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.kol.service import KolRadarService


@tool
def get_kol_summary(
    symbol: Annotated[str, "6-digit A-stock code, e.g. 300750"],
    trade_date: Annotated[str, "Trade date in yyyy-mm-dd format"],
    lookback_days: Annotated[int, "How many calendar days to look back"] = 7,
) -> str:
    """Return recent confirmed KOL signals for a stock."""
    return KolRadarService().get_kol_summary(
        symbol=symbol,
        trade_date=date.fromisoformat(trade_date),
        lookback_days=lookback_days,
    )


@tool
def get_kol_hotspots(
    trade_date: Annotated[str, "Trade date in yyyy-mm-dd format"],
    top_n: Annotated[int, "Maximum number of hot stocks to return"] = 10,
) -> str:
    """Return daily KOL hot stocks."""
    return KolRadarService().get_kol_hotspots(
        trade_date=date.fromisoformat(trade_date),
        top_n=top_n,
    )


@tool
def get_author_score(
    author: Annotated[str, "KOL author id"],
) -> str:
    """Return a KOL author's current score and sample status."""
    return KolRadarService().get_author_score(author)
