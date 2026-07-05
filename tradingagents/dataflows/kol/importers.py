"""Import adapters for KOL content sources."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import RawKolPost


def raw_post_from_text(
    *,
    post_id: str,
    author_id: str,
    platform: str,
    published_at: datetime,
    content: str,
    source_url: str,
) -> RawKolPost:
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return RawKolPost(
        post_id=post_id,
        author_id=author_id,
        platform=platform,
        published_at=published_at,
        content=content,
        source_url=source_url,
        content_hash=content_hash,
    )


def load_jsonl(path: str | Path) -> list[RawKolPost]:
    posts = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        published = item.get("published_at")
        published_at = (
            datetime.fromisoformat(published)
            if published
            else datetime.now(timezone.utc)
        )
        posts.append(
            raw_post_from_text(
                post_id=str(item.get("post_id") or item.get("id") or item["source_url"]),
                author_id=str(item["author_id"]),
                platform=str(item.get("platform") or "manual"),
                published_at=published_at,
                content=str(item["content"]),
                source_url=str(item.get("source_url") or item.get("url") or ""),
            )
        )
    return posts


class DouyinImporter:
    """Thin adapter around the local DouYin_Spider project."""

    def __init__(self, spider_root: str | Path):
        self.spider_root = Path(spider_root)

    def fetch_author_posts(self, author) -> list[RawKolPost]:
        """Fetch one Douyin author's posts via the existing spider package."""
        import sys

        sys.path.insert(0, str(self.spider_root))
        try:
            from main import Data_Spider
            from utils.common_util import init
        finally:
            try:
                sys.path.remove(str(self.spider_root))
            except ValueError:
                pass

        if not author.profile_url:
            return []
        auth, base_path = init()
        spider = Data_Spider()
        work_items = spider.douyin_apis.get_user_all_work_info(auth, author.profile_url)
        posts = []
        for item in work_items:
            desc = str(item.get("desc") or item.get("aweme_info", {}).get("desc") or "")
            aweme_id = str(item.get("aweme_id") or item.get("aweme_info", {}).get("aweme_id") or "")
            create_time = item.get("create_time") or item.get("aweme_info", {}).get("create_time")
            published_at = (
                datetime.fromtimestamp(int(create_time), tz=timezone.utc)
                if create_time
                else datetime.now(timezone.utc)
            )
            url = f"https://www.douyin.com/video/{aweme_id}" if aweme_id else author.profile_url
            posts.append(
                raw_post_from_text(
                    post_id=aweme_id or url,
                    author_id=author.id,
                    platform="douyin",
                    published_at=published_at,
                    content=desc,
                    source_url=url,
                )
            )
        return posts
