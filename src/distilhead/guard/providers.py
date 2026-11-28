"""Provider allowlist. Not legal advice: see DECISIONS.md; users must check their own provider terms."""

from __future__ import annotations

from pathlib import Path

import yaml

DENY = frozenset({"xai", "openai"})
DEFAULT_ALLOWED = frozenset({"gemini"})
TERMS_FIELDS = ("clause_url", "date", "summary")


class ProviderRefused(Exception):
    pass


def check_provider(provider: str, allowlist: list[str], pack_root: Path) -> None:
    p = provider.strip().lower()
    if p in DENY:
        raise ProviderRefused(f"provider {p!r} is hard-denied (see DECISIONS.md)")
    if p not in [a.lower() for a in allowlist]:
        raise ProviderRefused(f"provider {p!r} not in pack allowlist {allowlist}")
    if p in DEFAULT_ALLOWED:
        return
    rec = pack_root / "terms" / f"{p}.yaml"
    if not rec.is_file():
        raise ProviderRefused(f"provider {p!r} needs a terms record at {rec}")
    data = yaml.safe_load(rec.read_text()) or {}
    missing = [k for k in TERMS_FIELDS if not data.get(k)]
    if missing:
        raise ProviderRefused(f"terms record {rec} missing fields {missing}")
