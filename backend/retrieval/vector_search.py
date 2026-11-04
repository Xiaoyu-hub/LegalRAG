"""FAISS 向量检索。
- D-13：用 IndexFlatIP 做精确检索（不近似，数据量小的时候最稳）
- 向量先做 L2 归一化，这样内积等于余弦相似度"""
import os
import warnings
import numpy as np


class VectorSearch:
    # 按租户隔离的索引实例：一个进程里每个 tenant 一套 FAISS 索引
    _instances: dict[str, "VectorSearch"] = {}

    def __init__(self, dimension: int = 1024, tenant: str = "demo"):
        if tenant in VectorSearch._instances:
            raise RuntimeError("Use VectorSearch.get_instance() instead")
        self.tenant = tenant
        self.dimension = dimension
        self._init_index()
        self.chunk_ids = []  # FAISS 位置 -> 业务主键的映射表
        self.mapping_trusted = False

    def _init_index(self):
        import faiss
        self.index = faiss.IndexFlatIP(self.dimension)

    @classmethod
    def get_instance(cls, dimension: int = None, tenant: str = "demo"):
        if tenant not in cls._instances:
            cls._instances[tenant] = cls(dimension or 1024, tenant)
        return cls._instances[tenant]

    @classmethod
    def drop_tenant(cls, tenant: str):
        """丢弃某个租户的索引实例（测试与删除租户时用）。"""
        cls._instances.pop(tenant, None)

    def add(self, embeddings: np.ndarray, chunk_ids: list[int] | None = None):
        """把向量写入索引。发现不是单位长度就自动 L2 归一化——IndexFlatIP 的前提就是所有向量单位长度，否则内积不等于余弦。"""
        import faiss
        # 检查是否需要对向量做归一化
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
        self.mapping_trusted = len(self.chunk_ids) == self.index.ntotal

    def search(self, query_vec: np.ndarray, k: int = 10) -> tuple[np.ndarray, np.ndarray]:
        """检索最近邻。
        参数：
        - query_vec：L2 归一化的查询向量，形状 (dim,)
        - k：返回条数
        返回：(distances, indices) 两个 FAISS 结果数组；注意 indices 是**索引内部位置**，不是业务主键"""
        import faiss
        # 确保查询向量是二维且已归一化
        query_2d = query_vec.reshape(1, -1).astype(np.float32)
        norms = np.linalg.norm(query_2d, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-5):
            warnings.warn("Query vector not normalized. Auto-normalizing.")
            faiss.normalize_L2(query_2d)

        distances, indices = self.index.search(query_2d, k)
        return distances, indices

    def get_chunk_ids_for_indices(self, indices: np.ndarray) -> list[int]:
        """把 FAISS 位置映射成业务主键。"""
        return [self.chunk_ids[i] if i != -1 else -1 for i in indices[0]]

    def search_ids(self, query_vec: np.ndarray, k: int = 10) -> list[tuple[int, float]]:
        """搜索并直接返回 (chunk_id, score)。

        上层（HybridSearch / Pipeline / API）只应看到业务 id；位置映射留在本层，
        否则调用方很容易把位置当主键用（历史缺陷）。
        """
        distances, indices = self.search(query_vec, k=k)
        out: list[tuple[int, float]] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            if idx < len(self.chunk_ids):
                out.append((int(self.chunk_ids[idx]), float(dist)))
            else:
                # 映射缺失时不猜业务 id，宁可少返回
                continue
        return out

    def save(self, path: str):
        """Save FAISS index to file, plus the position→chunk_id mapping.

        只存向量是不够的：FAISS 内部只有位置（0..N-1），而 SQLite 主键从 1 开始，
        两者不是一个 id 空间。映射必须与索引一起落盘，否则重启后只能回退成
        range(ntotal)，同一份索引会两种语义（重启前后），造成“每条命中偏一条”。
        两个文件都走 tmp + os.replace 的原子写法。
        """
        import faiss
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + ".tmp"
        faiss.write_index(self.index, tmp_path)
        os.replace(tmp_path, path)

        ids_path = self._ids_path(path)
        tmp_ids = ids_path + ".tmp"
        np.save(tmp_ids, np.asarray(self.chunk_ids, dtype=np.int64))
        os.replace(tmp_ids + ".npy", ids_path)

    @staticmethod
    def _ids_path(path: str) -> str:
        """映射文件路径：与索引同目录，便于一起备份/回滚。"""
        return path + ".ids.npy"

    def load(self, path: str, chunk_ids: list[int] | None = None):
        """Load FAISS index from file.

        优先用显式传入的 chunk_ids；其次读旁边的 .ids.npy；都没有才回退
        range(ntotal)，并把 mapping_trusted 置 False，让调用方自行决定重建。
        """
        import faiss
        if not os.path.exists(path):
            raise FileNotFoundError(f"Index file not found: {path}")
        self.index = faiss.read_index(path)
        self.dimension = self.index.d
        self.mapping_trusted = False

        if chunk_ids:
            self.chunk_ids = list(chunk_ids)
            self.mapping_trusted = len(self.chunk_ids) == self.index.ntotal
            return

        ids_path = self._ids_path(path)
        if os.path.exists(ids_path):
            loaded = np.load(ids_path).tolist()
            if len(loaded) == self.index.ntotal:
                self.chunk_ids = loaded
                self.mapping_trusted = True
                return

        # 映射文件缺失或长度不符：不猜，交给调用方按数据库重建
        self.chunk_ids = list(range(self.index.ntotal))

    def mapping_matches(self, expected_ids: list[int]) -> bool:
        """校验映射与数据库 id 集合是否一致（集合比较，不管顺序）。

        不一致的典型成因：删过文档、重传同名文件、索引文件与 .ids.npy 不同步。
        """
        return sorted(self.chunk_ids) == sorted(expected_ids)

    @property
    def size(self) -> int:
        return self.index.ntotal

    def reset(self, dimension: int | None = None):
        """Clear the index.

        dimension 给出时顺便重建索引维度（单例被不同维度的用例共享时必需，
        否则 faiss 会在 add 时报 d != self.d）。
        """
        if dimension is not None:
            self.dimension = dimension
        self._init_index()
        self.chunk_ids = []
        self.mapping_trusted = False
