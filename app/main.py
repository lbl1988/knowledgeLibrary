# -*- coding: utf-8 -*-
"""FastAPI 入口 —— 薄 main，只管生命周期 + 路由注册 + 首页"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.services import storage, vectorstore
from app.config import (
    SUPABASE_ENABLE_AUTH, SUPABASE_URL, SUPABASE_ANON_KEY,
    R2_BUCKET_ORIGINALS, R2_BUCKET_EXTRACTED,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时确保 R2 bucket 存在"""
    try:
        storage.ensure_buckets()
    except Exception as e:
        print(f"R2 初始化跳过（key 未配置?）: {e}")
    yield


app = FastAPI(title="知识库", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态资源
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# 注册路由
from app.routes.browse import router as browse_router
from app.routes.search import router as search_router
from app.routes.open_doc import router as open_router
from app.routes.crawl import router as crawl_router

app.include_router(browse_router)
app.include_router(search_router)
app.include_router(open_router)
app.include_router(crawl_router)


# ---- 首页 ----
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """知识库主页面"""
    enable_auth = SUPABASE_ENABLE_AUTH
    supabase_url = SUPABASE_URL
    supabase_key = SUPABASE_ANON_KEY
    return templates.TemplateResponse(request, "index.html", {
        "enable_auth": enable_auth,
        "supabase_url": supabase_url,
        "supabase_key": supabase_key,
    })


@app.get("/health")
async def health():
    """健康检查"""
    return {
        "ok": True,
        "auth": SUPABASE_ENABLE_AUTH,
        "r2": storage.health(),
        "pinecone": vectorstore.describe_index(),
    }
