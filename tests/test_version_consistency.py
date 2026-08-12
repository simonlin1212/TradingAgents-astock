"""版本号三处必须一致（codex 第九轮）。

`pyproject.toml` 是权威值，但 `CHANGELOG.md` 的最新条目和 `CLAUDE.md` 的「当前版本」
也各写了一份。这轮就漏了 `CLAUDE.md`——后续 agent 和发版流程读它会拿到旧版本。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    assert m, "pyproject.toml 里找不到 version"
    return m.group(1)


def test_changelog_top_entry_matches_pyproject():
    version = _pyproject_version()
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## \[([^\]]+)\]", text, re.M)
    assert m, "CHANGELOG.md 里找不到版本条目"
    assert m.group(1) == version, (
        f"CHANGELOG 最新条目是 {m.group(1)}，pyproject 是 {version}"
    )


def test_claude_md_current_version_matches_pyproject():
    version = _pyproject_version()
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    m = re.search(r"\*\*当前版本\*\*[:：]\s*([0-9][0-9.]*)", text)
    assert m, "CLAUDE.md 里找不到「当前版本」"
    assert m.group(1) == version, (
        f"CLAUDE.md 写的是 {m.group(1)}，pyproject 是 {version}"
    )
