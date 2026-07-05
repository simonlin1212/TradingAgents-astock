"""Public interface for KOL radar workflows."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from .extractors import extract_signals
from .models import AuthorScore, RawKolPost
from .storage import KolStorage

RISK_DISCLOSURE = "仅供研究辅助，不构成投资建议。"


class KolRadarService:
    """Facade used by CLI, agent tools, Horizon, and Obsidian sync."""

    def __init__(self, db_path: str | Path | None = None, storage: KolStorage | None = None):
        self.storage = storage or KolStorage(db_path)

    def ingest_raw_posts(
        self,
        posts: list[RawKolPost],
        stock_name_map: dict[str, str] | None = None,
    ) -> int:
        signal_count = 0
        for post in posts:
            self.storage.upsert_raw_post(post)
            signals = extract_signals(post, stock_name_map=stock_name_map)
            self.storage.upsert_signals(signals)
            signal_count += len(signals)
        return signal_count

    def update_author_scores(self) -> None:
        signals = self.storage.list_signals()
        by_author: dict[str, int] = {}
        for signal in signals:
            by_author[signal.author_id] = by_author.get(signal.author_id, 0) + 1
        for author_id, count in by_author.items():
            if count < 10:
                score = AuthorScore(author_id=author_id, sample_count=count, overall_score=None, status="观察中")
            else:
                score = AuthorScore(author_id=author_id, sample_count=count, overall_score=5.0, status="可评分")
            self.storage.upsert_author_score(score)

    def get_kol_summary(self, symbol: str, trade_date: date, lookback_days: int = 7) -> str:
        start = datetime.combine(trade_date - timedelta(days=lookback_days), time.min, tzinfo=timezone.utc)
        signals = self.storage.list_signals(symbol=symbol, since=start)
        if not signals:
            return f"KOL 信息雷达未找到 {symbol} 最近 {lookback_days} 天的确认信号。\n\n{RISK_DISCLOSURE}"

        lines = [
            f"### KOL 信息雷达摘要: {symbol}",
            f"- 时间窗口: {lookback_days} 天",
            f"- 确认信号数: {len(signals)}",
        ]
        for signal in signals[:10]:
            published = signal.published_at.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"- {published} {signal.author_id}: {signal.action} {signal.symbol} "
                f"{signal.stock_name}; 周期={signal.horizon}; 发布价={signal.price_at_post if signal.price_at_post is not None else '[数据缺失: price_at_post]'}; "
                f"证据={signal.content_excerpt}; 来源={signal.source_url}"
            )
        lines.append("")
        lines.append(RISK_DISCLOSURE)
        return "\n".join(lines)

    def get_kol_hotspots(self, trade_date: date, top_n: int = 10) -> str:
        day_start = datetime.combine(trade_date, time.min, tzinfo=timezone.utc)
        signals = self.storage.list_signals(since=day_start)
        counts: dict[str, int] = {}
        names: dict[str, str] = {}
        for signal in signals:
            counts[signal.symbol] = counts.get(signal.symbol, 0) + 1
            names[signal.symbol] = signal.stock_name
        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:top_n]
        if not ranked:
            return f"KOL 信息雷达今日暂无热点。\n\n{RISK_DISCLOSURE}"
        lines = ["### 今日 KOL 热点", "| 股票 | 名称 | 提及数 |", "| --- | --- | --- |"]
        for symbol, count in ranked:
            lines.append(f"| {symbol} | {names.get(symbol, '')} | {count} |")
        lines.extend(["", RISK_DISCLOSURE])
        return "\n".join(lines)

    def get_author_score(self, author: str) -> str:
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT * FROM author_scores WHERE author_id = ?",
                (author,),
            ).fetchone()
        if not row:
            return f"{author}: 暂无评分。\n\n{RISK_DISCLOSURE}"
        score = row["overall_score"] if row["overall_score"] is not None else "观察中"
        return (
            f"{author}: 样本数={row['sample_count']}, 评分={score}, 状态={row['status']}。\n\n"
            f"{RISK_DISCLOSURE}"
        )
