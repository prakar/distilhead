"""The ONLY module allowed to create a provider client (enforced by a test).

Guards 1-4 live in clear_teacher; the client is created only from its result.
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


@dataclass(frozen=True)
class Reply:
    text: str
    tokens_in: int
    tokens_out: int  # includes thinking tokens: they are billed as output


class GeminiClient:
    """UNTESTED against the live API from the build sandbox. Only reachable via create_client."""

    def __init__(self, model: str, api_key: str):
        from google import genai
        from google.genai import types

        self._types = types
        self._model = model
        self._client = genai.Client(api_key=api_key)

    def generate(self, system: str, user: str, max_out: int) -> Reply:
        t = self._types
        cfg = {
            "system_instruction": system or None,
            "temperature": 0,
            "response_mime_type": "application/json",
            "max_output_tokens": max_out,
        }
        if "flash" in self._model and "lite" not in self._model:
            cfg["thinking_config"] = t.ThinkingConfig(thinking_budget=0)
        r = self._client.models.generate_content(
            model=self._model, contents=user, config=t.GenerateContentConfig(**cfg)
        )
        u = r.usage_metadata
        out = (u.candidates_token_count or 0) + (getattr(u, "thoughts_token_count", 0) or 0)
        return Reply(r.text or "", u.prompt_token_count or 0, out)


def create_client(cleared: Cleared, api_key: str):
    """Only call with a Cleared produced by clear_teacher: guards 1-4 have already passed."""
    if cleared.model.provider != "gemini":
        raise NotImplementedError(f"no client for provider {cleared.model.provider!r}")
    return GeminiClient(cleared.model.model, api_key)
