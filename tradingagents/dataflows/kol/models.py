"""Data models for the KOL information radar."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


EXTRACTOR_VERSION = "kol-radar-v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class KolAuthor:
    id: str
    name: str
    platform: str
    profile_url: str | None = None
    sec_uid: str | None = None
    style_tags: list[str] = field(default_factory=list)
    priority: str = "medium"
    enabled: bool = True


@dataclass(frozen=True)
class RawKolPost:
    post_id: str
    author_id: str
    platform: str
    published_at: datetime
    content: str
    source_url: str
    content_hash: str
    raw_media_path: str | None = None
    collected_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KolSignal:
    signal_id: str
    post_id: str
    author_id: str
    platform: str
    symbol: str
    stock_name: str
    action: str
    action_text: str
    strength: str
    horizon: str
    reason: str
    risk_warning: str
    llm_confidence: float
    published_at: datetime
    source_url: str
    content_excerpt: str
    extractor_version: str = EXTRACTOR_VERSION
    review_status: str = "confirmed"
    price_at_post: float | None = None
    pct_chg_at_post: float | None = None
    snapshot_precision: str = "missing"
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class SignalPerformance:
    signal_id: str
    return_1d: float | None = None
    return_3d: float | None = None
    return_5d: float | None = None
    return_20d: float | None = None
    max_gain_5d: float | None = None
    max_drawdown_5d: float | None = None
    excess_return_vs_hs300_5d: float | None = None
    excess_return_vs_industry_5d: float | None = None


@dataclass(frozen=True)
class AuthorScore:
    author_id: str
    sample_count: int
    overall_score: float | None
    status: str
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class DailyHotspot:
    trade_date: str
    symbol: str
    stock_name: str
    mention_count: int
    author_count: int
    kol_heat_score: float
    consensus_label: str
    risk_labels: list[str] = field(default_factory=list)
