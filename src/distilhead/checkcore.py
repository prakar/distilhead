"""No-domain-strings check: core paths must not contain any token from a pack denylist."""

from __future__ import annotations

import re
from pathlib import Path

SCAN_FILES = ("README.md", "DECISIONS.md", "pyproject.toml", "mise.toml", "package.json")
SCAN_DIRS = ("src", "tests", "tools", ".github", "packs/toy")
SCAN_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".mjs", ".toml", ".json", ".jsonl", ".txt"}


def load_denylist(path: Path) -> list[str]:
    toks = [ln.strip() for ln in path.read_text().splitlines()]
    return [t for t in toks if t and not t.startswith("#")]


def compile_denylist(tokens: list[str]) -> re.Pattern:
    if not tokens:
        raise ValueError("denylist is empty")
    parts = []
    for t in tokens:
        # word-start match; trailing * is explicit, matching is prefix-based either way
        parts.append(re.escape(t.rstrip("*")))
    return re.compile(r"\b(?:" + "|".join(parts) + ")", re.IGNORECASE)


def core_files(repo: Path):
    for f in SCAN_FILES:
        if (repo / f).is_file():
            yield repo / f
    for d in SCAN_DIRS:
        for p in sorted((repo / d).rglob("*")):
            if (
                p.is_file()
                and p.suffix in SCAN_SUFFIXES
                and p.name != "denylist.txt"
                and "__pycache__" not in p.parts
                and "node_modules" not in p.parts
            ):
                yield p


def scan(repo: Path, denylists: list[Path]) -> list[str]:
    tokens: list[str] = []
    for d in denylists:
        tokens += load_denylist(d)
    pat = compile_denylist(tokens)
    hits = []
    for p in core_files(repo):
        for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            m = pat.search(line)
            if m:
                hits.append(f"{p.relative_to(repo)}:{n}: {m.group(0)!r}")
    return hits
