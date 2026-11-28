"""Metric registry. Generic: sides come from the pack's declared label-set polarity.

side(label): 'A' / 'B' if the label is in the first / second opposed group, else 'mid'.
  exact      candidate label == reference label
  same_side  side(candidate) == side(reference)   (exact implies same_side)
  reversal   {side(candidate), side(reference)} == {'A', 'B'}
  coverage   candidate is not the label set's abstain label (1.0 when no abstain declared)
  cand_only / ref_only   counts of cells addressed by only one side (abstain vs non-abstain)
All metrics are computed over counted (non-locked) cells.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..pack.schema import LabelSet, Pack


def side(ls: LabelSet, label: str) -> str:
    a, b = ls.polarity.opposed
    return "A" if label in a else "B" if label in b else "mid"


@dataclass(frozen=True)
class Cell:
    item: str
    dimension: str
    candidate: str
    reference: str


def _exact(c: Cell, ls: LabelSet) -> bool:
    return c.candidate == c.reference


def _same_side(c: Cell, ls: LabelSet) -> bool:
    return side(ls, c.candidate) == side(ls, c.reference)


def _reversal(c: Cell, ls: LabelSet) -> bool:
    return {side(ls, c.candidate), side(ls, c.reference)} == {"A", "B"}


def _covered(c: Cell, ls: LabelSet) -> bool:
    return ls.abstain is None or c.candidate != ls.abstain


def _cand_only(c: Cell, ls: LabelSet) -> bool:
    return ls.abstain is not None and c.reference == ls.abstain and c.candidate != ls.abstain


def _ref_only(c: Cell, ls: LabelSet) -> bool:
    return ls.abstain is not None and c.candidate == ls.abstain and c.reference != ls.abstain


# name -> (per-cell predicate, kind). 'count' metrics report an integer, 'rate' a fraction.
REGISTRY = {
    "exact": (_exact, "rate"),
    "same_side": (_same_side, "rate"),
    "reversals": (_reversal, "count"),
    "coverage": (_covered, "rate"),
    "cand_only": (_cand_only, "count"),  # candidate addresses a cell the reference leaves silent
    "ref_only": (_ref_only, "count"),  # reference addresses a cell the candidate leaves silent
}


def compute(cells: list[Cell], pack: Pack) -> dict[str, float]:
    dims = {d.id: pack.label_sets[d.label_set] for d in pack.dimensions}
    out: dict[str, float] = {}
    n = len(cells)
    for name, (fn, kind) in REGISTRY.items():
        hits = sum(1 for c in cells if fn(c, dims[c.dimension]))
        out[name] = hits if kind == "count" else (hits / n if n else 0.0)
    return out


def per_dimension(cells: list[Cell], pack: Pack) -> dict[str, dict[str, float]]:
    by: dict[str, list[Cell]] = defaultdict(list)
    for c in cells:
        by[c.dimension].append(c)
    table = {}
    for d in pack.dimensions:  # pack order
        m = compute(by.get(d.id, []), pack)
        m["cells"] = len(by.get(d.id, []))
        table[d.id] = m
    return table
