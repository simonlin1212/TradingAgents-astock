"""Aggregation helpers for KOL radar."""

from __future__ import annotations

from collections import Counter


def mention_counts(signals) -> list[tuple[str, int]]:
    counts = Counter(signal.symbol for signal in signals)
    return counts.most_common()
