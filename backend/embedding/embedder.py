"""向量模型封装：用 SentenceTransformer 加载 BGE-large-en-v1.5。
- D-11：选用 BGE-large-en-v1.5
- D-12：批量编码 batch_size=32
- 单例模式：全应用共享一个模型实例（模型很重，不能每次请求都加载）"""
import os
import numpy as np
from sentence_transformers import SentenceTransformer

# BGE 官方建议：短查询检索长段落（s2p）时，查询侧要加这句指令
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

DEFAULT_MODEL = "BAAI/bge-large-en-v1.5"


def _fallback_snapshot() -> str | None:
    """在模块导入时也能拿到——但缓存可能在导入之后才建好，所以每次调用时现查。

    现代 HF 缓存布局是 snapshots/<commit-sha>/；不能写死 snapshots/main。
    """
    cache_root = os.path.join(
        os.path.expanduser("~"),
        ".cache/huggingface/hub/models--BAAI--bge-large-en-v1.5/snapshots",
    )
    if not os.path.isdir(cache_root):
        return None
    entries = [e for e in os.listdir(cache_root)
               if os.path.isdir(os.path.join(cache_root, e))]
    if not entries:
        return None
    entries.sort(key=lambda e: os.path.getmtime(os.path.join(cache_root, e)))
    return os.path.join(cache_root, entries[-1])


def _load_model(name: str) -> SentenceTransformer:
    """加载模型：先走 hub（能用缓存就用缓存），失败再回退到本地 snapshot 目录。"""
    try:
        return SentenceTransformer(name)
    except Exception:
        fallback = _fallback_snapshot()
        if fallback:
            return SentenceTransformer(fallback)
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
        """编码文档段落（不加指令前缀）。返回 (n_texts, 1024) 的 float32 数组，向量已做 L2 归一化。"""
        return self.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,  # D-12：批量 32
        )

    def encode_query(self, query: str) -> np.ndarray:
        """编码查询（前置 BGE 指令）。返回 (1024,) 的 float32 向量，已 L2 归一化。"""
        return self.model.encode(
            [QUERY_INSTRUCTION + query],
            normalize_embeddings=True,
            batch_size=1,
        )[0]

    @property
    def dimension(self) -> int:
        # 优先用新版 API 名，老版本 sentence-transformers 回退到旧方法名
        try:
            return self.model.get_embedding_dimension()
        except AttributeError:
            return self.model.get_sentence_embedding_dimension()
