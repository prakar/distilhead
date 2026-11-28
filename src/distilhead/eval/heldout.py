"""The ONLY reader of held-out texts and reference labels (besides pack validation).

Every read appends one row to heldout_touches.jsonl so held-out use is auditable.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..manifest import sha256_file
from ..pack.schema import Pack
from ..pack.validate import load_yaml

TOUCH_LOG = "heldout_touches.jsonl"


def _touch(log_dir: Path, path: Path, purpose: str) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "path": str(path),
        "sha256": sha256_file(path),
        "purpose": purpose,
    }
    with open(log_dir / TOUCH_LOG, "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def read_texts(root: Path, pack: Pack, log_dir: Path, purpose: str) -> list[dict]:
    p = root / pack.files.heldout
    _touch(log_dir, p, purpose)
    return (load_yaml(p) or {}).get("items", [])


def read_reference(root: Path, pack: Pack, log_dir: Path, purpose: str) -> dict:
    """Returns {(item, dimension): label}. Duplicate cells are an error."""
    p = root / pack.files.reference
    _touch(log_dir, p, purpose)
    ref: dict[tuple[str, str], str] = {}
    for n, line in enumerate(p.read_text().splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        key = (r["item"], r["dimension"])
        if key in ref:
            raise ValueError(f"reference line {n}: duplicate cell {key}")
        ref[key] = r["label"]
    return ref


def read_locks(root: Path, pack: Pack) -> set[tuple[str, str]]:
    """Explicit lock cells only. Rule-based locks are not supported in core: refuse loudly."""
    data = load_yaml(root / pack.files.locks) or {}
    cells: set[tuple[str, str]] = set()
    for lk in data.get("locks", []):
        if "rule" in lk:
            raise ValueError(
                f"lock {lk.get('id')!r}: rule-based locks unsupported; expand to cells"
            )
        for c in lk.get("cells", []):
            cells.add((c["item"], c["dimension"]))
    return cells


def reference_sha(root: Path, pack: Pack) -> str:
    return sha256_file(root / pack.files.reference)
