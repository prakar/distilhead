"""Cost cap and append-only ledger. Cap is always finite, in (0, DEFAULT], raisable only via a logged call."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_CAP_USD = 5.0
PILOT_ITEMS = 20


class CapExceeded(Exception):
    pass


class CapRefused(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Ledger:
    """State is derived from the jsonl file, so kill/re-run resumes exactly."""

    def __init__(self, path: Path, cap_usd: float | None = None):
        self.path = path
        events = self._read()
        caps = [e for e in events if e["type"] == "cap"]
        if caps:
            self.cap = caps[-1]["cap_usd"]
            if cap_usd is not None and cap_usd < self.cap:
                self._set_cap(cap_usd, "cli", "lowered")
        else:
            c = DEFAULT_CAP_USD if cap_usd is None else cap_usd
            self._validate(c)
            self._set_cap(c, "init", "initial cap")

    @staticmethod
    def _validate(c: float) -> None:
        if not isinstance(c, (int, float)) or not math.isfinite(c) or c <= 0:
            raise CapRefused(f"cap must be finite and > 0, got {c!r}")

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def _append(self, ev: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps({"ts": _now(), **ev}, sort_keys=True) + "\n")
            f.flush()

    def _set_cap(self, cap: float, who: str, reason: str) -> None:
        self._validate(cap)
        self._append({"type": "cap", "cap_usd": float(cap), "who": who, "reason": reason})
        self.cap = float(cap)

    def raise_cap(self, new_cap: float, who: str, reason: str) -> None:
        """The only way to raise the cap. Requires who + reason; logged."""
        if not who.strip() or not reason.strip():
            raise CapRefused("raising the cap needs non-empty who and reason")
        self._validate(new_cap)
        if new_cap <= self.cap:
            raise CapRefused("new cap must exceed current cap")
        self._set_cap(new_cap, who, reason)

    @property
    def spent(self) -> float:
        return sum(e["cost_usd"] for e in self._read() if e["type"] == "call")

    def check(self, worst_case_usd: float) -> None:
        """Call before every API call."""
        if not math.isfinite(worst_case_usd) or worst_case_usd < 0:
            raise CapExceeded(f"invalid worst-case cost {worst_case_usd!r}")
        if self.spent + worst_case_usd > self.cap + 1e-12:
            raise CapExceeded(
                f"spent {self.spent:.4f} + worst-case {worst_case_usd:.4f} > cap {self.cap:.2f}"
            )

    def record(self, key: str, model: str, cost_usd: float, **extra) -> None:
        """Call after every API call, with the actual cost."""
        if not math.isfinite(cost_usd) or cost_usd < 0:
            raise ValueError(f"invalid cost {cost_usd!r}")
        self._append({"type": "call", "key": key, "model": model, "cost_usd": cost_usd, **extra})

    def calls(self) -> int:
        return sum(1 for e in self._read() if e["type"] == "call")


def extrapolate(measured_usd: float, n_measured: int, n_total: int) -> float:
    if n_measured <= 0:
        raise ValueError("need at least one measured item")
    return measured_usd / n_measured * n_total
