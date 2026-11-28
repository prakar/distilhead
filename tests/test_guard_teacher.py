import pytest

from distilhead.guard import teacher
from distilhead.guard.cost import CapRefused
from distilhead.guard.model import ModelRefused
from distilhead.guard.providers import ProviderRefused

ENV = {"LLM_MODEL_RESOLVER_PROFILE": "economy"}


def res(tier="economy"):
    calls = []

    def f(p, e):
        calls.append(p)
        return {"model": "m", "tier": tier}

    f.calls = calls
    return f


def test_clears_and_creates_ledger(toy, tmp_path):
    r = res()
    c = teacher.clear_teacher(toy, "gemini", ENV, tmp_path / "l.jsonl", resolver=r)
    assert c.model.model == "m" and c.ledger.cap == 5.0 and r.calls == ["gemini"]


def test_invalid_pack_stops_before_resolver(toy, tmp_path):
    (toy / "bar.yaml").unlink()
    r = res()
    with pytest.raises(ValueError):
        teacher.clear_teacher(toy, "gemini", ENV, tmp_path / "l.jsonl", resolver=r)
    assert r.calls == []


def test_denied_provider_stops_before_resolver(toy, tmp_path):
    r = res()
    with pytest.raises(ProviderRefused):
        teacher.clear_teacher(toy, "xai", ENV, tmp_path / "l.jsonl", resolver=r)
    assert r.calls == []


def test_model_guard_stops_before_ledger(toy, tmp_path):
    with pytest.raises(ModelRefused):
        teacher.clear_teacher(toy, "gemini", ENV, tmp_path / "l.jsonl", resolver=res("premium"))
    assert not (tmp_path / "l.jsonl").exists()


def test_bad_cap_refused(toy, tmp_path):
    with pytest.raises(CapRefused):
        teacher.clear_teacher(toy, "gemini", ENV, tmp_path / "l.jsonl", cap_usd=0, resolver=res())


def test_no_client_for_unsupported_provider(toy, tmp_path):
    c = teacher.clear_teacher(toy, "gemini", ENV, tmp_path / "l.jsonl", resolver=res())
    other = teacher.Cleared(c.model.__class__("other", "m", "economy", None), c.ledger)
    with pytest.raises(NotImplementedError):
        teacher.create_client(other, "k")
