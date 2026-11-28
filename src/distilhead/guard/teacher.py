"""The ONLY module allowed to create a provider client (enforced by a test).

Step 0: guards only. Actual client construction arrives with the label step.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..pack.validate import load_pack, validate
from . import providers
from .cost import Ledger
from .model import ModelChoice, Resolver, node_resolver, resolve_teacher_model


@dataclass(frozen=True)
class Cleared:
    model: ModelChoice
    ledger: Ledger


def clear_teacher(
    pack_root: Path,
    provider: str,
    env: Mapping[str, str],
    ledger_path: Path,
    cap_usd: float | None = None,
    resolver: Resolver = node_resolver,
) -> Cleared:
    """Run guards 1-4 in order. Raises before any client could be created."""
    errs = validate(pack_root)
    if errs:
        raise ValueError("pack invalid: " + "; ".join(errs))
    pack = load_pack(pack_root)
    providers.check_provider(provider, pack.teacher.providers, pack_root)
    model = resolve_teacher_model(provider, env, resolver)
    cap = pack.teacher.cap_usd if cap_usd is None else cap_usd
    ledger = Ledger(ledger_path, cap)
    return Cleared(model, ledger)


def create_client(cleared: Cleared):
    raise NotImplementedError("provider client creation is added with the label step")
