import pytest

from distilhead.guard.model import ModelRefused, resolve_teacher_model

ENV = {"LLM_MODEL_RESOLVER_PROFILE": "economy"}


def fake(tier, model="m-small"):
    return lambda p, e: {"provider": p, "model": model, "tier": tier}


def test_economy_ok():
    c = resolve_teacher_model("gemini", ENV, fake("economy"))
    assert c.model == "m-small" and c.override_reason is None


@pytest.mark.parametrize("env", [{}, {"LLM_MODEL_RESOLVER_PROFILE": "premium"}])
def test_profile_must_be_economy(env):
    called = []
    with pytest.raises(ModelRefused):
        resolve_teacher_model("gemini", env, lambda p, e: called.append(1))
    assert not called  # resolver never reached


@pytest.mark.parametrize("tier", ["reasoning", "premium", "", "unknown"])
def test_non_economy_refused_without_reason(tier):
    with pytest.raises(ModelRefused, match="MODEL_OVERRIDE_REASON"):
        resolve_teacher_model("gemini", ENV, fake(tier))


def test_override_logged():
    c = resolve_teacher_model(
        "gemini", {**ENV, "MODEL_OVERRIDE_REASON": "needed for X"}, fake("premium")
    )
    assert c.override_reason == "needed for X"


def test_blank_reason_is_no_reason():
    with pytest.raises(ModelRefused):
        resolve_teacher_model("gemini", {**ENV, "MODEL_OVERRIDE_REASON": "  "}, fake("premium"))


def test_no_model():
    with pytest.raises(ModelRefused):
        resolve_teacher_model("gemini", ENV, lambda p, e: {"tier": "economy"})
