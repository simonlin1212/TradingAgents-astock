"""Model profile loader for TradingAgents-Astock.

Reads ``model_profile.yaml`` from the project root and returns a ready-to-use
config dict for ``TradingAgentsGraph``.

Usage::

    from tradingagents.model_profile import get_active_config
    config = get_active_config()
    ta = TradingAgentsGraph(config=config)

You can also select a specific profile::

    config = get_profile("deepseek_pro")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from tradingagents.default_config import DEFAULT_CONFIG

_PROFILE_PATH = Path(__file__).parent.parent / "model_profile.yaml"


def _load_profiles() -> dict:
    """Load and parse model_profile.yaml."""
    if not _PROFILE_PATH.exists():
        return {}
    with open(_PROFILE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_active_config() -> Dict[str, Any]:
    """Return a config dict using the active profile from model_profile.yaml.

    Falls back to DEFAULT_CONFIG if the profile file is missing or the
    active profile is not found.
    """
    data = _load_profiles()
    active = data.get("active_profile", "")
    profiles = data.get("profiles", {})
    shared = data.get("shared_settings", {})

    if active not in profiles:
        return dict(DEFAULT_CONFIG)

    profile = dict(profiles[active])
    profile.pop("description", None)  # Remove non-config keys

    # Merge: defaults < shared < profile
    config = {**DEFAULT_CONFIG, **shared, **profile}
    return config


def get_profile(name: str) -> Dict[str, Any]:
    """Return a specific profile's config dict."""
    data = _load_profiles()
    profiles = data.get("profiles", {})
    shared = data.get("shared_settings", {})

    if name not in profiles:
        raise ValueError(
            f"Profile '{name}' not found. Available: {list(profiles.keys())}"
        )

    profile = dict(profiles[name])
    profile.pop("description", None)
    return {**DEFAULT_CONFIG, **shared, **profile}


def list_profiles() -> Dict[str, str]:
    """Return {name: description} for all available profiles."""
    data = _load_profiles()
    return {
        name: info.get("description", "")
        for name, info in data.get("profiles", {}).items()
    }
