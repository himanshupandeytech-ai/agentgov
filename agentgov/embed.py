"""Local embedding helper - loaded lazily so the base tool stays dependency-light."""

from __future__ import annotations

from functools import lru_cache

from .config import EMBED_MODEL


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBED_MODEL)


def embed(text: str) -> list[float]:
    return _model().encode(text, normalize_embeddings=True).tolist()
