# -*- coding: utf-8 -*-
"""Cloudflare R2 存储封装 —— S3 兼容协议"""
from typing import Optional
from urllib.parse import quote
import os
import boto3
from app.config import R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET_ORIGINALS, R2_BUCKET_EXTRACTED


_s3: Optional[boto3.client] = None


def _get_s3() -> boto3.client:
    global _s3
    if _s3 is not None:
        return _s3
    if not R2_ACCESS_KEY or not R2_SECRET_KEY or not R2_ENDPOINT:
        raise RuntimeError("R2 未配置")
    _s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
    )
    return _s3


def ensure_buckets():
    """确保两个 bucket 存在"""
    s3 = _get_s3()
    for bucket in [R2_BUCKET_ORIGINALS, R2_BUCKET_EXTRACTED]:
        try:
            s3.head_bucket(Bucket=bucket)
        except Exception:
            try:
                s3.create_bucket(Bucket=bucket)
            except Exception as e:
                print(f"创建 bucket {bucket} 失败: {e}")


def upload_file(local_path: str, bucket: str, r2_key: str) -> str:
    """上传本地文件到 R2，返回 R2 key"""
    s3 = _get_s3()
    s3.upload_file(local_path, bucket, r2_key)
    return r2_key


def upload_bytes(data: bytes, bucket: str, r2_key: str) -> str:
    """上传 bytes 到 R2"""
    s3 = _get_s3()
    s3.put_object(Bucket=bucket, Key=r2_key, Body=data)
    return r2_key


def get_presigned_url(bucket: str, r2_key: str, expires: int = 3600,
                      disposition: Optional[str] = None,
                      filename: Optional[str] = None,
                      content_type: Optional[str] = None) -> str:
    """生成预签名 URL（有效期 expires 秒）。

    参数:
        disposition: "inline" 浏览器内联预览 / "attachment" 强制下载。None 表示用 R2 对象默认行为。
        filename:    下载时建议的文件名（支持中文，自动按 RFC 5987 编码）。
        content_type: 覆盖响应 Content-Type（让浏览器知道怎么渲染）。
    """
    s3 = _get_s3()
    params = {"Bucket": bucket, "Key": r2_key}
    if disposition:
        # 同时给 ASCII fallback 和 UTF-8 版本，兼容旧浏览器
        ascii_name = (filename or r2_key).encode("ascii", "ignore").decode("ascii") or "file"
        cd = f'{disposition}; filename="{ascii_name}"'
        if filename:
            cd += f"; filename*=UTF-8''{quote(filename)}"
        params["ResponseContentDisposition"] = cd
    if content_type:
        params["ResponseContentType"] = content_type
    return s3.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires,
    )


def download_to_file(bucket: str, r2_key: str, local_path: str) -> str:
    """下载 R2 对象到本地文件"""
    s3 = _get_s3()
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    s3.download_file(bucket, r2_key, local_path)
    return local_path


def download_bytes(bucket: str, r2_key: str) -> bytes:
    """下载 R2 对象为 bytes"""
    s3 = _get_s3()
    resp = s3.get_object(Bucket=bucket, Key=r2_key)
    return resp["Body"].read()


def list_objects(bucket: str, prefix: str = "") -> list[dict]:
    """列出 bucket 内对象"""
    s3 = _get_s3()
    results = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            results.append({
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            })
    return results


def delete_object(bucket: str, r2_key: str):
    s3 = _get_s3()
    s3.delete_object(Bucket=bucket, Key=r2_key)


def health() -> dict:
    try:
        ensure_buckets()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
