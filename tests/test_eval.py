import json

import pytest

from distilhead import barlock, cli, zeroshot
from distilhead.embed.embedders import HashEmbedder
from distilhead.eval import harness, heldout, metrics
from distilhead.pack.validate import load_pack


def write_preds(path, rows):
    path.write_text(
        "".join(json.dumps(dict(zip(("item", "dimension", "label"), r))) + "\n" for r in rows)
    )


PERFECT = [
    ("h1", "sentiment", "positive"), ("h1", "urgency", "low"),
    ("h2", "sentiment", "negative"), ("h2", "urgency", "high"),
    ("h3", "sentiment", "neutral"), ("h3", "urgency", "low"),
]  # fmt: skip


def test_metrics_polarity(toy):
    pack = load_pack(toy)
    c = lambda cand, ref: metrics.Cell("i", "sentiment", cand, ref)
    cells = [c("positive", "negative"), c("neutral", "negative"), c("positive", "positive"),
             c("neutral", "neutral")]  # fmt: skip
    m = metrics.compute(cells, pack)
    assert m["reversals"] == 1  # only positive vs negative
    assert m["exact"] == 0.5
    assert m["same_side"] == 0.5  # neutral vs negative is mid vs A: different side, not a reversal
    assert m["coverage"] == 0.5  # neutral is the abstain label
    assert m["cand_only"] == 0 and m["ref_only"] == 1  # neutral vs negative: reference-only


def test_eval_perfect_and_locked_excluded(toy, tmp_path):
    barlock.lock(toy)
    p = tmp_path / "p.jsonl"
    write_preds(p, PERFECT[:5] + [("h3", "urgency", "high")])  # wrong, but locked cell
    rep = harness.run_eval(toy, p, tmp_path / "out")
    assert rep["cells_locked"] == 1 and rep["cells_counted"] == 5
    assert rep["overall"]["exact"] == 1.0 and rep["overall"]["reversals"] == 0
    assert rep["bar_pass"]
    assert list(rep["per_dimension"]) == ["sentiment", "urgency"]


def test_eval_reversal_fails_bar(toy, tmp_path):
    barlock.lock(toy)
    p = tmp_path / "p.jsonl"
    write_preds(p, [("h1", "sentiment", "negative")] + PERFECT[1:])
    rep = harness.run_eval(toy, p, tmp_path / "out")
    assert rep["overall"]["reversals"] == 1 and not rep["bar_pass"]
    assert cli.main(["eval", str(toy), "--predictions", str(p), "--out", str(tmp_path / "o2"),
                     "--require-pass"]) == 1  # fmt: skip


def test_eval_refuses_without_or_with_changed_bar_lock(toy, tmp_path):
    p = tmp_path / "p.jsonl"
    write_preds(p, PERFECT)
    with pytest.raises(barlock.BarLockError):
        harness.run_eval(toy, p, tmp_path / "out")
    barlock.lock(toy)
    (toy / "bar.yaml").write_text((toy / "bar.yaml").read_text().replace("0.8", "0.1"))
    with pytest.raises(barlock.BarLockError):
        harness.run_eval(toy, p, tmp_path / "out")
    assert not (tmp_path / "out" / heldout.TOUCH_LOG).exists()  # refused before any held-out read


def test_eval_fails_early_on_bad_predictions(toy, tmp_path):
    barlock.lock(toy)
    p = tmp_path / "p.jsonl"
    write_preds(p, PERFECT[:1] + PERFECT[2:])
    with pytest.raises(ValueError, match="missing prediction"):
        harness.run_eval(toy, p, tmp_path / "out")
    write_preds(p, [("h1", "sentiment", "bogus")] + PERFECT[1:])
    with pytest.raises(ValueError, match="invalid label"):
        harness.run_eval(toy, p, tmp_path / "out")


def test_rule_locks_refused(toy):
    (toy / "locks.yaml").write_text("locks:\n  - {id: r, rule: some_rule, reason: x}\n")
    with pytest.raises(ValueError, match="rule-based"):
        heldout.read_locks(toy, load_pack(toy))


def test_every_heldout_read_is_logged(toy, tmp_path):
    barlock.lock(toy)
    out = tmp_path / "out"
    pred = zeroshot.predict(toy, HashEmbedder(), out)
    harness.run_eval(toy, pred, out)
    rows = [json.loads(x) for x in (out / heldout.TOUCH_LOG).read_text().splitlines()]
    assert [r["purpose"] for r in rows] == ["zeroshot", "eval"]
    assert all(len(r["sha256"]) == 64 for r in rows)
    man = json.loads((out / "eval" / "manifest.json").read_text())
    assert man["params"]["heldout_touches"] == 2


def test_zeroshot_on_toy_is_offline_free_and_deterministic(toy, tmp_path):
    barlock.lock(toy)
    a = zeroshot.predict(toy, HashEmbedder(), tmp_path / "a")
    b = zeroshot.predict(toy, HashEmbedder(), tmp_path / "b")
    assert a.read_text() == b.read_text()
    assert len(a.read_text().splitlines()) == 6  # 3 items x 2 dimensions
    man = json.loads((tmp_path / "a" / "zeroshot" / "manifest.json").read_text())
    assert man["params"]["cost_usd"] == 0
    rep = harness.run_eval(toy, a, tmp_path / "a")
    assert rep["cells_counted"] == 5
    print(harness.format_report(rep))


def test_cli_end_to_end(toy, tmp_path, capsys):
    assert cli.main(["bar-lock", str(toy)]) == 0
    out = str(tmp_path / "o")
    assert cli.main(["zeroshot", str(toy), "--out", out, "--embedder", "hash"]) == 0
    assert cli.main(["eval", str(toy), "--predictions", f"{out}/zeroshot/predictions.jsonl",
                     "--out", out]) == 0  # fmt: skip
    assert "OVERALL" in capsys.readouterr().out


def test_heldout_files_read_only_via_reader():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "distilhead"
    allowed = {"eval/heldout.py", "pack/validate.py", "pack/schema.py"}
    for f in src.rglob("*.py"):
        rel = f.relative_to(src).as_posix()
        if rel in allowed:
            continue
        t = f.read_text()
        assert "files.heldout" not in t and "files.reference" not in t, rel
