"""One-off importer: builds this pack from the MC repo's files. Not part of core.

usage: python3 import_mc.py <MC repo root or a dir mirroring its eval/ and lab/spread/ files>

Reference label per cell = the MC scorer's own effective stance (non-silent needs a verbatim quote;
reported-voice reductions demote to implicit), taken from the current reference reader's rows
(latest row per text wins, as MC's own bundler does). Prototypes are the rubric's own per-stance
descriptions, verbatim. Nothing here is invented.
"""

import json
import sys
from pathlib import Path

import yaml

MC = Path(sys.argv[1])
HERE = Path(__file__).parent
sys.path.insert(0, str(MC / "eval"))
import score
from scoring import effective_stance

STANCES = ["affirms", "implicit", "silent", "reduces"]
rubric = json.loads((MC / "eval/rubric.json").read_text())
dims = rubric["categories"]
locked_calls = json.loads((MC / "eval/locked_calls.json").read_text())["calls"]

rows = {}
for ln in (MC / "lab/spread/results.jsonl").read_text().splitlines():
    r = json.loads(ln)
    if r.get("ok") and r.get("parsed"):
        rows[r["id"]] = r
versions = {(r["model"], r["prompt_version"], r["reader"]) for r in rows.values()}
if len(versions) != 1:
    sys.exit(f"reference rows come from more than one reader: {versions}")
ids = sorted(rows)
if len(ids) != 63:
    sys.exit(f"expected 63 texts, found {len(ids)}")

ref = []
for i in ids:
    r = rows[i]
    by = {c["id"]: c for c in r["parsed"].get("categories", [])}
    for d in dims:
        c = by.get(d["id"])
        label = effective_stance(c, r["text"]) if c else "silent"
        ref.append({"item": i, "dimension": d["id"], "label": label})

locks = []
for lc in locked_calls:
    cells = []
    if "must_reduce" in lc["rules"]:
        cells = [{"item": lc["id"], "dimension": k} for k in lc["dimensions"]]
    elif "set_stances" in lc["rules"]:
        cells = [{"item": lc["id"], "dimension": k} for k in lc["set"]]
    for c in cells:  # the owner's call is the reference label for a locked cell
        spec = lc["set"][c["dimension"]]["stance"] if "set_stances" in lc["rules"] else "reduces"
        for x in ref:
            if (x["item"], x["dimension"]) == (c["item"], c["dimension"]):
                x["label"] = spec
    if cells:
        locks.append(
            {"id": lc["id"], "cells": cells, "reason": f"owner-decided call ({lc['decided']})"}
        )

(HERE / "reference.jsonl").write_text("".join(json.dumps(x) + "\n" for x in ref))
(HERE / "heldout.yaml").write_text(
    yaml.safe_dump(
        {"items": [{"id": i, "text": rows[i]["text"]} for i in ids]},
        sort_keys=False,
        allow_unicode=True,
        width=10**6,
    )
)
(HERE / "locks.yaml").write_text(yaml.safe_dump({"locks": locks}, sort_keys=False))
(HERE / "prototypes.yaml").write_text(
    yaml.safe_dump(
        {d["id"]: {s: [d[s]] for s in STANCES} for d in dims}, sort_keys=False, allow_unicode=True
    )
)
# Teacher prompt = the MC lab reader's prompt, verbatim, in rubric order, with a passage placeholder.
order = [d["id"] for d in dims]
user = score.USER_TMPL.format(cats=score.cats_block(rubric, order), passage="<<PASSAGE>>")
(HERE / "prompt.md").write_text(score.SYSTEM + "\n=====USER=====\n" + user + "\n")
pack = {
    "schema_version": 1,
    "pack": {"id": "mc", "version": "0.1.0", "licence": "per-source"},
    "dimensions": [{"id": d["id"], "definition": d["probe"], "label_set": "stance"} for d in dims],
    "label_sets": {
        "stance": {
            "kind": "categorical",
            "labels": STANCES,
            "abstain": "silent",
            "polarity": {"opposed": [["affirms", "implicit"], ["reduces"]]},
        }
    },
    "teacher": {
        "prompt_file": "prompt.md",
        "prompt_version": score.PROMPT_VERSION,
        "evidence_quote": "required",
        "output": {
            "list_key": "categories",
            "id_key": "id",
            "label_key": "stance",
            "quote_key": "evidence_quote",
        },
        "demote": [
            {
                "from_label": "reduces",
                "field": "voice",
                "equals": "reported",
                "to_label": "implicit",
            }
        ],
        "providers": ["gemini"],
        "profile": "economy",
        "cap_usd": 5,
    },
    "files": {
        "corpus": "corpus.yaml",
        "heldout": "heldout.yaml",
        "reference": "reference.jsonl",
        "locks": "locks.yaml",
        "prototypes": "prototypes.yaml",
        "bar": "bar.yaml",
        "denylist": "denylist.txt",
    },
    "encoder": {
        "id": "BAAI/bge-small-en-v1.5",
        "revision": "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        "sha256": "0" * 64,
        "max_len": 512,
        "pooling": "mean",
    },
    "head": {"type": "logreg", "class_weight": "balanced", "seed": 0, "c_grid": [0.1, 1.0, 10.0]},
}
(HERE / "pack.yaml").write_text(
    yaml.safe_dump(pack, sort_keys=False, allow_unicode=True, width=10**6)
)
n_locked = sum(len(l["cells"]) for l in locks)
print(f"texts {len(ids)}, cells {len(ref)}, locked cells {n_locked}")
