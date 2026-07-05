"""Market data binding hooks for KOL signals."""

from __future__ import annotations

from dataclasses import replace

from .models import KolSignal


def mark_market_snapshot_missing(signal: KolSignal) -> KolSignal:
    """Return a signal with explicit missing-market-data precision."""
    return replace(signal, snapshot_precision="missing")
