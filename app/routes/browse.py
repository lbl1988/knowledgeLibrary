# -*- coding: utf-8 -*-
"""浏览路由 —— Pinecone metadata 里存了所有文档元信息"""
from fastapi import APIRouter, Depends, Query
from app.services.vectorstore import query, describe_index
from app.auth import get_current_user
from app.services.embedder import embed_single
from app.services.chunker import chunk_text

router = APIRouter(prefix="/api/browse", tags=["browse"])


def _list_all_docs() -> list[dict]:
    """从 Pinecone 拉所有向量的 metadata，按 doc_id 去重取文档"""
    from app.services.vectorstore import get_index

    try:
        idx = get_index()
    except Exception as e:
        print(f"获取 Pinecone index 失败: {e}")
        return []

    try:
        docs = {}
        stats = describe_index()
        total = stats.get("total_vector_count", 0)
        if total == 0:
            return []

        # 用 list() 拉所有向量 ID（serverless index 支持），再分批 fetch metadata
        all_ids = []
        try:
            for ids in idx.list(prefix=""):
                all_ids.extend(ids)
        except Exception as le:
            print(f"list() 不可用，回退到 query: {le}")
            # 回退：用随机向量 + 大 top_k 查
            import random
            vec = [random.uniform(-1, 1) for _ in range(1024)]
            results = idx.query(vector=vec, top_k=min(total, 10000), include_metadata=True)
            for match in results.get("matches", []):
                md = match.get("metadata", {})
                doc_id = md.get("doc_id")
                if doc_id and doc_id not in docs:
                    docs[doc_id] = {
                        "doc_id": doc_id,
                        "filename": md.get("filename", ""),
                        "ext": md.get("ext", ""),
                        "top_folder": md.get("top_folder", ""),
                        "size_mb": md.get("size_mb", 0),
                        "source": md.get("source", "local"),
                        "r2_original": md.get("r2_original", ""),
                        "r2_extracted": md.get("r2_extracted", ""),
                    }
            return list(docs.values())

        # 分批 fetch metadata（每批最多 1000）
        for i in range(0, len(all_ids), 1000):
            batch_ids = all_ids[i:i + 1000]
            fetched = idx.fetch(ids=batch_ids)
            for vid, vdata in fetched.get("vectors", {}).items():
                md = vdata.get("metadata", {})
                doc_id = md.get("doc_id")
                if doc_id and doc_id not in docs:
                    docs[doc_id] = {
                        "doc_id": doc_id,
                        "filename": md.get("filename", ""),
                        "ext": md.get("ext", ""),
                        "top_folder": md.get("top_folder", ""),
                        "size_mb": md.get("size_mb", 0),
                        "source": md.get("source", "local"),
                        "r2_original": md.get("r2_original", ""),
                        "r2_extracted": md.get("r2_extracted", ""),
                    }
        return list(docs.values())
    except Exception as e:
        print(f"list_all_docs 出错: {e}")
        return []


@router.get("/overview")
async def overview(user: dict = Depends(get_current_user)):
    """总览"""
    stats = describe_index()
    docs = _list_all_docs()
    # 按 top_folder 分组
    by_folder = {}
    by_ext = {}
    total_size = 0.0
    scanned = 0
    for d in docs:
        by_folder[d["top_folder"]] = by_folder.get(d["top_folder"], 0) + 1
        by_ext[d["ext"]] = by_ext.get(d["ext"], 0) + 1
        total_size += float(d["size_mb"] or 0)
        if d.get("top_folder") == "OCR":  # 粗略判断
            scanned += 1

    return {
        "total": len(docs),
        "chunks": stats.get("total_vector_count", 0),
        "size_mb": round(total_size, 1),
        "by_folder": by_folder,
        "by_ext": by_ext,
    }


@router.get("/files")
async def list_files(
    folder: str = Query(None),
    ext: str = Query(None),
    source: str = Query(None),
    user: dict = Depends(get_current_user),
):
    """文件列表，可按目录/类型/来源筛选"""
    all_docs = _list_all_docs()
    if folder:
        all_docs = [d for d in all_docs if d["top_folder"] == folder]
    if ext:
        all_docs = [d for d in all_docs if d["ext"] == ext]
    if source:
        all_docs = [d for d in all_docs if d.get("source") == source]
    all_docs.sort(key=lambda d: d["filename"])
    return {"files": all_docs}


@router.get("/dirs")
async def browse_dirs(user: dict = Depends(get_current_user)):
    """按目录汇总"""
    docs = _list_all_docs()
    by_folder = {}
    for d in docs:
        key = d["top_folder"] or "(根)"
        if key not in by_folder:
            by_folder[key] = {"top_folder": key, "cnt": 0, "sz": 0.0}
        by_folder[key]["cnt"] += 1
        by_folder[key]["sz"] += float(d["size_mb"] or 0)
    return {"dirs": sorted(by_folder.values(), key=lambda x: -x["cnt"])}


@router.get("/types")
async def browse_types(user: dict = Depends(get_current_user)):
    """按类型汇总"""
    docs = _list_all_docs()
    by_ext = {}
    for d in docs:
        ext = d["ext"] or "unknown"
        if ext not in by_ext:
            by_ext[ext] = {"ext": ext, "cnt": 0, "sz": 0.0}
        by_ext[ext]["cnt"] += 1
        by_ext[ext]["sz"] += float(d["size_mb"] or 0)
    return {"types": sorted(by_ext.values(), key=lambda x: -x["cnt"])}
