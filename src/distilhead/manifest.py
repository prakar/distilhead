"""Shared manifest envelope and hashing."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import __version__


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(step: str, status: str, pack: dict, inputs=(), outputs=(), params=None) -> dict:
    return {
        "schema_version": 1,
        "step": step,
        "status": status,
        "tool": {"version": __version__},
        "pack": pack,
        "inputs": list(inputs),
        "outputs": list(outputs),
        "params": params or {},
        "env": {"python": sys.version.split()[0], "platform": platform.platform()},
        "created_at": datetime.now(UTC).isoformat(),
    }


def write_manifest(out_dir: Path, manifest: dict) -> Path:
    d = out_dir / manifest["step"]
    d.mkdir(parents=True, exist_ok=True)
    p = d / "manifest.json"
    p.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return p


def check_chain(inputs: list[dict]) -> None:
    """Fail early if any recorded input hash no longer matches the file on disk."""
    for i in inputs:
        p = Path(i["path"])
        if not p.exists():
            raise ValueError(f"chain: missing input {p}")
        if sha256_file(p) != i["sha256"]:
            raise ValueError(f"chain: hash mismatch for {p}")
