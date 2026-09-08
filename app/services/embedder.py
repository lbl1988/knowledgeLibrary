# -*- coding: utf-8 -*-
"""Jina AI 嵌入封装 —— 替代本地 BGE"""
from typing import List
import requests
import numpy as np
from app.config import JINA_API_KEY, JINA_EMBED_MODEL, JINA_EMBED_DIM


def embed(texts: List[str]) -> np.ndarray:
    """批量嵌入，返回 (N, dim) 数组"""
    if not texts:
        return np.zeros((0, JINA_EMBED_DIM), dtype=np.float32)

    if not JINA_API_KEY:
        raise RuntimeError("JINA_API_KEY 未配置")

    # Jina v3 兼容 v2 接口
    resp = requests.post(
        "https://api.jina.ai/v1/embeddings",
        headers={
            "Authorization": f"Bearer {JINA_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "model": JINA_EMBED_MODEL,
            "input": texts,
            "embedding_type": "float",
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Jina 嵌入失败: {resp.status_code} {resp.text}")

    data = resp.json()
    # Jina 返回 {"data": [{"embedding": [...], "index": 0}, ...]}
    items = sorted(data["data"], key=lambda x: x["index"])
    vecs = np.array([item["embedding"] for item in items], dtype=np.float32)
    return vecs


def embed_single(text: str) -> np.ndarray:
    """单条嵌入"""
    return embed([text])[0]


def health() -> dict:
    """检查 Key 是否有效"""
    try:
        v = embed(["hello"])
        return {"ok": True, "dim": v.shape[1]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
