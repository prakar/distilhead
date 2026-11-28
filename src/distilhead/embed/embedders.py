"""Embedders: text list -> L2-normalised float matrix.

HashEmbedder is deterministic, offline, dependency-free: for tests and the toy pack only.
EncoderEmbedder wraps a real frozen encoder (optional extra `encoder`); lazy import.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

from ..pack.schema import Encoder


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray: ...


def _normalise(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(n == 0, 1.0, n)


class HashEmbedder:
    """Hashed bag of lowercase word tokens. No semantics beyond shared words."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        m = np.zeros((len(texts), self.dim))
        for i, t in enumerate(texts):
            for tok in re.findall(r"[a-z0-9']+", t.lower()):
                h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:8], "big")
                m[i, h % self.dim] += 1.0
        return _normalise(m)


class EncoderEmbedder:
    """UNTESTED here (no weights offline). Pinned by pack.encoder revision."""

    def __init__(self, enc: Encoder):
        if set(enc.revision) <= {"0"}:
            raise RuntimeError("pack.encoder.revision is a placeholder: pin a real commit sha")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError("install the encoder extra: uv sync --extra encoder") from e
        self.model = SentenceTransformer(enc.id, revision=enc.revision)
        self.model.max_seq_length = enc.max_len

    def embed(self, texts: list[str]) -> np.ndarray:
        return _normalise(np.asarray(self.model.encode(texts, convert_to_numpy=True)))


def load(kind: str, enc: Encoder) -> Embedder:
    if kind == "hash":
        return HashEmbedder()
    if kind == "encoder":
        return EncoderEmbedder(enc)
    raise ValueError(f"unknown embedder {kind!r}")
