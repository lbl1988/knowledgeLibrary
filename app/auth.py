# -*- coding: utf-8 -*-
"""Supabase Auth 鉴权 —— FastAPI 依赖注入"""
from typing import Optional
from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from app.config import SUPABASE_ENABLE_AUTH, SUPABASE_JWT_SECRET, SUPABASE_URL, SUPABASE_ANON_KEY


def verify_token(token: str) -> Optional[dict]:
    """验证 Supabase JWT，返回 payload 或 None"""
    if not SUPABASE_JWT_SECRET:
        return None
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except JWTError:
        return None


async def get_current_user(request: Request) -> Optional[dict]:
    """FastAPI 依赖：从 Authorization header 提取并验证 token"""
    if not SUPABASE_ENABLE_AUTH:
        return {"id": "anonymous", "email": "anonymous@local", "aud": "authenticated"}

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未认证")

    token = auth[7:]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或过期")

    return payload


def require_auth():
    """需要认证的路由用这个依赖"""
    if not SUPABASE_ENABLE_AUTH:
        async def _skip():
            return {"id": "anonymous", "email": "anonymous@local"}
        return _skip

    async def _auth(request: Request = None, token: str = Depends(get_current_user)):
        if not token:
            raise HTTPException(status_code=401, detail="需要登录")
        return token

    return _auth
