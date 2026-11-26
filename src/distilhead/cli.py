"""Subcommands only; logic lives in modules."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import barlock, checkcore
from .manifest import build_manifest, sha256_file, write_manifest
from .pack.validate import load_pack, validate


def _validate(root: Path) -> int:
    errs = validate(root)
    for e in errs:
        print(f"FAIL {e}", file=sys.stderr)
    print("pack ok" if not errs else f"{len(errs)} error(s)")
    return 1 if errs else 0


def _check_core(repo: Path, denylists: list[Path]) -> int:
    hits = checkcore.scan(repo, denylists)
    for h in hits:
        print(f"FAIL domain string {h}", file=sys.stderr)
    print("core clean" if not hits else f"{len(hits)} hit(s)")
    return 1 if hits else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="distilhead")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("pack-validate", help="schema-check a pack before any spend")
    pv.add_argument("pack", type=Path)

    bl = sub.add_parser("bar-lock", help="freeze bar.yaml into bar.lock")
    bl.add_argument("pack", type=Path)

    cc = sub.add_parser("check-core", help="fail if core contains denylisted tokens")
    cc.add_argument("--repo", type=Path, default=Path("."))
    cc.add_argument("--denylist", type=Path, action="append", required=True)

    run = sub.add_parser(
        "run", help="step-0 pipeline: validate, lock bar, check core, write manifest"
    )
    run.add_argument("pack", type=Path)
    run.add_argument("--out", type=Path, default=Path("out"))
    run.add_argument("--repo", type=Path, default=Path("."))

    a = ap.parse_args(argv)
    try:
        if a.cmd == "pack-validate":
            return _validate(a.pack)
        if a.cmd == "bar-lock":
            print(barlock.lock(a.pack))
            return 0
        if a.cmd == "check-core":
            return _check_core(a.repo, a.denylist)
        if a.cmd == "run":
            if _validate(a.pack):
                return 1
            h = barlock.lock(a.pack)
            if _check_core(a.repo, [a.pack / load_pack(a.pack).files.denylist]):
                return 1
            pk = load_pack(a.pack)
            out = [{"path": str(a.pack / "bar.lock"), "sha256": sha256_file(a.pack / "bar.lock")}]
            m = build_manifest(
                "pack",
                "complete",
                {"id": pk.pack.id, "version": pk.pack.version, "hash": h},
                outputs=out,
            )
            print(write_manifest(a.out, m))
            return 0
    except Exception as e:  # noqa: BLE001 - fail early with a clear message
        print(f"FAIL {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
