"""Export KOL signals in Horizon-compatible item dictionaries."""

from __future__ import annotations

from .storage import KolStorage


def iter_horizon_items(storage: KolStorage):
    for signal in storage.list_signals():
        yield {
            "id": f"kol:{signal.platform}:{signal.signal_id}",
            "title": f"{signal.symbol} {signal.stock_name} KOL {signal.action}",
            "url": signal.source_url,
            "content": signal.content_excerpt,
            "author": signal.author_id,
            "published_at": signal.published_at.isoformat(),
            "metadata": {
                "symbol": signal.symbol,
                "action": signal.action,
                "horizon": signal.horizon,
                "source_platform": signal.platform,
                "extractor_version": signal.extractor_version,
            },
        }
