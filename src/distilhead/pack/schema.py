"""Pack schema. Generic vocabulary only: dimension, label set, polarity, bar."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PackInfo(_M):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    licence: str


class Dimension(_M):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    definition: str
    label_set: str


class Polarity(_M):
    opposed: list[list[str]]  # exactly two groups: reversal = one side vs the other

    @model_validator(mode="after")
    def _two_groups(self):
        if len(self.opposed) != 2 or not all(self.opposed):
            raise ValueError("polarity.opposed needs exactly two non-empty groups")
        if set(self.opposed[0]) & set(self.opposed[1]):
            raise ValueError("polarity.opposed groups overlap")
        return self


class LabelSet(_M):
    kind: Literal["categorical", "ordinal"]
    labels: list[str] = Field(min_length=2)
    abstain: str | None = None
    polarity: Polarity


class TeacherOutput(_M):
    """Where the teacher's JSON puts per-dimension readings. Names are pack data, not core."""

    list_key: str = "items"
    id_key: str = "id"
    label_key: str = "label"
    quote_key: str = "quote"


class Demotion(_M):
    """If a reading has label `from_label` and field `field` equals `equals`, relabel it `to_label`."""

    from_label: str
    field: str
    equals: str
    to_label: str


class Teacher(_M):
    prompt_file: str
    prompt_version: str
    evidence_quote: Literal["required", "optional"] = "required"
    providers: list[str] = ["gemini"]
    profile: Literal["economy"] = "economy"
    cap_usd: float = 5.0
    output: TeacherOutput = TeacherOutput()
    demote: list[Demotion] = []

    @model_validator(mode="after")
    def _cap(self):
        if not (0 < self.cap_usd <= 5.0):
            raise ValueError("teacher.cap_usd must be in (0, 5]; raising needs the CLI flag")
        if not self.providers:
            raise ValueError("teacher.providers must not be empty")
        return self


class Encoder(_M):
    id: str
    revision: str
    sha256: str
    max_len: int = Field(gt=0)
    pooling: Literal["mean", "cls"]


class Head(_M):
    type: Literal["logreg"] = "logreg"
    class_weight: str = "balanced"
    seed: int
    c_grid: list[float] = Field(min_length=1)


class Files(_M):
    corpus: str
    heldout: str
    reference: str
    locks: str
    prototypes: str
    bar: str
    denylist: str = "denylist.txt"


class Pack(_M):
    schema_version: Literal[1]
    pack: PackInfo
    dimensions: list[Dimension] = Field(min_length=1)
    label_sets: dict[str, LabelSet]
    teacher: Teacher
    files: Files
    encoder: Encoder
    head: Head


class Threshold(_M):
    metric: Literal["exact", "same_side", "reversals", "coverage"]
    op: Literal["<=", ">="]
    value: float


class Bar(_M):
    thresholds: list[Threshold] = Field(min_length=1)
    scope: str  # human-readable description of counted cells, e.g. "all non-locked cells"
    per_dimension_floors: dict[str, list[Threshold]] = {}
