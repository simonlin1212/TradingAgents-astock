"""Load configured KOL authors."""

from __future__ import annotations

from pathlib import Path

from .models import KolAuthor


def load_author_registry(path: str | Path) -> list[KolAuthor]:
    """Load author definitions from ``config/kol_authors.yaml``."""
    try:
        import yaml
        loader = lambda text: yaml.safe_load(text) or {}
    except ImportError as exc:  # pragma: no cover - depends on environment
        loader = _load_minimal_yaml

    config_path = Path(path)
    if not config_path.exists():
        return []

    raw = loader(config_path.read_text(encoding="utf-8"))
    authors = []
    for item in raw.get("authors", []):
        authors.append(
            KolAuthor(
                id=str(item["id"]),
                name=str(item.get("name") or item["id"]),
                platform=str(item.get("platform") or "unknown"),
                profile_url=item.get("profile_url"),
                sec_uid=item.get("sec_uid"),
                style_tags=list(item.get("style_tags") or []),
                priority=str(item.get("priority") or "medium"),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return authors


def _load_minimal_yaml(text: str) -> dict:
    """Parse the small kol_authors.yaml shape when PyYAML is unavailable."""
    authors: list[dict] = []
    current: dict | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line == "authors:":
            continue
        if line.startswith("- "):
            if current:
                authors.append(current)
            current = {}
            line = line[2:].strip()
            if line:
                key, value = line.split(":", 1)
                current[key.strip()] = _parse_scalar(value.strip())
            continue
        if current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.strip()] = _parse_scalar(value.strip())
    if current:
        authors.append(current)
    return {"authors": authors}


def _parse_scalar(value: str):
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [part.strip().strip('"').strip("'") for part in inner.split(",")]
    return value.strip('"').strip("'")
