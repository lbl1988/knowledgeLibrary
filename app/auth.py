# -*- coding: utf-8 -*-
"""Supabase Auth 鉴权 —— FastAPI 依赖注入
自动从 Supabase JWKS 端点获取公钥，支持 ECC (P-256/ES256) 和 HS256 两种签名方式
"""
import json
import time
import urllib.request
import logging
from typing import Optional
from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from jose.utils import base64url_decode
from app.config import SUPABASE_ENABLE_AUTH, SUPABASE_URL

logger = logging.getLogger(__name__)

# ---- JWKS 缓存 ----
_jwks_cache = {"keys": None, "expires_at": 0}
JWKS_URL_SUFFIX = "/auth/v1/.well-known/jwks.json"
JWKS_CACHE_TTL = 3600  # 缓存 1 小时


def _get_jwks() -> Optional[list]:
    """从 Supabase JWKS 端点获取所有公钥（带缓存）"""
    now = time.time()
    if _jwks_cache["keys"] and now < _jwks_cache["expires_at"]:
        return _jwks_cache["keys"]
    try:
        url = SUPABASE_URL.rstrip("/") + JWKS_URL_SUFFIX
        logger.info(f"[auth] 正在获取 JWKS: {url}")
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        keys = data.get("keys", [])
        logger.info(f"[auth] JWKS 获取成功, keys 数量: {len(keys)}, kty: {[k.get('kty') for k in keys]}")
        _jwks_cache["keys"] = keys
        _jwks_cache["expires_at"] = now + JWKS_CACHE_TTL
        return keys
    except Exception as e:
        logger.error(f"[auth] JWKS 获取失败: {type(e).__name__}: {e}")
        return None


def _decode_with_jwks(token: str, keys: list) -> Optional[dict]:
    """用 JWKS 公钥验证 token，支持 ECC(ES256) 和 HS256"""
    if not keys:
        logger.warning("[auth] keys 为空, 无法验证")
        return None
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg")
        logger.info(f"[auth] token header: alg={alg}, kid={kid}")
        # 优先匹配 kid，没匹配就试所有 key
        matching = [k for k in keys if k.get("kid") == kid]
        if not matching:
            matching = keys
        for key_data in matching:
            try:
                kty = key_data.get("kty")
                logger.info(f"[auth] 尝试 key kty={kty}, kid={key_data.get('kid')}")
                if kty == "EC":
                    # ECC P-256 → ES256
                    from cryptography.hazmat.primitives.asymmetric.ec import (
                        EllipticCurvePublicNumbers, SECP256R1,
                    )
                    from cryptography.hazmat.primitives import serialization
                    from cryptography.hazmat.backends import default_backend
                    x = int.from_bytes(base64url_decode(key_data["x"]), "big")
                    y = int.from_bytes(base64url_decode(key_data["y"]), "big")
                    nums = EllipticCurvePublicNumbers(x, y, SECP256R1())
                    pub_key = nums.public_key(default_backend())
                    pem = pub_key.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                    payload = jwt.decode(
                        token, pem, algorithms=["ES256"], audience="authenticated",
                    )
                    logger.info(f"[auth] ES256 验证成功! sub={payload.get('sub')}")
                    return payload
                elif kty == "oct":
                    # HS256 共享密钥（JWKS 里的 legacy secret）
                    secret = base64url_decode(key_data["k"])
                    payload = jwt.decode(
                        token, secret, algorithms=["HS256"], audience="authenticated",
                    )
                    logger.info(f"[auth] HS256 验证成功! sub={payload.get('sub')}")
                    return payload
            except JWTError as e:
                logger.warning(f"[auth] key验证失败 JWTError: {e}")
                continue
    except Exception as e:
        logger.error(f"[auth] _decode_with_jwks 异常: {type(e).__name__}: {e}")
    return None


def verify_token(token: str) -> Optional[dict]:
    """验证 Supabase JWT，返回 payload 或 None
    自动尝试 JWKS 公钥验证（兼容 ECC 和 HS256）
    """
    if not token or len(token) < 20:
        logger.warning("[auth] token 为空或太短")
        return None
    keys = _get_jwks()
    if not keys:
        logger.error("[auth] 无法获取 JWKS keys, 验证失败")
        return None
    payload = _decode_with_jwks(token, keys)
    if not payload:
        logger.error("[auth] 所有 key 验证均失败")
    return payload


async def get_current_user(request: Request) -> Optional[dict]:
    """FastAPI 依赖：从 Authorization header 提取并验证 token"""
    if not SUPABASE_ENABLE_AUTH:
        return {"id": "anonymous", "email": "anonymous@local", "aud": "authenticated"}

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        logger.warning("[auth] 缺少 Bearer token")
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
