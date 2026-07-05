"""Transparent first-pass KOL scoring helpers."""

from __future__ import annotations


def sample_reliability_label(sample_count: int) -> str:
    return "观察中" if sample_count < 10 else "可评分"
