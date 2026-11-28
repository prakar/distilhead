"""Teacher labelling of the held-out texts (the teacher-ceiling run) and its gate.

Append-only labels.jsonl, resumable and idempotent: state is derived from the file.
Pilot first (PILOT_ITEMS), measured cost extrapolated, full run only with an explicit continue.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

from .. import barlock
from ..eval import heldout
from ..guard import cost
from ..guard.cost import PILOT_ITEMS, CapExceeded, Ledger
from ..manifest import build_manifest, sha256_file, write_manifest
from ..pack.schema import Pack
from ..pack.validate import load_pack

USER_MARK = "=====USER====="
PASSAGE = "<<PASSAGE>>"
MAX_ATTEMPTS = 3
MAX_OUT_TOKENS = 4096
EST_OUT_TOKENS = 1500  # dry-run guess, UNMEASURED
Generate = Callable[[str, str, int], object]  # (system, user, max_out) -> Reply


def split_prompt(text: str) -> tuple[str, str]:
    if USER_MARK in text:
        a, b = text.split(USER_MARK, 1)
        return a.strip(), b.strip()
    return "", text.strip()


def prompt_sha(root: Path, pack: Pack) -> str:
    return hashlib.sha256((root / pack.teacher.prompt_file).read_bytes()).hexdigest()


def _norm(s: str) -> str:
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[\W_]+", " ", re.sub(r"\s+", " ", s).strip().lower()).strip()


def quote_ok(quote: str, text: str) -> bool:
    """Every fragment (split on ellipses) occurs verbatim in the text, ignoring case and punctuation."""
    t = " " + _norm(text) + " "
    frags = [x for x in re.split(r"\.\.\.|…", quote) if len(x.strip()) >= 3]
    return bool(frags) and all((" " + _norm(x) + " ") in t for x in frags if _norm(x))


def parse_reading(raw: str, pack: Pack) -> list[dict]:
    """Returns the teacher's per-dimension readings; raises ValueError listing every problem."""
    o = pack.teacher.output
    m = re.search(r"\{.*\}", raw.strip(), re.DOTALL)
    data = json.loads(m.group(0) if m else raw)
    rows = data.get(o.list_key)
    if not isinstance(rows, list):
        raise ValueError(f"missing list {o.list_key!r}")  # noqa: TRY004
    valid = {d.id: set(pack.label_sets[d.label_set].labels) for d in pack.dimensions}
    seen, errs = {}, []
    for r in rows:
        did, lab = r.get(o.id_key), str(r.get(o.label_key, "")).strip().lower()
        if did not in valid:
            errs.append(f"unknown id {did!r}")
        elif did in seen:
            errs.append(f"duplicate id {did}")
        elif lab not in valid[did]:
            errs.append(f"{did}: label {lab!r} not in {sorted(valid[did])}")
        else:
            seen[did] = {**r, o.label_key: lab}
    errs += [f"missing id {d}" for d in valid if d not in seen]
    if errs:
        raise ValueError("; ".join(errs[:6]))
    return [seen[d.id] for d in pack.dimensions]


def effective_labels(reading: list[dict], text: str, pack: Pack) -> dict[str, str]:
    """Unquoted or unverifiable non-abstain labels fall to abstain; pack-declared demotions apply."""
    o = pack.teacher.output
    out = {}
    for d, r in zip(pack.dimensions, reading, strict=True):
        ls = pack.label_sets[d.label_set]
        lab = r[o.label_key]
        if ls.abstain is not None and lab != ls.abstain:
            q = str(r.get(o.quote_key) or "").strip()
            if pack.teacher.evidence_quote == "required" and not (q and quote_ok(q, text)):
                lab = ls.abstain
        for dm in pack.teacher.demote:
            if lab == dm.from_label and str(r.get(dm.field, "")).strip().lower() == dm.equals:
                lab = dm.to_label
        out[d.id] = lab
    return out


def _done(path: Path, key: tuple[str, str]) -> set[str]:
    if not path.exists():
        return set()
    done = set()
    for ln in path.read_text().splitlines():
        if ln.strip():
            r = json.loads(ln)
            if r.get("ok") and (r["prompt_sha"], r["model"]) == key:
                done.add(r["item"])
    return done


def dry_run(root: Path, out: Path, price: tuple[float, float], cap: float, model: str) -> str:
    """Writes nothing, makes no calls, resolves no model (so the price and model are ASSUMPTIONS)."""
    pack = load_pack(root)
    system, user = split_prompt((root / pack.teacher.prompt_file).read_text())
    n = len(load_items(root, pack, out, "label-dry-run"))
    tin = (len(system) + len(user)) // 4 + 300  # chars/4 plus passage allowance, rough
    per = cost.call_cost(price, tin, EST_OUT_TOKENS)
    return (
        f"calls: {n} (one per held-out text; retries add up to {MAX_ATTEMPTS - 1} more each)\n"
        f"assumed model {model}, price in/out per 1M tokens {price}\n"
        f"estimated per call ~${per:.4f} (UNMEASURED), total ~${per * n:.3f}, cap ${cap:.2f}\n"
        f"pilot = first {PILOT_ITEMS} texts; nothing was called or written"
    )


def load_items(root: Path, pack: Pack, out: Path, purpose: str) -> list[dict]:
    return heldout.read_texts(root, pack, out, purpose=purpose)


def run_label(
    root: Path,
    out: Path,
    cleared,
    generate: Generate,
    env,
    continue_full: bool = False,
    progress: Callable[[str], None] = print,
) -> dict:
    barlock.verify(root)  # the bar is frozen before the teacher touches held-out
    pack = load_pack(root)
    ledger: Ledger = cleared.ledger
    model = cleared.model.model
    price = cost.price_for(model, env)
    system, user_t = split_prompt((root / pack.teacher.prompt_file).read_text())
    psha = prompt_sha(root, pack)
    path = out / "label" / "labels.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    items = load_items(root, pack, out, "label")
    done = _done(path, (psha, model))
    todo = [i for i in items if i["id"] not in done]
    if continue_full:
        if len(done) < min(PILOT_ITEMS, len(items)):
            raise ValueError(f"run the {PILOT_ITEMS}-item pilot first ({len(done)} done)")
    else:
        todo = todo[: max(0, PILOT_ITEMS - len(done))]
    stopped = None
    with open(path, "a") as fh:
        for it in todo:
            prompt = user_t.replace(PASSAGE, it["text"])
            rec = {"item": it["id"], "model": model, "prompt_sha": psha, "ok": False, "errors": []}
            msgs = prompt
            for attempt in range(MAX_ATTEMPTS):
                est_in = (len(system) + len(msgs)) // 3 + 100  # pessimistic chars/3
                try:
                    ledger.check(cost.call_cost(price, est_in, MAX_OUT_TOKENS))
                except CapExceeded as e:
                    stopped = str(e)
                    break
                r = generate(system, msgs, MAX_OUT_TOKENS)
                c = cost.call_cost(price, r.tokens_in, r.tokens_out)
                ledger.record(
                    f"{it['id']}#{attempt}",
                    model,
                    c,
                    tokens_in=r.tokens_in,
                    tokens_out=r.tokens_out,
                )
                rec.update(raw=r.text, attempts=attempt + 1)
                try:
                    reading = parse_reading(r.text, pack)
                    rec.update(
                        ok=True,
                        reading=reading,
                        labels=effective_labels(reading, it["text"], pack),
                        errors=[],
                    )
                    break
                except (ValueError, json.JSONDecodeError) as e:
                    rec["errors"] = [str(e)[:300]]
                    msgs = (
                        prompt
                        + "\n\nYour previous JSON was invalid: "
                        + str(e)[:300]
                        + ". Return the complete corrected JSON only."
                    )
            if stopped:
                break
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()
            progress(f"{it['id']:36s} {'ok' if rec['ok'] else 'FAILED ' + str(rec['errors'])[:80]}")
    done = _done(path, (psha, model))
    spent, n_calls = ledger.spent, ledger.calls()
    per_item = spent / len(done) if done else None
    summary = {
        "model": model,
        "prompt_sha": psha,
        "items_done": len(done),
        "items_total": len(items),
        "spent_usd": spent,
        "cap_usd": ledger.cap,
        "calls": n_calls,
        "usd_per_item_measured": per_item,
        "usd_extrapolated_all_items": (
            cost.extrapolate(spent, len(done), len(items)) if done else None
        ),
        "stopped_by_cap": stopped,
    }
    write_manifest(
        out,
        build_manifest(
            "label",
            "complete" if len(done) == len(items) else "partial",
            {"id": pack.pack.id, "version": pack.pack.version, "hash": ""},
            outputs=[{"path": str(path), "sha256": sha256_file(path), "rows": len(done)}],
            params={**summary, "override_reason": cleared.model.override_reason},
        ),
    )
    return summary


def write_predictions(root: Path, out: Path, model: str) -> Path:
    """Teacher labels -> predictions.jsonl for eval. Fails early unless every item has an ok label."""
    pack = load_pack(root)
    psha = prompt_sha(root, pack)
    rows = {}
    for ln in (out / "label" / "labels.jsonl").read_text().splitlines():
        r = json.loads(ln)
        if r.get("ok") and (r["prompt_sha"], r["model"]) == (psha, model):
            rows[r["item"]] = r
    items = heldout.read_texts(root, pack, out, purpose="gate")
    missing = [i["id"] for i in items if i["id"] not in rows]
    if missing:
        raise ValueError(
            f"{len(missing)} texts have no valid teacher label yet (first: {missing[:3]})"
        )
    p = out / "label" / "predictions.jsonl"
    p.write_text(
        "".join(
            json.dumps({"item": i["id"], "dimension": d, "label": lab}) + "\n"
            for i in items
            for d, lab in rows[i["id"]]["labels"].items()
        )
    )
    return p
