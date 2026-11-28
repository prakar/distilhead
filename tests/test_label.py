import json
from types import SimpleNamespace

import pytest

from distilhead import barlock, cli
from distilhead.guard import cost, teacher
from distilhead.label import run as lrun
from distilhead.pack.validate import load_pack

ENV = {"LLM_MODEL_RESOLVER_PROFILE": "economy"}
TEXTS = {
    "h1": ("Lovely service, will happily come back.", "positive", "low"),
    "h2": ("Terrible experience, I want a refund immediately.", "negative", "high"),
    "h3": ("The report is stored in the shared folder.", "neutral", "low"),
}


class Fake:
    """Stands in for the provider client: records calls, never touches the network."""

    def __init__(self, bad_first=False, quote=None):
        self.calls, self.bad_first, self.quote = 0, bad_first, quote

    def generate(self, system, user, max_out):
        self.calls += 1
        if self.bad_first and self.calls == 1:
            return SimpleNamespace(text="not json", tokens_in=500, tokens_out=10)
        text = next(t for t, *_ in TEXTS.values() if t in user)
        _, s, u = next(v for v in TEXTS.values() if v[0] == text)
        q = self.quote if self.quote is not None else text.split(",")[0]
        rows = [{"id": "sentiment", "label": s, "quote": q if s != "neutral" else ""},
                {"id": "urgency", "label": u, "quote": q if u != "low" else ""}]  # fmt: skip
        return SimpleNamespace(text=json.dumps({"items": rows}), tokens_in=500, tokens_out=100)


def clear(toy, tmp_path, cap=None):
    res = lambda p, e: {"model": "gemini-2.5-flash", "tier": "economy"}
    return teacher.clear_teacher(
        toy, "gemini", ENV, tmp_path / "out/label/cost_ledger.jsonl", cap, res
    )


def test_pilot_cost_and_predictions_and_gate(toy, tmp_path):
    barlock.lock(toy)
    out, f = tmp_path / "out", Fake()
    s = lrun.run_label(toy, out, clear(toy, tmp_path), f.generate, ENV, progress=lambda m: None)
    assert s["items_done"] == 3 and f.calls == 3
    assert s["spent_usd"] == pytest.approx(3 * cost.call_cost((0.30, 2.50), 500, 100))
    assert s["usd_extrapolated_all_items"] == pytest.approx(s["spent_usd"])
    p = lrun.write_predictions(toy, out, "gemini-2.5-flash")
    assert len(p.read_text().splitlines()) == 6
    rep = __import__("distilhead.eval.harness", fromlist=["x"]).run_eval(
        toy, p, out, step="gate", purpose="gate"
    )
    assert rep["bar_pass"] and rep["overall"]["reversals"] == 0


def test_resume_is_idempotent_and_never_recalls(toy, tmp_path):
    barlock.lock(toy)
    out, f = tmp_path / "out", Fake()
    lrun.run_label(toy, out, clear(toy, tmp_path), f.generate, ENV, progress=lambda m: None)
    lrun.run_label(toy, out, clear(toy, tmp_path), f.generate, ENV, progress=lambda m: None)
    assert f.calls == 3  # second run did nothing


def test_retry_after_bad_json(toy, tmp_path):
    barlock.lock(toy)
    f = Fake(bad_first=True)
    s = lrun.run_label(
        toy, tmp_path / "o", clear(toy, tmp_path), f.generate, ENV, progress=lambda m: None
    )
    assert s["items_done"] == 3 and f.calls == 4


def test_cap_stops_before_call_and_is_resumable(toy, tmp_path):
    barlock.lock(toy)
    cl = clear(toy, tmp_path, cap=0.0001)  # below one worst-case call
    f = Fake()
    s = lrun.run_label(toy, tmp_path / "out", cl, f.generate, ENV, progress=lambda m: None)
    assert f.calls == 0 and s["stopped_by_cap"] and s["items_done"] == 0


def test_unverifiable_quote_falls_to_abstain(toy, tmp_path):
    barlock.lock(toy)
    f = Fake(quote="a phrase that is not in the passage")
    out = tmp_path / "out"
    lrun.run_label(toy, out, clear(toy, tmp_path), f.generate, ENV, progress=lambda m: None)
    rows = [json.loads(x) for x in (out / "label/labels.jsonl").read_text().splitlines()]
    assert all(r["labels"] == {"sentiment": "neutral", "urgency": "low"} for r in rows)


def test_refuses_without_bar_lock_before_any_call(toy, tmp_path):
    f = Fake()
    with pytest.raises(barlock.BarLockError):
        lrun.run_label(toy, tmp_path / "o", clear(toy, tmp_path), f.generate, ENV)
    assert f.calls == 0


def test_continue_requires_pilot(toy, tmp_path):
    barlock.lock(toy)
    with pytest.raises(ValueError, match="pilot"):
        lrun.run_label(
            toy, tmp_path / "o", clear(toy, tmp_path), Fake().generate, ENV, continue_full=True
        )


def test_unknown_model_price_refused():
    with pytest.raises(cost.CapRefused):
        cost.price_for("some-unlisted-model", {})
    assert cost.price_for(
        "x", {"DISTILHEAD_PRICE_IN_PER_M": "1", "DISTILHEAD_PRICE_OUT_PER_M": "2"}
    ) == (1.0, 2.0)


def test_demotion_rule(toy):
    from distilhead.pack.schema import Demotion

    pk = load_pack(toy).model_copy(deep=True)
    pk.teacher.demote = [
        Demotion(from_label="negative", field="tone", equals="reported", to_label="neutral")
    ]
    rd = [{"id": "sentiment", "label": "negative", "quote": "Terrible experience", "tone": "reported"},
          {"id": "urgency", "label": "low", "quote": ""}]  # fmt: skip
    got = lrun.effective_labels(rd, "Terrible experience, I want a refund", pk)
    assert got["sentiment"] == "neutral"


def test_dry_run_calls_nothing(toy, tmp_path, capsys):
    assert cli.main(["label", str(toy), "--out", str(tmp_path / "o"), "--dry-run"]) == 0
    assert "calls: 3" in capsys.readouterr().out
    assert not (tmp_path / "o" / "label").exists()


def test_label_cli_refuses_without_key(toy, tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert cli.main(["label", str(toy), "--out", str(tmp_path / "o")]) == 1
