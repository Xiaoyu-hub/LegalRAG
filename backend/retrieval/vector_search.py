"""FAISS vector similarity search.

Per D-13: FAISS with IndexFlatIP for exact similarity search.
Uses L2-normalized vectors (cosine similarity via inner product).
"""
import os
import warnings
import numpy as np


class VectorSearch:
    _instance = None

    def __init__(self, dimension: int = 1024):
        if VectorSearch._instance is not None:
            raise RuntimeError("Use VectorSearch.get_instance() instead")
        self.dimension = dimension
        self._init_index()
        self.chunk_ids = []  # Maps FAISS index position -> chunk_id

    def _init_index(self):
        import faiss
        self.index = faiss.IndexFlatIP(self.dimension)

    @classmethod
    def get_instance(cls, dimension: int = None):
        if cls._instance is None:
            if dimension is None:
                dimension = 1024  # BGE-large-en-v1.5 default
            cls._instance = cls(dimension)
        return cls._instance

    def add(self, embeddings: np.ndarray, chunk_ids: list[int] | None = None):
        """Add embeddings to the index.

        Automatically L2-normalizes if vectors are not unit length.
        Per D-13 and Pitfall 2: All vectors MUST be unit-length for IndexFlatIP.
        """
        import faiss
        # Check if normalization needed
        norms = np.linalg.norm(embeddings, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-5):
            warnings.warn("Embeddings not normalized. Auto-normalizing.")
            embeddings = embeddings.copy()
            faiss.normalize_L2(embeddings)

        start_idx = len(self.chunk_ids)
        self.index.add(embeddings)
        if chunk_ids:
            self.chunk_ids.extend(chunk_ids)
        else:
            self.chunk_ids.extend(range(start_idx, start_idx + embeddings.shape[0]))

    def search(self, query_vec: np.ndarray, k: int = 10) -> tuple[np.ndarray, np.ndarray]:
        """Search index for nearest neighbors.

        Args:
            query_vec: L2-normalized query vector of shape (dim,)
            k: Number of results to return
        Returns:
            (distances, indices): FAISS result arrays
        """
        import faiss
        # Ensure query is 2D and normalized
        query_2d = query_vec.reshape(1, -1).astype(np.float32)
        norms = np.linalg.norm(query_2d, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-5):
            warnings.warn("Query vector not normalized. Auto-normalizing.")
            faiss.normalize_L2(query_2d)

        distances, indices = self.index.search(query_2d, k)
        return distances, indices

    def get_chunk_ids_for_indices(self, indices: np.ndarray) -> list[int]:
        """Map FAISS index positions to chunk IDs."""
        return [self.chunk_ids[i] if i != -1 else -1 for i in indices[0]]

    def save(self, path: str):
        """Save FAISS index to file."""
        import faiss
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Write to temp file then rename for atomicity (Pitfall 6)
        tmp_path = path + ".tmp"
        faiss.write_index(self.index, tmp_path)
        os.replace(tmp_path, path)

    def load(self, path: str, chunk_ids: list[int] | None = None):
        """Load FAISS index from file."""
        import faiss
        if not os.path.exists(path):
            raise FileNotFoundError(f"Index file not found: {path}")
        self.index = faiss.read_index(path)
        self.dimension = self.index.d
        if chunk_ids:
            self.chunk_ids = chunk_ids
        else:
            self.chunk_ids = list(range(self.index.ntotal))

    @property
    def size(self) -> int:
        return self.index.ntotal

    def reset(self):
        """Clear the index."""
        self._init_index()
        self.chunk_ids = []
