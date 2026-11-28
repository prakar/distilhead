"""Subcommands only; logic lives in modules."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import barlock, checkcore, zeroshot
from .embed import embedders
from .eval import harness
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


def _label(a) -> int:
    from .guard import cost, teacher
    from .label import run as lrun

    env = dict(os.environ)
    pk = load_pack(a.pack)
    if a.dry_run:
        model = "gemini-2.5-flash"
        price = cost.price_for(model, env)
        print(lrun.dry_run(a.pack, a.out, price, a.cap_usd or pk.teacher.cap_usd, model))
        return 0
    key = env.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY not set (source ~/.secrets); never pass keys on the command line"
        )
    env["DISTILHEAD_PROVIDER_KEY"] = key
    env.setdefault("LLM_MODEL_RESOLVER_PROFILE", "economy")
    cleared = teacher.clear_teacher(
        a.pack, "gemini", env, a.out / "label" / "cost_ledger.jsonl", a.cap_usd
    )
    if a.raise_cap is not None:
        cleared.ledger.raise_cap(a.raise_cap, env.get("USER", "owner"), a.reason)
    client = teacher.create_client(cleared, key)
    s = lrun.run_label(a.pack, a.out, cleared, client.generate, env, continue_full=a.cont)
    print(json.dumps(s, indent=2))
    if not a.cont:
        print(
            "pilot done. Check the measured cost above, then re-run with --continue for the rest."
        )
    return 1 if s["stopped_by_cap"] else 0


def _gate(a) -> int:
    from .eval import harness
    from .label import run as lrun

    pk = load_pack(a.pack)
    man = json.loads((a.out / "label" / "manifest.json").read_text())
    model = man["params"]["model"]
    preds = lrun.write_predictions(a.pack, a.out, model)
    rep = harness.run_eval(a.pack, preds, a.out, step="gate", purpose="gate")
    print(harness.format_report(rep))
    print(f"teacher {model}  prompt {lrun.prompt_sha(a.pack, pk)[:12]}")
    return 0 if rep["bar_pass"] else 1


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

    zs = sub.add_parser("zeroshot", help="nearest-prototype predictions on held-out ($0, no LLM)")
    zs.add_argument("pack", type=Path)
    zs.add_argument("--out", type=Path, default=Path("out"))
    zs.add_argument("--embedder", choices=["hash", "encoder"], default="encoder")

    ev = sub.add_parser("eval", help="score predictions on held-out under the frozen bar")
    ev.add_argument("pack", type=Path)
    ev.add_argument("--predictions", type=Path, required=True)
    ev.add_argument("--out", type=Path, default=Path("out"))
    ev.add_argument("--require-pass", action="store_true", help="exit 1 if the bar fails")

    lb = sub.add_parser("label", help="teacher labels held-out texts (pilot first; spends money)")
    lb.add_argument("pack", type=Path)
    lb.add_argument("--out", type=Path, default=Path("out"))
    lb.add_argument(
        "--dry-run", action="store_true", help="print call count and estimate; no calls"
    )
    lb.add_argument(
        "--continue", dest="cont", action="store_true", help="after the pilot: label the rest"
    )
    lb.add_argument("--cap-usd", type=float, default=None, help="can only lower the cap")
    lb.add_argument("--raise-cap", type=float, default=None)
    lb.add_argument("--reason", default="", help="required with --raise-cap")

    gt = sub.add_parser(
        "gate", help="teacher-ceiling: score the teacher's labels under the frozen bar"
    )
    gt.add_argument("pack", type=Path)
    gt.add_argument("--out", type=Path, default=Path("out"))

    a = ap.parse_args(argv)
    try:
        if a.cmd == "pack-validate":
            return _validate(a.pack)
        if a.cmd == "bar-lock":
            print(barlock.lock(a.pack))
            return 0
        if a.cmd == "check-core":
            return _check_core(a.repo, a.denylist)
        if a.cmd == "zeroshot":
            pk = load_pack(a.pack)
            print(zeroshot.predict(a.pack, embedders.load(a.embedder, pk.encoder), a.out))
            return 0
        if a.cmd == "eval":
            rep = harness.run_eval(a.pack, a.predictions, a.out)
            print(harness.format_report(rep))
            return 1 if (a.require_pass and not rep["bar_pass"]) else 0
        if a.cmd == "label":
            return _label(a)
        if a.cmd == "gate":
            return _gate(a)
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
