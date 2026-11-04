"""cross-encoder 重排器：把召回结果精排一遍。
- D-17：用 ms-marco-MiniLM-L-6-v2（轻量、CPU 可跑）
- D-18：接混合检索给的 10 条候选，重排后留 5 条
关键（第 4 个坑）：cross-encoder 最长 512 token，超长片段会被分词器截断，尾部信息直接丢。"""
import os
import urllib.request
import ssl
from sentence_transformers import CrossEncoder


def _latest_snapshot(cache_dir: str) -> str | None:
    """从 HF 缓存目录里挑最新的 snapshot 子目录。

    现代 huggingface_hub 的布局是 snapshots/<commit-sha>/，早期文档里的
    snapshots/main 只是别名，实际下载后不会存在。所以不能写死 main，
    否则离线兜底永远不命中（表现为 Reranker 用例被 skip）。
    """
    snapshots = os.path.join(cache_dir, "snapshots")
    if not os.path.isdir(snapshots):
        return None
    entries = [e for e in os.listdir(snapshots)
               if os.path.isdir(os.path.join(snapshots, e))]
    if not entries:
        return None
    entries.sort(key=lambda e: os.path.getmtime(os.path.join(snapshots, e)))
    return os.path.join(snapshots, entries[-1])


def _local_cache_dirs() -> list[str]:
    """列出本机 HF 缓存里所有 cross-encoder 模型目录。

    不能从模型名拼目录名：`cross-encoder/ms-marco-MiniLM-L-6-v2` 在 hub 上
    实际重定向到仓库 `ms-marco-MiniLM-L6-v2`（少一个连字符），拼出来的目录名
    与真实缓存不一致，离线时就找不到。所以直接扫 `models--cross-encoder--*`。
    """
    hub = os.path.join(os.path.expanduser("~"), ".cache/huggingface/hub")
    if not os.path.isdir(hub):
        return []
    return [os.path.join(hub, d) for d in sorted(os.listdir(hub))
            if d.startswith("models--cross-encoder--")]


class Reranker:
    """cross-encoder 重排器，模型是 ms-marco-MiniLM-L-6-v2。"""
    
    _instance = None
    _model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """加载 cross-encoder 模型。hub 下载失败（常见于证书/网络问题）时，回退到本地缓存的 snapshot 目录。"""
        if Reranker._instance is not None:
            raise RuntimeError("Use Reranker.get_instance() instead")
        
        try:
            self.model = CrossEncoder(model_name, max_length=512)
        except Exception:
            for cache_dir in _local_cache_dirs():
                local = _latest_snapshot(cache_dir)
                if local:
                    self.model = CrossEncoder(local, max_length=512)
                    break
            else:
                raise
        
        self.model_name = model_name
    
    @classmethod
    def get_instance(cls, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """取重排器单例。"""
        if cls._instance is None:
            cls._instance = cls(model_name)
        return cls._instance
    
    def rerank(
        self,
        query: str,
        passages: list[str],
        top_k: int = 5
    ) -> list[dict]:
        """用 cross-encoder 给候选片段按与查询的相关性重新打分排序。
        参数：
        - query：用户查询
        - passages：待重排的片段文本列表
        - top_k：返回条数（D-18 定 5）
        返回：dict 列表，含 corpus_id、score、text，按分数降序"""
        if not passages:
            return []

        from backend.observability import span as _span

        with _span("retrieval.rerank", **{"rerank.model": self.model_name,
                                          "rerank.inputs": len(passages),
                                          "rerank.top_k": top_k}) as sp:
            results = self.model.rank(query, passages, top_k=top_k)
            sp.set_attribute("rerank.returned", len(results))

        return [
            {
                "corpus_id": r["corpus_id"],
                "score": float(r["score"]),
                "text": passages[r["corpus_id"]]
            }
            for r in results
        ]
