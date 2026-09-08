# -*- coding: utf-8 -*-
"""全网抓取 —— Jina AI Search API (s.jina.ai) 替代 Bing Search API
使用已有的 JINA_API_KEY，无需额外注册 Azure 或 Bing API。
s.jina.ai 直接返回搜索结果的正文内容，无需单独抓取网页。
"""
import requests
from urllib.parse import quote
from app.config import JINA_API_KEY


def search_jina(query: str, count: int = 5) -> list[dict]:
    """Jina AI Search API (s.jina.ai)，返回搜索结果含正文

    接口文档: https://jina.ai/reader/
    - GET https://s.jina.ai/{query}
    - Header: Authorization: Bearer {JINA_API_KEY}
    - Header: Accept: application/json
    - 返回 JSON: {data: [{url, title, content, description}]}
    """
    if not JINA_API_KEY:
        raise RuntimeError("JINA_API_KEY 未配置，无法使用全网搜索")

    encoded_query = quote(query)
    resp = requests.get(
        f"https://s.jina.ai/{encoded_query}",
        headers={
            "Authorization": f"Bearer {JINA_API_KEY}",
            "Accept": "application/json",
            "X-Retain-Images": "none",
        },
        params={"num": count},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Jina 搜索失败: {resp.status_code} {resp.text[:200]}")

    data = resp.json()
    results_raw = data.get("data", [])

    return [
        {
            "url": item.get("url", ""),
            "title": item.get("title", "").strip(),
            "text": item.get("content", "").strip(),
            "snippet": (item.get("description") or item.get("content", "")[:200]).strip(),
            "display_url": item.get("url", ""),
        }
        for item in results_raw
    ]


def crawl_keyword(query: str, max_results: int = 5) -> list[dict]:
    """完整流程：Jina 搜索 → 返回结构化内容

    s.jina.ai 已在搜索时提取正文，无需二次抓取网页。
    """
    results = search_jina(query, count=max_results)

    # 过滤掉正文过短的结果
    filtered = []
    for item in results:
        text = item.get("text", "")
        if text and len(text) > 100:
            filtered.append(item)

    return filtered
