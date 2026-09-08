# -*- coding: utf-8 -*-
"""全网抓取路由 —— 搜关键词 → Jina AI Search → 入库"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.services.crawler import crawl_keyword
from app.services.chunker import chunk_text
from app.services.embedder import embed
from app.services.vectorstore import upsert as pinecone_upsert
from app.config import CHUNK_SIZE, CHUNK_OVERLAP
from app.auth import get_current_user

router = APIRouter(prefix="/api", tags=["crawl"])


class CrawlRequest(BaseModel):
    keyword: str
    max_results: int = 5


@router.post("/crawl")
async def crawl(req: CrawlRequest, user: dict = Depends(get_current_user)):
    """全网抓取并入库"""
    try:
        articles = crawl_keyword(req.keyword, max_results=req.max_results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抓取失败: {e}")

    if not articles:
        return {"ok": True, "docs": 0, "chunks": 0, "message": "未抓到有效内容"}

    chunks_total = 0
    docs_added = 0

    for art in articles:
        text = art.get("text", "")
        if not text:
            continue

        chunks = chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        if not chunks:
            continue

        # 嵌入
        vecs = embed(chunks)

        # 构造 Pinecone 记录
        batch_ids = []
        batch_vecs = []
        batch_docs = []
        batch_meta = []

        doc_id = f"web_{hash(art['url']) & 0xFFFFFFFF}"

        for ci, (chunk, vec) in enumerate(zip(chunks, vecs)):
            batch_ids.append(f"{doc_id}_chunk{ci}")
            batch_vecs.append(vec.tolist())
            batch_docs.append(chunk)
            batch_meta.append({
                "doc_id": doc_id,
                "chunk_index": ci,
                "filename": art.get("title", "unknown"),
                "ext": ".html",
                "top_folder": "全网搜索",
                "source": "web",
                "url": art.get("url", ""),
                "title": art.get("title", ""),
                "r2_original": "",
                "r2_extracted": "",
                "size_mb": round(len(text) / 1024 / 1024, 3),
                "text": chunk,  # Pinecone metadata 存完整 chunk 文本
            })

        pinecone_upsert(batch_ids, batch_vecs, batch_docs, batch_meta)
        chunks_total += len(chunks)
        docs_added += 1

    return {
        "ok": True,
        "docs": docs_added,
        "chunks": chunks_total,
        "keyword": req.keyword,
    }
