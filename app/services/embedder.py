# -*- coding: utf-8 -*-
"""Jina AI 嵌入封装 —— 替代本地 BGE"""
from typing import List
import time
import requests
import numpy as np
from app.config import JINA_API_KEY, JINA_EMBED_MODEL, JINA_EMBED_DIM


def embed(texts: List[str], max_retries: int = 5) -> np.ndarray:
    """批量嵌入，返回 (N, dim) 数组。遇 429 限流自动退避重试。"""
    if not texts:
        return np.zeros((0, JINA_EMBED_DIM), dtype=np.float32)

    if not JINA_API_KEY:
        raise RuntimeError("JINA_API_KEY 未配置")

    for attempt in range(max_retries):
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
            timeout=120,
        )
        if resp.status_code == 200:
            break
        if resp.status_code == 429 and attempt < max_retries - 1:
            wait = min(2 ** attempt * 3, 30)  # 3, 6, 12, 24, 30
            print(f"  [Jina 限流] 等待 {wait}s 后重试 ({attempt+1}/{max_retries})")
            time.sleep(wait)
            continue
        raise RuntimeError(f"Jina 嵌入失败: {resp.status_code} {resp.text}")

    data = resp.json()
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
