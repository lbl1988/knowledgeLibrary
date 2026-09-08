# -*- coding: utf-8 -*-
"""迁移脚本：本地 SQLite + 本地文件 → Pinecone + Cloudflare R2

使用：
    cd kb_cloud\data
    python migrate.py

前提：
    1. .env 里配好 PINECONE_API_KEY / R2_* / JINA_API_KEY
    2. 本地 kb_src\data\kb.db 存在（含 documents / chunks 表）
    3. 本地 kb_src\extracted\ 有纯文本
    4. 本地 E:\Learn\ 有原文件（只读，不动）
"""
import os
import sys
import sqlite3
import json
import hashlib
import time
from pathlib import Path

# 确保能 import app.*
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.config import LOCAL_KB_DIR, CHUNK_SIZE, CHUNK_OVERLAP  # noqa
from app.services import storage, embedder, vectorstore, chunker  # noqa


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def main():
    print("=" * 60)
    print("本地知识库 → 云服务迁移")
    print("=" * 60)

    # ---- 1. 读本地 SQLite ----
    db_path = os.path.join(LOCAL_KB_DIR, "data", "kb.db")
    if not os.path.exists(db_path):
        print(f"[错误] 找不到本地数据库: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM documents")
    total_docs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chunks")
    total_chunks = c.fetchone()[0]
    print(f"本地数据库: {total_docs} 文档, {total_chunks} 文本块")

    c.execute("SELECT * FROM documents")
    docs = [dict(r) for r in c.fetchall()]

    # ---- 2. 确保 R2 bucket 存在 ----
    print("\n[1/4] 初始化 R2 bucket ...")
    try:
        storage.ensure_buckets()
        print("  ✓ R2 bucket 就绪")
    except Exception as e:
        print(f"  ✗ R2 初始化失败: {e}")
        return

    # ---- 3. 迁移原文件 + 提取文本 ----
    print(f"\n[2/4] 上传文件到 R2 ...")
    r2_keys = {}  # sha256 → {"original": key, "extracted": key}
    ok = 0
    skip = 0
    for i, doc in enumerate(docs):
        sha = doc["sha256"]
        if sha in r2_keys:
            skip += 1
            continue
        r2_orig_key = f"{sha}{doc['ext']}"
        r2_ext_key = f"{sha}.txt"

        # 原文件
        orig_path = doc["source_path"]
        if os.path.exists(orig_path):
            try:
                storage.upload_file(orig_path, storage.R2_BUCKET_ORIGINALS, r2_orig_key)
            except Exception as e:
                print(f"  ⚠ 原文件上传失败 {orig_path}: {e}")

        # 提取文本
        ext_path = doc.get("extracted_path", "")
        if ext_path and os.path.exists(ext_path):
            try:
                with open(ext_path, "rb") as f:
                    storage.upload_bytes(f.read(), storage.R2_BUCKET_EXTRACTED, r2_ext_key)
            except Exception as e:
                print(f"  ⚠ 提取文本上传失败 {ext_path}: {e}")

        r2_keys[sha] = {"original": r2_orig_key, "extracted": r2_ext_key}
        ok += 1
        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{total_docs} 文档")

    print(f"  ✓ 上传完成: {ok} 新, {skip} 重复")

    # ---- 4. 用 Jina 重新嵌入 + 写 Pinecone ----
    print(f"\n[3/4] 嵌入 + 写入 Pinecone ...")
    print(f"  注意：Jina 免费 100 万 token/月，{total_chunks} 块约需 46 万 token")

    c.execute("SELECT c.*, d.sha256, d.filename, d.ext, d.top_folder, d.source_root, d.size_mb, d.source_path "
              "FROM chunks c JOIN documents d ON c.doc_id = d.id ORDER BY c.doc_id, c.chunk_index")
    all_chunks = [dict(r) for r in c.fetchall()]
    conn.close()

    # 按 doc_id 分组批量嵌入
    current_doc_id = None
    batch_chunks = []
    batch_vecs = []
    batch_ids = []
    batch_docs = []
    batch_meta = []
    upsert_count = 0

    def flush_batch():
        nonlocal batch_vecs, batch_ids, batch_docs, batch_meta, upsert_count
        if not batch_vecs:
            return
        pinecone.upsert(batch_ids, [v.tolist() for v in batch_vecs], batch_docs, batch_meta, batch_size=100)
        upsert_count += len(batch_ids)
        batch_vecs = []
        batch_ids = []
        batch_docs = []
        batch_meta = []

    doc_ids_seen = set()
    for i, row in enumerate(all_chunks):
        if row["doc_id"] != current_doc_id:
            flush_batch()
            current_doc_id = row["doc_id"]

        doc_id = str(row["doc_id"])
        chunk_idx = row["chunk_index"]
        chunk_text = row["text"]
        sha = row["sha256"]
        r2 = r2_keys.get(sha, {"original": "", "extracted": ""})

        if doc_id not in doc_ids_seen:
            doc_ids_seen.add(doc_id)

        batch_ids.append(f"{doc_id}_chunk{chunk_idx}")
        batch_docs.append(chunk_text)
        batch_meta.append({
            "doc_id": doc_id,
            "chunk_index": chunk_idx,
            "filename": row["filename"],
            "ext": row["ext"],
            "top_folder": row["top_folder"] or "(根)",
            "source": "local",
            "size_mb": float(row["size_mb"] or 0),
            "r2_original": r2["original"],
            "r2_extracted": r2["extracted"],
            "source_path": row["source_path"],
            "url": "",
            "title": row["filename"],
            "sha256": sha,
            "text": chunk_text,  # Pinecone metadata 存完整文本，搜索时直接返回
        })

        if len(batch_ids) >= 100:
            # 批量嵌入
            vecs = embedder.embed(batch_docs)
            batch_vecs = list(vecs)
            flush_batch()

        if (i + 1) % 5000 == 0:
            print(f"  进度: {i+1}/{total_chunks} 块, upserted {upsert_count}")
            time.sleep(1)  # 避免打爆 API 限流

    # 最后一批
    if batch_docs:
        vecs = embedder.embed(batch_docs)
        batch_vecs = list(vecs)
        flush_batch()

    print(f"  ✓ Pinecone 写入完成: {upsert_count} 向量")

    # ---- 5. 报告 ----
    print(f"\n[4/4] 迁移报告")
    stats = vectorstore.describe_index()
    print(f"  Pinecone 向量数: {stats.get('total_vector_count', 0)}")
    print(f"  R2 originals bucket: {len(r2_keys)} 个文件")
    print(f"  R2 extracted bucket: {len(r2_keys)} 个文件")
    print(f"\n{'='*60}")
    print("迁移完成！现在可以部署 Render 并访问了。")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
