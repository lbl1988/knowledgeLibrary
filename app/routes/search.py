# -*- coding: utf-8 -*-
"""搜索路由 —— Pinecone 语义搜索"""
from fastapi import APIRouter, Depends, Query
from app.services.vectorstore import query as pinecone_query
from app.services.embedder import embed_single
from app.auth import get_current_user

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search(
    q: str = Query(...),
    limit: int = Query(10),
    source: str = Query(None),
    user: dict = Depends(get_current_user),
):
    """向量语义搜索"""
    vec = embed_single(q)
    filter_meta = {"source": source} if source else None
    results = pinecone_query(vec.tolist(), top_k=limit, filter_meta=filter_meta)

    out = []
    for match in results.get("matches", []):
        md = match.get("metadata", {})
        # Pinecone 返回 score 是 cosine distance，转成 similarity
        score = match.get("score", 0)
        # Pinecone 用 cosine metric 时 score 就是 cosine similarity
        out.append({
            "score": round(score, 3),
            "text": match.get("metadata", {}).get("text", "")[:300],
            "full_text": match.get("metadata", {}).get("text", ""),
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
    return {"query": q, "results": out}


@router.get("/chunk/{doc_id}/{chunk_index}")
async def chunk_detail(
    doc_id: str,
    chunk_index: int,
    user: dict = Depends(get_current_user),
):
    """获取某个 chunk 的完整内容（Pinecone metadata 里已存 text）"""
    from app.services.vectorstore import query as pq
    from app.services.embedder import embed_single
    # 用匹配 filter 查出这个 chunk
    vec = embed_single("")
    results = pq(vec.tolist(), top_k=1, filter_meta={"doc_id": doc_id, "chunk_index": chunk_index})
    matches = results.get("matches", [])
    if not matches:
        return {"error": "not found"}
    md = matches[0]["metadata"]
    return {
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "text": md.get("text", ""),
        "filename": md.get("filename", ""),
        "ext": md.get("ext", ""),
        "source": md.get("source", "local"),
    }
