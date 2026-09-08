# -*- coding: utf-8 -*-
"""Pinecone 向量库封装 —— 接口与 Chroma 保持一致"""
from typing import List, Optional
import pinecone
from app.config import PINECONE_API_KEY, PINECONE_ENV, PINECONE_INDEX, JINA_EMBED_DIM


_client: Optional[pinecone.Pinecone] = None
_index: Optional[pinecone.Index] = None


def get_index() -> pinecone.Index:
    """懒加载 Pinecone index"""
    global _client, _index
    if _index is not None:
        return _index

    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY 未配置")

    _client = pinecone.Pinecone(api_key=PINECONE_API_KEY)

    # 检查 index 是否存在
    available = [i.name for i in _client.list_indexes()]
    if PINECONE_INDEX not in available:
        _client.create_index(
            name=PINECONE_INDEX,
            dimension=JINA_EMBED_DIM,
            metric="cosine",
        )

    _index = _client.Index(PINECONE_INDEX)
    return _index


def upsert(ids: List[str], vectors: List[List[float]],
           documents: List[str], metadatas: List[dict], batch_size: int = 100):
    """批量 upsert（Pinecone v10 API: vectors=[(id, values, metadata), ...]）"""
    idx = get_index()
    for start in range(0, len(ids), batch_size):
        end = start + batch_size
        # 把 text 存入 metadata（Pinecone v10 不再支持 documents 参数）
        batch = []
        for i in range(start, end):
            meta = dict(metadatas[i])
            if "text" not in meta and i < len(documents):
                meta["text"] = documents[i]
            batch.append((ids[i], vectors[i], meta))
        idx.upsert(vectors=batch)


def query(vector: List[float], top_k: int = 10,
          filter_meta: Optional[dict] = None) -> dict:
    """向量搜索，返回 raw pinecone 结果"""
    idx = get_index()
    kw = {"vector": vector, "top_k": top_k, "include_metadata": True, "include_values": False}
    if filter_meta:
        kw["filter"] = filter_meta
    return idx.query(**kw)


def delete_by_id(ids: List[str]):
    idx = get_index()
    idx.delete(ids=ids)


def delete_by_filter(filter_meta: dict):
    idx = get_index()
    idx.delete(filter=filter_meta)


def describe_index() -> dict:
    """返回 index 统计信息"""
    try:
        idx = get_index()
        stats = idx.describe_index_stats()
        return {
            "total_vector_count": stats.total_vector_count,
            "namespaces": list(stats.namespaces.keys()) if stats.namespaces else [],
            "dimension": JINA_EMBED_DIM,
        }
    except Exception as e:
        return {"error": str(e)}
