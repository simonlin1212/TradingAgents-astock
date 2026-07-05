"""SQLite storage for KOL radar data."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import AuthorScore, KolSignal, RawKolPost


def default_db_path() -> Path:
    env_path = os.environ.get("TRADINGAGENTS_KOL_DB_PATH")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".tradingagents" / "kol" / "kol_radar.sqlite"


def _dt(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class KolStorage:
    """Small SQLite interface used by CLI, agent tools, and Obsidian sync."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path is not None else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS raw_kol_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    raw_media_path TEXT,
                    collected_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(content_hash, source_url)
                );

                CREATE TABLE IF NOT EXISTS kol_signals (
                    signal_id TEXT PRIMARY KEY,
                    post_id TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    action_text TEXT NOT NULL,
                    strength TEXT NOT NULL,
                    horizon TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    risk_warning TEXT NOT NULL,
                    llm_confidence REAL NOT NULL,
                    published_at TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    content_excerpt TEXT NOT NULL,
                    extractor_version TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    price_at_post REAL,
                    pct_chg_at_post REAL,
                    snapshot_precision TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS author_scores (
                    author_id TEXT PRIMARY KEY,
                    sample_count INTEGER NOT NULL,
                    overall_score REAL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def upsert_raw_post(self, post: RawKolPost) -> int:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO raw_kol_posts (
                    post_id, author_id, platform, published_at, content, source_url,
                    content_hash, raw_media_path, collected_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    post.post_id,
                    post.author_id,
                    post.platform,
                    _dt(post.published_at),
                    post.content,
                    post.source_url,
                    post.content_hash,
                    post.raw_media_path,
                    _dt(post.collected_at),
                    json.dumps(post.metadata, ensure_ascii=False),
                ),
            )
            row = conn.execute(
                "SELECT id FROM raw_kol_posts WHERE content_hash = ? AND source_url = ?",
                (post.content_hash, post.source_url),
            ).fetchone()
            return int(row["id"])

    def list_raw_posts(self) -> list[RawKolPost]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM raw_kol_posts ORDER BY published_at DESC"
            ).fetchall()
        return [self._raw_post_from_row(row) for row in rows]

    def upsert_signals(self, signals: Iterable[KolSignal]) -> None:
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO kol_signals (
                    signal_id, post_id, author_id, platform, symbol, stock_name,
                    action, action_text, strength, horizon, reason, risk_warning,
                    llm_confidence, published_at, source_url, content_excerpt,
                    extractor_version, review_status, price_at_post,
                    pct_chg_at_post, snapshot_precision, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        signal.signal_id,
                        signal.post_id,
                        signal.author_id,
                        signal.platform,
                        signal.symbol,
                        signal.stock_name,
                        signal.action,
                        signal.action_text,
                        signal.strength,
                        signal.horizon,
                        signal.reason,
                        signal.risk_warning,
                        signal.llm_confidence,
                        _dt(signal.published_at),
                        signal.source_url,
                        signal.content_excerpt,
                        signal.extractor_version,
                        signal.review_status,
                        signal.price_at_post,
                        signal.pct_chg_at_post,
                        signal.snapshot_precision,
                        _dt(signal.created_at),
                    )
                    for signal in signals
                ],
            )

    def list_signals(self, symbol: str | None = None, since: datetime | None = None) -> list[KolSignal]:
        query = "SELECT * FROM kol_signals WHERE 1=1"
        params: list[str] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if since:
            query += " AND published_at >= ?"
            params.append(_dt(since))
        query += " ORDER BY published_at DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._signal_from_row(row) for row in rows]

    def upsert_author_score(self, score: AuthorScore) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO author_scores (
                    author_id, sample_count, overall_score, status, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    score.author_id,
                    score.sample_count,
                    score.overall_score,
                    score.status,
                    _dt(score.updated_at),
                ),
            )

    @staticmethod
    def _raw_post_from_row(row: sqlite3.Row) -> RawKolPost:
        return RawKolPost(
            post_id=row["post_id"],
            author_id=row["author_id"],
            platform=row["platform"],
            published_at=_parse_dt(row["published_at"]),
            content=row["content"],
            source_url=row["source_url"],
            content_hash=row["content_hash"],
            raw_media_path=row["raw_media_path"],
            collected_at=_parse_dt(row["collected_at"]),
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    @staticmethod
    def _signal_from_row(row: sqlite3.Row) -> KolSignal:
        return KolSignal(
            signal_id=row["signal_id"],
            post_id=row["post_id"],
            author_id=row["author_id"],
            platform=row["platform"],
            symbol=row["symbol"],
            stock_name=row["stock_name"],
            action=row["action"],
            action_text=row["action_text"],
            strength=row["strength"],
            horizon=row["horizon"],
            reason=row["reason"],
            risk_warning=row["risk_warning"],
            llm_confidence=float(row["llm_confidence"]),
            published_at=_parse_dt(row["published_at"]),
            source_url=row["source_url"],
            content_excerpt=row["content_excerpt"],
            extractor_version=row["extractor_version"],
            review_status=row["review_status"],
            price_at_post=row["price_at_post"],
            pct_chg_at_post=row["pct_chg_at_post"],
            snapshot_precision=row["snapshot_precision"],
            created_at=_parse_dt(row["created_at"]),
        )
