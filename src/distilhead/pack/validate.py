"""`pack validate`: runs before any spend; returns a list of errors (empty = ok)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from ..checkcore import load_denylist
from ..guard import providers
from .schema import Bar, Pack


def load_yaml(p: Path):
    return yaml.safe_load(p.read_text())


def load_pack(root: Path) -> Pack:
    return Pack.model_validate(load_yaml(root / "pack.yaml"))


def bar_hash(root: Path, pack: Pack) -> str:
    return hashlib.sha256((root / pack.files.bar).read_bytes()).hexdigest()


def validate(root: Path) -> list[str]:
    errs: list[str] = []
    try:
        pack = load_pack(root)
    except Exception as e:  # noqa: BLE001 - report any schema failure
        return [f"pack.yaml: {e}"]

    f = pack.files
    for name in (
        f.corpus,
        f.heldout,
        f.reference,
        f.locks,
        f.prototypes,
        f.bar,
        f.denylist,
        pack.teacher.prompt_file,
    ):
        if not (root / name).is_file():
            errs.append(f"missing file: {name}")
    if errs:
        return errs

    dim_ids = [d.id for d in pack.dimensions]
    if len(set(dim_ids)) != len(dim_ids):
        errs.append("duplicate dimension ids")
    for d in pack.dimensions:
        if d.label_set not in pack.label_sets:
            errs.append(f"dimension {d.id}: unknown label_set {d.label_set}")
    for sid, ls in pack.label_sets.items():
        if len(set(ls.labels)) != len(ls.labels):
            errs.append(f"label_set {sid}: duplicate labels")
        for g in ls.polarity.opposed:
            for lab in g:
                if lab not in ls.labels:
                    errs.append(f"label_set {sid}: polarity label {lab!r} not in labels")
        if ls.abstain is not None and ls.abstain not in ls.labels:
            errs.append(f"label_set {sid}: abstain {ls.abstain!r} not in labels")

    try:
        Bar.model_validate(load_yaml(root / f.bar))
    except Exception as e:  # noqa: BLE001
        errs.append(f"{f.bar}: {e}")

    proto = load_yaml(root / f.prototypes) or {}
    for d in pack.dimensions:
        ls = pack.label_sets.get(d.label_set)
        if not ls:
            continue
        for lab in ls.labels:
            if not (proto.get(d.id, {}) or {}).get(lab):
                errs.append(f"prototypes: missing {d.id}/{lab}")

    corpus = load_yaml(root / f.corpus) or {}
    held = load_yaml(root / f.heldout) or {}
    corpus_ids = {i["id"] for i in corpus.get("items", [])}
    held_ids = [i["id"] for i in held.get("items", [])]
    if len(set(held_ids)) != len(held_ids):
        errs.append("heldout: duplicate ids")
    if corpus_ids & set(held_ids):
        errs.append(f"held-out ids present in corpus: {sorted(corpus_ids & set(held_ids))}")
    corpus_hashes = {
        hashlib.sha256(i["text"].encode()).hexdigest() for i in corpus.get("items", [])
    }
    for i in held.get("items", []):
        if hashlib.sha256(i["text"].encode()).hexdigest() in corpus_hashes:
            errs.append(f"held-out text also in corpus: {i['id']}")

    held_set = set(held_ids)
    for n, line in enumerate((root / f.reference).read_text().splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        ds = {d.id: d for d in pack.dimensions}
        if r.get("item") not in held_set:
            errs.append(f"reference line {n}: unknown item {r.get('item')!r}")
        d = ds.get(r.get("dimension"))
        if d is None:
            errs.append(f"reference line {n}: unknown dimension {r.get('dimension')!r}")
        elif (
            d.label_set in pack.label_sets
            and r.get("label") not in pack.label_sets[d.label_set].labels
        ):
            errs.append(f"reference line {n}: label {r.get('label')!r} not in label set")

    prompt = (root / pack.teacher.prompt_file).read_text()
    if pack.teacher.evidence_quote == "required" and "quote" not in prompt.lower():
        errs.append("evidence_quote required but prompt never mentions a quote")

    for prov in pack.teacher.providers:
        try:
            providers.check_provider(prov, pack.teacher.providers, root)
        except providers.ProviderRefused as e:
            errs.append(str(e))

    if not load_denylist(root / f.denylist):
        errs.append("denylist is empty")
    return errs
