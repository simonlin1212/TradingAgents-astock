"""Generate an Obsidian projection from SQLite KOL data."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .service import RISK_DISCLOSURE
from .storage import KolStorage

DEFAULT_VAULT_PATH = Path(r"C:\Users\35230\Documents\Obsidian Vault")


class ObsidianSync:
    def __init__(self, storage: KolStorage, vault_path: str | Path | None = None):
        env_path = os.environ.get("OBSIDIAN_VAULT_PATH")
        self.storage = storage
        self.vault_path = Path(vault_path or env_path or DEFAULT_VAULT_PATH)
        self.root = self.vault_path / "KOL-Radar"

    def sync_full(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ("Authors", "Stocks", "Signals", "Daily", "Reviews", "_templates"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        signals = self.storage.list_signals()
        for signal in signals:
            self._write_signal(signal)
            self._write_stock(signal)
            self._write_author(signal.author_id)
        self._write_moc()

    def _write_signal(self, signal) -> None:
        day = signal.published_at.strftime("%Y-%m-%d")
        folder = self.root / "Signals" / day
        folder.mkdir(parents=True, exist_ok=True)
        filename = f"{signal.signal_id}.md"
        path = folder / filename
        stock_note = f"Stocks/{signal.symbol}-{_safe_name(signal.stock_name)}"
        author_note = f"Authors/{_safe_name(signal.author_id)}"
        body = f"""---
signal_id: {signal.signal_id}
symbol: {signal.symbol}
stock_name: {signal.stock_name}
author: {signal.author_id}
platform: {signal.platform}
action: {signal.action}
horizon: {signal.horizon}
strength: {signal.strength}
published_at: {signal.published_at.isoformat()}
price_at_post: {signal.price_at_post if signal.price_at_post is not None else ''}
pct_chg_at_post: {signal.pct_chg_at_post if signal.pct_chg_at_post is not None else ''}
snapshot_precision: {signal.snapshot_precision}
llm_confidence: {signal.llm_confidence}
source_url: {signal.source_url}
extractor_version: {signal.extractor_version}
review_status: {signal.review_status}
---

# {signal.symbol} {signal.stock_name} KOL Signal

[[{author_note}]] -> [[{stock_note}]]

{signal.content_excerpt}

#action/{signal.action} #horizon/{signal.horizon}

Source: {signal.source_url}

{RISK_DISCLOSURE}
"""
        path.write_text(body, encoding="utf-8")

    def _write_stock(self, signal) -> None:
        path = self.root / "Stocks" / f"{signal.symbol}-{_safe_name(signal.stock_name)}.md"
        body = f"""---
symbol: {signal.symbol}
stock_name: {signal.stock_name}
---

# {signal.symbol} {signal.stock_name}

```dataview
TABLE author, action, horizon, published_at, price_at_post
FROM "KOL-Radar/Signals"
WHERE symbol = "{signal.symbol}"
SORT published_at DESC
```

{RISK_DISCLOSURE}
"""
        path.write_text(body, encoding="utf-8")

    def _write_author(self, author_id: str) -> None:
        path = self.root / "Authors" / f"{_safe_name(author_id)}.md"
        body = f"""---
author: {author_id}
---

# {author_id}

```dataview
TABLE symbol, stock_name, action, horizon, published_at
FROM "KOL-Radar/Signals"
WHERE author = "{author_id}"
SORT published_at DESC
```

{RISK_DISCLOSURE}
"""
        path.write_text(body, encoding="utf-8")

    def _write_moc(self) -> None:
        path = self.root / "_MOC.md"
        path.write_text(
            f"""# KOL Radar

```dataview
TABLE symbol, stock_name, author, action, horizon, published_at
FROM "KOL-Radar/Signals"
SORT published_at DESC
```

{RISK_DISCLOSURE}
""",
            encoding="utf-8",
        )


def _safe_name(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "-", value).strip() or "unknown"
