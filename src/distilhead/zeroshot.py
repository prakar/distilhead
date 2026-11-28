"""Zero-shot comparator: nearest label prototype by cosine. No training, no LLM, $0."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .embed.embedders import Embedder, _normalise
from .eval import heldout
from .manifest import build_manifest, sha256_file, write_manifest
from .pack.validate import load_pack, load_yaml


def predict(root: Path, embedder: Embedder, out: Path) -> Path:
    pack = load_pack(root)
    proto = load_yaml(root / pack.files.prototypes)
    items = heldout.read_texts(root, pack, out, purpose="zeroshot")
    xs = embedder.embed([i["text"] for i in items])
    rows = []
    for d in pack.dimensions:
        labels = pack.label_sets[d.label_set].labels
        cents = []
        for lab in labels:
            texts = proto[d.id][lab]
            cents.append(embedder.embed(texts).mean(axis=0))
        sims = xs @ _normalise(np.stack(cents)).T
        for it, s in zip(items, sims, strict=True):
            rows.append({"item": it["id"], "dimension": d.id, "label": labels[int(np.argmax(s))]})
    p = out / "zeroshot" / "predictions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    write_manifest(
        out,
        build_manifest(
            "zeroshot",
            "complete",
            {"id": pack.pack.id, "version": pack.pack.version, "hash": ""},
            outputs=[{"path": str(p), "sha256": sha256_file(p), "rows": len(rows)}],
            params={"embedder": type(embedder).__name__, "cost_usd": 0},
        ),
    )
    return p
