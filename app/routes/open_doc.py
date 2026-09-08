# -*- coding: utf-8 -*-
"""打开/预览/下载原文件路由 —— 全部走 R2 预签名 URL，不跳转本地路径。

设计原则（对应用户要求）：
  1. 原文件只读不动 —— 服务器不接触本地 E:\ 盘，只从 R2 取。
  2. 不跳转到本地打开 —— 不返回 file:// 也不调 os.startfile。
  3. 在线浏览 / 下载到本地 二选一 —— 通过 ResponseContentDisposition 控制。
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from app.services.storage import get_presigned_url
from app.services.vectorstore import query as pinecone_query
from app.services.embedder import embed_single
from app.config import R2_BUCKET_ORIGINALS, R2_BUCKET_EXTRACTED
from app.auth import get_current_user

router = APIRouter(prefix="/api/open", tags=["open"])

# 文件扩展名 → 浏览器 Content-Type
CONTENT_TYPES = {
    ".pdf":  "application/pdf",
    ".txt":  "text/plain; charset=utf-8",
    ".md":   "text/plain; charset=utf-8",
    ".csv":  "text/csv; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".htm":  "text/html; charset=utf-8",
    ".xml":  "application/xml; charset=utf-8",
    ".log":  "text/plain; charset=utf-8",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".webp": "image/webp",
    ".bmp":  "image/bmp",
    ".svg":  "image/svg+xml",
    ".mp4":  "video/mp4",
    ".mp3":  "audio/mpeg",
    ".wav":  "audio/wav",
    # Office 文件浏览器原生不支持预览，但仍然给正确 Content-Type
    ".doc":  "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls":  "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt":  "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

# 浏览器原生支持在线预览的扩展名（点开就能在标签页里看）
PREVIEWABLE = {
    ".pdf", ".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml", ".log",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg",
    ".mp4", ".mp3", ".wav",
}


def _get_ext(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def _find_doc_metadata(doc_id: str) -> dict:
    """从 Pinecone 查出 doc_id 对应的任意一条 metadata"""
    vec = embed_single("")
    results = pinecone_query(vec.tolist(), top_k=1, filter_meta={"doc_id": doc_id})
    matches = results.get("matches", [])
    if not matches:
        raise HTTPException(status_code=404, detail="文档不存在")
    return matches[0]["metadata"]


def _resolve_original(md: dict) -> tuple:
    """从 metadata 拿 r2_key + filename + ext，统一校验"""
    r2_key = md.get("r2_original")
    if not r2_key:
        raise HTTPException(status_code=404, detail="该文档无原始文件（可能只入了一部分）")
    filename = md.get("filename", "") or r2_key
    ext = _get_ext(filename)
    return r2_key, filename, ext


# ============ 在线浏览 ============
@router.get("/preview/{doc_id}")
async def preview_original(doc_id: str, user: dict = Depends(get_current_user)):
    """生成在线浏览 URL（inline disposition，浏览器内嵌显示）"""
    md = _find_doc_metadata(doc_id)
    r2_key, filename, ext = _resolve_original(md)
    content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
    url = get_presigned_url(
        R2_BUCKET_ORIGINALS, r2_key, expires=3600,
        disposition="inline", filename=filename,
        content_type=content_type,
    )
    return {
        "url": url,
        "filename": filename,
        "ext": ext,
        "previewable": ext in PREVIEWABLE,
        "content_type": content_type,
    }


# ============ 下载到本地 ============
@router.get("/download/{doc_id}")
async def download_original(doc_id: str, user: dict = Depends(get_current_user)):
    """生成下载链接（attachment disposition，强制浏览器下载）"""
    md = _find_doc_metadata(doc_id)
    r2_key, filename, ext = _resolve_original(md)
    content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
    url = get_presigned_url(
        R2_BUCKET_ORIGINALS, r2_key, expires=3600,
        disposition="attachment", filename=filename,
        content_type=content_type,
    )
    return {"url": url, "filename": filename, "ext": ext}


# ============ 提取文本 ============
@router.get("/extracted/{doc_id}")
async def open_extracted(doc_id: str, user: dict = Depends(get_current_user)):
    """生成提取文本下载/预览链接（txt 永远可预览）"""
    md = _find_doc_metadata(doc_id)
    r2_key = md.get("r2_extracted")
    if not r2_key:
        raise HTTPException(status_code=404, detail="该文档无提取文本")
    filename = md.get("filename", "") or r2_key
    base = os.path.splitext(filename)[0]
    txt_name = f"{base}.txt"
    url = get_presigned_url(
        R2_BUCKET_EXTRACTED, r2_key, expires=3600,
        disposition="inline", filename=txt_name,
        content_type="text/plain; charset=utf-8",
    )
    return {"url": url, "filename": txt_name, "previewable": True}


# ============ 全网抓取的网页 ============
@router.get("/url/{doc_id}")
async def open_web_url(doc_id: str, user: dict = Depends(get_current_user)):
    """全网抓取的文档，返回原始网页 URL"""
    md = _find_doc_metadata(doc_id)
    url = md.get("url")
    if not url:
        raise HTTPException(status_code=404, detail="该文档无网页 URL")
    return {"url": url, "title": md.get("title", "")}


# ============ 元数据查询（前端判断按钮显示用）============
@router.get("/info/{doc_id}")
async def doc_info(doc_id: str, user: dict = Depends(get_current_user)):
    """返回文档的预览能力信息，前端据此决定显示哪些按钮"""
    md = _find_doc_metadata(doc_id)
    filename = md.get("filename", "")
    ext = _get_ext(filename)
    return {
        "doc_id": doc_id,
        "filename": filename,
        "ext": ext,
        "source": md.get("source", "local"),
        "has_original": bool(md.get("r2_original")),
        "has_extracted": bool(md.get("r2_extracted")),
        "web_url": md.get("url", ""),
        "previewable": ext in PREVIEWABLE,
    }
