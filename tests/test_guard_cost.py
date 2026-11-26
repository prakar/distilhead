import json
import math

import pytest

from distilhead.guard.cost import CapExceeded, CapRefused, Ledger, extrapolate


@pytest.mark.parametrize("cap", [0, -1, math.inf, math.nan])
def test_bad_caps_refused(tmp_path, cap):
    with pytest.raises(CapRefused):
        Ledger(tmp_path / "l.jsonl", cap)


def test_default_cap_is_five(tmp_path):
    assert Ledger(tmp_path / "l.jsonl").cap == 5.0


def test_hard_stop_and_resume(tmp_path):
    p = tmp_path / "l.jsonl"
    L = Ledger(p, 1.0)
    L.check(0.6)
    L.record("k1", "m", 0.6)
    with pytest.raises(CapExceeded):
        L.check(0.5)
    L2 = Ledger(p, 1.0)  # fresh process
    assert L2.spent == pytest.approx(0.6) and L2.calls() == 1
    L2.check(0.4)
    L2.record("k2", "m", 0.4)
    with pytest.raises(CapExceeded):
        L2.check(0.0001)


def test_cap_only_lowered_by_constructor_and_logged(tmp_path):
    p = tmp_path / "l.jsonl"
    Ledger(p, 3.0)
    assert Ledger(p, 4.0).cap == 3.0  # asking for more at construction does not raise it
    assert Ledger(p, 2.0).cap == 2.0


def test_raise_cap_logged(tmp_path):
    p = tmp_path / "l.jsonl"
    L = Ledger(p, 1.0)
    with pytest.raises(CapRefused):
        L.raise_cap(2.0, "", "why")
    with pytest.raises(CapRefused):
        L.raise_cap(2.0, "me", " ")
    with pytest.raises(CapRefused):
        L.raise_cap(0.5, "me", "why")
    L.raise_cap(2.0, "me", "bigger corpus")
    assert Ledger(p).cap == 2.0
    last = [json.loads(x) for x in p.read_text().splitlines()][-1]
    assert last["who"] == "me" and last["reason"] == "bigger corpus" and last["cap_usd"] == 2.0


def test_append_only(tmp_path):
    p = tmp_path / "l.jsonl"
    L = Ledger(p, 1.0)
    L.record("a", "m", 0.1)
    before = p.read_text()
    L.record("b", "m", 0.1)
    assert p.read_text().startswith(before)


def test_invalid_costs(tmp_path):
    L = Ledger(tmp_path / "l.jsonl", 1.0)
    with pytest.raises(CapExceeded):
        L.check(math.nan)
    with pytest.raises(ValueError):
        L.record("a", "m", -1)


def test_extrapolate():
    assert extrapolate(0.2, 20, 1000) == pytest.approx(10.0)
    with pytest.raises(ValueError):
        extrapolate(0, 0, 10)
