# -*- coding: utf-8 -*-
"""搜索路由 —— 语义搜索（Jina+Pinecone）失败时回退到 R2 关键词搜索"""
import json, time
from fastapi import APIRouter, Depends, Query
from app.auth import get_current_user
from app.services.storage import download_bytes, R2_BUCKET_EXTRACTED

router = APIRouter(prefix="/api", tags=["search"])

# R2 提取文本缓存：r2_key -> text
_text_cache: dict[str, str] = {}
_text_cache_ts: dict[str, float] = {}
_TEXT_TTL: float = 600.0  # 10 分钟

# 文档索引缓存
_docs_index_cache: list | None = None
_docs_index_ts: float = 0.0
_INDEX_TTL: float = 300.0


def _get_docs_index() -> list[dict]:
    global _docs_index_cache, _docs_index_ts
    now = time.time()
    if _docs_index_cache and (now - _docs_index_ts) < _INDEX_TTL:
        return _docs_index_cache
    try:
        raw = download_bytes(R2_BUCKET_EXTRACTED, "_docs_index.json")
        _docs_index_cache = json.loads(raw.decode("utf-8"))
        _docs_index_ts = now
    except Exception as e:
        print(f"[search] R2 文档索引读取失败: {e}")
        if not _docs_index_cache:
            return []
    return _docs_index_cache


def _get_extracted_text(r2_key: str) -> str:
    """从 R2 下载提取文本（带缓存）"""
    now = time.time()
    if r2_key in _text_cache and (now - _text_cache_ts.get(r2_key, 0)) < _TEXT_TTL:
        return _text_cache[r2_key]
    try:
        raw = download_bytes(R2_BUCKET_EXTRACTED, r2_key)
        text = raw.decode("utf-8", errors="ignore")
        _text_cache[r2_key] = text
        _text_cache_ts[r2_key] = now
        return text
    except Exception as e:
        print(f"[search] 下载提取文本失败 {r2_key}: {e}")
        return ""


def _keyword_search(q: str, limit: int = 10) -> list[dict]:
    """关键词搜索：遍历 R2 提取文本，返回匹配片段"""
    docs = _get_docs_index()
    q_lower = q.lower()
    results = []

    for d in docs:
        r2_key = d.get("r2_extracted")
        if not r2_key:
            continue
        text = _get_extracted_text(r2_key)
        if not text:
            continue
        # 查找所有匹配位置
        text_lower = text.lower()
        idx = 0
        matches_in_doc = 0
        snippet = ""
        while True:
            pos = text_lower.find(q_lower, idx)
            if pos == -1:
                break
            matches_in_doc += 1
            if not snippet:
                # 取第一个匹配的上下文
                start = max(0, pos - 100)
                end = min(len(text), pos + len(q) + 200)
                snippet = text[start:end].strip()
            idx = pos + len(q)
            if matches_in_doc >= 5:  # 每篇最多统计 5 次匹配
                break

        if matches_in_doc > 0:
            results.append({
                "score": round(matches_in_doc / 5.0, 3),  # 归一化分数
                "text": snippet[:300],
                "full_text": snippet,
                "doc_id": str(d.get("doc_id")),
                "chunk_index": 0,
                "filename": d.get("filename", ""),
                "ext": d.get("ext", ""),
                "top_folder": d.get("top_folder", ""),
                "source": d.get("source", "local"),
                "url": d.get("url", ""),
                "title": d.get("title", ""),
                "r2_original": d.get("r2_original", ""),
                "r2_extracted": d.get("r2_extracted", ""),
                "match_count": matches_in_doc,
            })

    # 按匹配次数排序
    results.sort(key=lambda x: -x.get("match_count", 0))
    return results[:limit]


@router.get("/search")
async def search(
    q: str = Query(...),
    limit: int = Query(10),
    source: str = Query(None),
    user: dict = Depends(get_current_user),
):
    """搜索：优先语义搜索，失败回退关键词搜索"""
    # 尝试语义搜索
    try:
        from app.services.embedder import embed_single
        from app.services.vectorstore import query as pinecone_query
        vec = embed_single(q)
        filter_meta = {"source": source} if source else None
        results = pinecone_query(vec.tolist(), top_k=limit, filter_meta=filter_meta)
        out = []
        for match in results.get("matches", []):
            md = match.get("metadata", {})
            out.append({
                "score": round(match.get("score", 0), 3),
                "text": md.get("text", "")[:300],
                "full_text": md.get("text", ""),
                "doc_id": md.get("doc_id"),
                "chunk_index": md.get("chunk_index"),
                "filename": md.get("filename", ""),
                "ext": md.get("ext", ""),
                "top_folder": md.get("top_folder", ""),
                "source": md.get("source", "local"),
                "url": md.get("url", ""),
                "title": md.get("title", ""),
                "r2_original": md.get("r2_original", ""),
                "r2_extracted": md.get("r2_extracted", ""),
            })
        return {"query": q, "results": out, "mode": "semantic"}
    except Exception as e:
        print(f"[search] 语义搜索失败，回退关键词搜索: {e}")

    # 回退：关键词搜索
    out = _keyword_search(q, limit)
    return {"query": q, "results": out, "mode": "keyword"}


@router.get("/chunk/{doc_id}/{chunk_index}")
async def chunk_detail(
    doc_id: str,
    chunk_index: int,
    user: dict = Depends(get_current_user),
):
    """获取文档提取文本的某个片段（从 R2 读取）"""
    docs = _get_docs_index()
    doc = None
    for d in docs:
        if str(d.get("doc_id")) == str(doc_id):
            doc = d
            break
    if not doc:
        return {"error": "not found"}

    r2_key = doc.get("r2_extracted")
    if not r2_key:
        return {"error": "no extracted text"}

    text = _get_extracted_text(r2_key)
    # 按 chunk_index 粗略切分（每块约 500 字符）
    chunk_size = 500
    start = chunk_index * chunk_size
    end = min(start + chunk_size, len(text))
    snippet = text[start:end] if start < len(text) else ""

    return {
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "text": snippet,
        "filename": doc.get("filename", ""),
        "ext": doc.get("ext", ""),
        "source": doc.get("source", "local"),
    }
