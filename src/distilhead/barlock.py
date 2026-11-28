"""Bar freezing: bar.lock holds the sha256 of bar.yaml; eval and gate refuse on mismatch."""

from __future__ import annotations

from pathlib import Path

from .pack.validate import bar_hash, load_pack


class BarLockError(Exception):
    pass


def lock(root: Path) -> str:
    h = bar_hash(root, load_pack(root))
    p = root / "bar.lock"
    if p.exists() and p.read_text().strip() != h:
        raise BarLockError(
            "bar.lock exists and differs; the bar is frozen. Delete it deliberately to re-freeze."
        )
    p.write_text(h + "\n")
    return h


def verify(root: Path) -> str:
    p = root / "bar.lock"
    if not p.exists():
        raise BarLockError("bar.lock missing: run `distilhead bar lock` first")
    h = bar_hash(root, load_pack(root))
    if p.read_text().strip() != h:
        raise BarLockError("bar.yaml does not match bar.lock")
    return h
