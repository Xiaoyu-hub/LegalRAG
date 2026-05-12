"""Embedder using BGE-large-en-v1.5 via SentenceTransformer.

Per D-11: BGE-large-en-v1.5 embedding model.
Per D-12: batch_size=32 for embedding generation.
Singleton pattern - one model instance shared across the app.
"""
import os
import numpy as np
from sentence_transformers import SentenceTransformer

# Per BGE specification: for short query to long passage (s2p)
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

DEFAULT_MODEL = "BAAI/bge-large-en-v1.5"
# Fallback local cache path used when hub download fails (SSL issues)
_LOCAL_CACHE = os.path.join(
    os.path.expanduser("~"),
    ".cache/huggingface/hub/models--BAAI--bge-large-en-v1.5/snapshots",
)
_FALLBACK = None
if os.path.isdir(_LOCAL_CACHE):
    entries = sorted(os.listdir(_LOCAL_CACHE))
    if entries:
        _FALLBACK = os.path.join(_LOCAL_CACHE, entries[-1])


def _load_model(name: str) -> SentenceTransformer:
    """Load model with fallback to local cache."""
    try:
        return SentenceTransformer(name)
    except Exception:
        if _FALLBACK and os.path.isdir(_FALLBACK):
            return SentenceTransformer(_FALLBACK)
        raise


class Embedder:
    _instance = None

    def __init__(self, model_name: str = DEFAULT_MODEL):
        if Embedder._instance is not None:
            raise RuntimeError("Use Embedder.get_instance() instead")
        self.model = _load_model(model_name)
        self.model_name = model_name

    @classmethod
    def get_instance(cls, model_name: str = "BAAI/bge-large-en-v1.5"):
        if cls._instance is None:
            cls._instance = cls(model_name)
        return cls._instance

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode passages (no instruction prepended).
        Returns float32 array of shape (n_texts, 1024) with L2-normalized vectors.
        """
        return self.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,  # Per D-12
        )

    def encode_query(self, query: str) -> np.ndarray:
        """Encode query with instruction prepended.
        Returns float32 array of shape (1024,) with L2-normalized vector.
        """
        return self.model.encode(
            [QUERY_INSTRUCTION + query],
            normalize_embeddings=True,
            batch_size=1,
        )[0]

    @property
    def dimension(self) -> int:
        # Use new API name; fall back to old one for older sentence-transformers
        try:
            return self.model.get_embedding_dimension()
        except AttributeError:
            return self.model.get_sentence_embedding_dimension()
