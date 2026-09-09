# -*- coding: utf-8 -*-
"""云配置 —— 全部从环境变量读取，render.yaml 里同步"""
import os
from dotenv import load_dotenv

load_dotenv()  # 本地开发时读 .env

# ---- Pinecone 向量库 ----
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_ENV = os.getenv("PINECONE_ENV", "gcp-starter")  # 例如 us-east-1-aws
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "kb-docs")

# ---- Cloudflare R2 存储 ----
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")    # https://xxx.r2.cloudflarestorage.com
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY", "")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY", "")
R2_BUCKET_ORIGINALS = os.getenv("R2_BUCKET_ORIGINALS", "kb-originals")
R2_BUCKET_EXTRACTED = os.getenv("R2_BUCKET_EXTRACTED", "kb-extracted")

# ---- Jina AI 嵌入 ----
JINA_API_KEY = os.getenv("JINA_API_KEY", "")
JINA_EMBED_MODEL = os.getenv("JINA_EMBED_MODEL", "jina-embeddings-v3")
JINA_EMBED_DIM = int(os.getenv("JINA_EMBED_DIM", "1024"))

# ---- Supabase Auth ----
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")  # 从 Supabase JWT 配置里复制
SUPABASE_ENABLE_AUTH = os.getenv("SUPABASE_ENABLE_AUTH", "false").lower() == "true"

# ---- 全网搜索 ----
# Serper.dev (Google 搜索, 2500次/月免费) —— 注册 https://serper.dev
# 不配置则降级使用 DuckDuckGo (无需 key, 可能受限)
# 正文统一用 Jina Reader r.jina.ai (免费, 无需 key)
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")

# ---- 本地迁移 ----
LOCAL_KB_DIR = os.getenv("LOCAL_KB_DIR",
    r"C:\Users\v1522\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a9f629c773bdfd80a28d0b4\kb_src")

# ---- 切分参数 ----
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "80"))
