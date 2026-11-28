"""Eval: candidate predictions vs held-out reference, under a frozen bar."""

from __future__ import annotations

import json
import operator
from pathlib import Path

from .. import barlock
from ..manifest import build_manifest, sha256_file, write_manifest
from ..pack.schema import Bar, Pack
from ..pack.validate import load_pack, load_yaml
from . import heldout, metrics

_OPS = {"<=": operator.le, ">=": operator.ge}


def read_predictions(path: Path) -> dict[tuple[str, str], str]:
    preds: dict[tuple[str, str], str] = {}
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        key = (r["item"], r["dimension"])
        if key in preds:
            raise ValueError(f"predictions line {n}: duplicate cell {key}")
        preds[key] = r["label"]
    return preds


def build_cells(pack: Pack, ref: dict, locks: set, preds: dict):
    """Fail early: every non-locked reference cell needs a valid prediction."""
    valid = {d.id: set(pack.label_sets[d.label_set].labels) for d in pack.dimensions}
    cells, locked, problems = [], 0, []
    for (item, dim), label in sorted(ref.items()):
        if (item, dim) in locks:
            locked += 1
            continue
        p = preds.get((item, dim))
        if p is None:
            problems.append(f"missing prediction for {item}/{dim}")
        elif p not in valid[dim]:
            problems.append(f"invalid label {p!r} for {item}/{dim}")
        else:
            cells.append(metrics.Cell(item, dim, p, label))
    if problems:
        raise ValueError(
            "; ".join(problems[:10])
            + (f" (+{len(problems) - 10} more)" if len(problems) > 10 else "")
        )
    return cells, locked


def check_bar(bar: Bar, overall: dict, table: dict) -> list[dict]:
    results = []
    for t in bar.thresholds:
        v = overall[t.metric]
        results.append(
            {"scope": "overall", **t.model_dump(), "actual": v, "pass": _OPS[t.op](v, t.value)}
        )
    for dim, floors in bar.per_dimension_floors.items():
        for t in floors:
            v = table[dim][t.metric]
            results.append(
                {"scope": dim, **t.model_dump(), "actual": v, "pass": _OPS[t.op](v, t.value)}
            )
    return results


def run_eval(root: Path, predictions: Path, out: Path) -> dict:
    bar_hash = barlock.verify(root)  # refuses if bar.yaml changed since lock
    pack = load_pack(root)
    bar = Bar.model_validate(load_yaml(root / pack.files.bar))
    ref = heldout.read_reference(root, pack, out, purpose="eval")
    locks = heldout.read_locks(root, pack)
    cells, locked = build_cells(pack, ref, locks, read_predictions(predictions))
    overall = metrics.compute(cells, pack)
    table = metrics.per_dimension(cells, pack)
    results = check_bar(bar, overall, table)
    report = {
        "bar_hash": bar_hash,
        "cells_counted": len(cells),
        "cells_locked": locked,
        "overall": overall,
        "per_dimension": table,
        "bar_results": results,
        "bar_pass": all(r["pass"] for r in results),
    }
    d = out / "eval"
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    touches = (out / heldout.TOUCH_LOG).read_text().count("\n")
    write_manifest(
        out,
        build_manifest(
            "eval",
            "complete",
            {"id": pack.pack.id, "version": pack.pack.version, "hash": bar_hash},
            inputs=[
                {"path": str(predictions), "sha256": sha256_file(predictions)},
                {"path": "reference", "sha256": heldout.reference_sha(root, pack)},
            ],
            outputs=[{"path": str(d / "report.json"), "sha256": sha256_file(d / "report.json")}],
            params={
                "bar_hash": bar_hash,
                "heldout_touches": touches,
                "bar_pass": report["bar_pass"],
            },
        ),
    )
    return report


def format_report(r: dict) -> str:
    lines = [
        f"cells counted {r['cells_counted']}, locked (excluded) {r['cells_locked']}",
        f"{'dimension':<16}{'cells':>6}{'exact':>8}{'same_side':>11}{'reversals':>11}{'coverage':>10}",
    ]
    for dim, m in r["per_dimension"].items():
        lines.append(
            f"{dim:<16}{m['cells']:>6}{m['exact']:>8.2f}{m['same_side']:>11.2f}"
            f"{int(m['reversals']):>11}{m['coverage']:>10.2f}"
        )
    o = r["overall"]
    lines.append(
        f"{'OVERALL':<16}{r['cells_counted']:>6}{o['exact']:>8.2f}{o['same_side']:>11.2f}"
        f"{int(o['reversals']):>11}{o['coverage']:>10.2f}"
    )
    lines.append(
        f"addressed by candidate only {int(o['cand_only'])}, by reference only {int(o['ref_only'])}"
    )
    for b in r["bar_results"]:
        lines.append(
            f"bar {b['scope']} {b['metric']} {b['op']} {b['value']}: {b['actual']:.3g} {'PASS' if b['pass'] else 'FAIL'}"
        )
    lines.append("BAR " + ("PASS" if r["bar_pass"] else "FAIL"))
    return "\n".join(lines)
