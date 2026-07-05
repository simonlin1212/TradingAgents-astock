from datetime import date, datetime, timezone

import pytest

from tradingagents.dataflows.kol.author_registry import load_author_registry
from tradingagents.dataflows.kol.extractors import extract_signals
from tradingagents.dataflows.kol.models import RawKolPost
from tradingagents.dataflows.kol.obsidian_sync import ObsidianSync
from tradingagents.dataflows.kol.service import KolRadarService
from tradingagents.dataflows.kol.storage import KolStorage


def test_author_registry_loads_douyin_author(tmp_path):
    config = tmp_path / "kol_authors.yaml"
    config.write_text(
        """
authors:
  - id: teacher_a
    name: 老师A
    platform: douyin
    sec_uid: SEC123
    profile_url: https://www.douyin.com/user/SEC123
    style_tags: [短线, 题材]
    priority: high
    enabled: true
""",
        encoding="utf-8",
    )

    authors = load_author_registry(config)

    assert len(authors) == 1
    assert authors[0].id == "teacher_a"
    assert authors[0].platform == "douyin"
    assert authors[0].sec_uid == "SEC123"


def test_storage_upserts_raw_posts_by_hash_and_url(tmp_path):
    storage = KolStorage(tmp_path / "kol.sqlite")
    post = RawKolPost(
        post_id="p1",
        author_id="teacher_a",
        platform="douyin",
        published_at=datetime(2026, 7, 5, 9, 30, tzinfo=timezone.utc),
        content="低吸 300750 宁德时代，短线观察",
        source_url="https://www.douyin.com/video/1",
        content_hash="same",
    )

    first = storage.upsert_raw_post(post)
    second = storage.upsert_raw_post(post)

    assert first == second
    assert len(storage.list_raw_posts()) == 1


def test_extract_signals_requires_confirmed_a_stock_code():
    post = RawKolPost(
        post_id="p1",
        author_id="teacher_a",
        platform="douyin",
        published_at=datetime(2026, 7, 5, 9, 30, tzinfo=timezone.utc),
        content="今天低吸 300750 宁德时代，短线看 1-5 天，风险是追高。",
        source_url="https://www.douyin.com/video/1",
        content_hash="hash",
    )

    signals = extract_signals(post, stock_name_map={"300750": "宁德时代"})

    assert len(signals) == 1
    assert signals[0].symbol == "300750"
    assert signals[0].stock_name == "宁德时代"
    assert signals[0].action == "buy"
    assert signals[0].horizon == "short"
    assert signals[0].review_status == "confirmed"


def test_extract_signals_marks_name_only_mentions_pending():
    post = RawKolPost(
        post_id="p2",
        author_id="teacher_a",
        platform="douyin",
        published_at=datetime(2026, 7, 5, 9, 30, tzinfo=timezone.utc),
        content="机器人板块可以观察，某某股份有机会。",
        source_url="https://www.douyin.com/video/2",
        content_hash="hash2",
    )

    signals = extract_signals(post, stock_name_map={})

    assert signals == []


def test_service_ingests_posts_extracts_and_queries_summary(tmp_path):
    service = KolRadarService(db_path=tmp_path / "kol.sqlite")
    post = RawKolPost(
        post_id="p1",
        author_id="teacher_a",
        platform="douyin",
        published_at=datetime(2026, 7, 5, 9, 30, tzinfo=timezone.utc),
        content="低吸 300750 宁德时代，短线观察",
        source_url="https://www.douyin.com/video/1",
        content_hash="hash",
    )

    service.ingest_raw_posts([post], stock_name_map={"300750": "宁德时代"})
    summary = service.get_kol_summary("300750", date(2026, 7, 5), lookback_days=3)

    assert "300750" in summary
    assert "低吸" in summary or "buy" in summary
    assert "仅供研究辅助" in summary


def test_obsidian_sync_writes_stable_signal_notes(tmp_path):
    service = KolRadarService(db_path=tmp_path / "kol.sqlite")
    post = RawKolPost(
        post_id="p1",
        author_id="teacher_a",
        platform="douyin",
        published_at=datetime(2026, 7, 5, 9, 30, tzinfo=timezone.utc),
        content="低吸 300750 宁德时代，短线观察",
        source_url="https://www.douyin.com/video/1",
        content_hash="hash",
    )
    service.ingest_raw_posts([post], stock_name_map={"300750": "宁德时代"})

    vault = tmp_path / "vault"
    sync = ObsidianSync(service.storage, vault)
    sync.sync_full()
    sync.sync_full()

    signal_notes = list((vault / "KOL-Radar" / "Signals" / "2026-07-05").glob("*.md"))
    assert len(signal_notes) == 1
    text = signal_notes[0].read_text(encoding="utf-8")
    assert "symbol: 300750" in text
    assert "[[Stocks/300750-宁德时代]]" in text
    assert "#action/buy" in text
