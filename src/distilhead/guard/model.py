"""Teacher-model guard: economy profile, cheapest model, no reasoning/premium without a logged reason."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

ECONOMY_TIERS = frozenset({"economy", "cheap", "cheapest"})
TOOLS = Path(__file__).resolve().parents[3] / "tools" / "resolve_model.mjs"


class ModelRefused(Exception):
    pass


@dataclass(frozen=True)
class ModelChoice:
    provider: str
    model: str
    tier: str
    override_reason: str | None


Resolver = Callable[[str, Mapping[str, str]], dict]


def node_resolver(provider: str, env: Mapping[str, str]) -> dict:
    """Calls the pinned Node shim around llm-model-resolver. The key is passed via env only."""
    out = subprocess.run(
        ["node", str(TOOLS), provider],
        check=False,
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if out.returncode != 0:
        raise ModelRefused(f"resolver failed (exit {out.returncode}): {out.stderr.strip()[:200]}")
    return json.loads(out.stdout)


def resolve_teacher_model(
    provider: str, env: Mapping[str, str], resolver: Resolver = node_resolver
) -> ModelChoice:
    if env.get("LLM_MODEL_RESOLVER_PROFILE") != "economy":
        raise ModelRefused("LLM_MODEL_RESOLVER_PROFILE must be 'economy'")
    r = resolver(provider, env)
    model, tier = r.get("model"), str(r.get("tier", "")).lower()
    if not model:
        raise ModelRefused("resolver returned no model id")
    reason = (env.get("MODEL_OVERRIDE_REASON") or "").strip() or None
    if tier not in ECONOMY_TIERS and reason is None:
        raise ModelRefused(
            f"resolved model {model!r} has tier {tier!r}, not economy; "
            "set MODEL_OVERRIDE_REASON to override (logged)"
        )
    return ModelChoice(provider, model, tier, reason if tier not in ECONOMY_TIERS else None)
