# TradingAgents-Astock Context

TradingAgents-Astock is an A-share multi-agent investment research framework. It combines direct A-share data vendors, analyst agents, debate agents, risk review, and Streamlit/CLI outputs.

The KOL information radar is an auxiliary research subsystem. It stores structured KOL signals in SQLite, projects them into Obsidian for review, and exposes summaries to the social analyst. It must not auto-recommend stocks or place trades.

Core invariants:

- SQLite is the truth source for KOL data.
- Obsidian notes are idempotent projections that can be rebuilt.
- Every KOL signal must preserve `source_url`, `published_at`, `content_hash`, `author_id`, `platform`, `extractor_version`, and market snapshot precision.
- A-share code confirmation takes precedence over fuzzy name matching.
- User-facing KOL output must include the research-only risk disclosure.

