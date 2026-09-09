# -*- coding: utf-8 -*-
"""全网抓取 —— 免费组合：Serper.dev (Google 搜索) + Jina Reader (免费正文提取)

搜索源优先级：
1. Serper.dev（推荐，Google 结果，2500次/月免费，需 SERPER_API_KEY）
2. DuckDuckGo（降级，无需 key，但可能受限）
正文提取：Jina Reader r.jina.ai（免费，无需 key）

不再使用 Jina Search API (s.jina.ai) —— 它是付费的，和 Embedding 分开计费
"""
import requests
import urllib.request
from urllib.parse import quote
from app.config import SERPER_API_KEY


def search_serper(query: str, count: int = 5) -> list[dict]:
    """Serper.dev Google 搜索（需 API Key）

    注册: https://serper.dev （GitHub/Google OAuth 一键登录，2500次/月免费）
    """
    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "num": count, "gl": "cn", "hl": "zh-cn"},
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Serper 搜索失败: {resp.status_code} {resp.text[:200]}")

    data = resp.json()
    results = []
    for item in data.get("organic", []):
        results.append({
            "url": item.get("link", ""),
            "title": item.get("title", "").strip(),
            "snippet": item.get("snippet", "").strip(),
        })
    return results


def search_duckduckgo(query: str, count: int = 5) -> list[dict]:
    """DuckDuckGo 搜索（免费，无需 key，但可能在 Render 上受限）"""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        raise RuntimeError("未安装 duckduckgo-search，且 SERPER_API_KEY 未配置")

    with DDGS() as ddgs:
        raw = list(ddgs.text(query, max_results=count, region="wt-wt"))

    results = []
    for item in raw:
        results.append({
            "url": item.get("href", ""),
            "title": item.get("title", "").strip(),
            "snippet": item.get("body", "").strip(),
        })
    return results


def extract_with_jina_reader(url: str) -> str:
    """用 Jina Reader 免费提取网页正文（r.jina.ai，无需 key）"""
    reader_url = f"https://r.jina.ai/{url}"
    req = urllib.request.Request(reader_url, headers={
        "Accept": "text/plain",
        "X-Retain-Images": "none",
        "X-Remove-Selector": "script,style,nav,footer,header",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="ignore").strip()
    except Exception as e:
        print(f"[crawler] Jina Reader 提取失败 {url}: {e}")
        return ""


def crawl_keyword(query: str, max_results: int = 5) -> list[dict]:
    """完整流程：搜索 → 提取正文 → 返回结构化内容"""
    # 1. 搜索（优先 Serper，降级 DuckDuckGo）
    if SERPER_API_KEY:
        print(f"[crawler] 使用 Serper 搜索: {query}")
        search_results = search_serper(query, count=max_results)
    else:
        print(f"[crawler] SERPER_API_KEY 未配置，使用 DuckDuckGo")
        search_results = search_duckduckgo(query, count=max_results)

    if not search_results:
        print(f"[crawler] 搜索无结果")
        return []

    # 2. 用 Jina Reader 逐个提取正文
    articles = []
    for item in search_results:
        url = item["url"]
        if not url or not url.startswith(("http://", "https://")):
            continue

        text = extract_with_jina_reader(url)
        if text and len(text) > 100:
            articles.append({
                "url": url,
                "title": item.get("title", "") or url,
                "text": text,
                "snippet": item.get("snippet", "") or text[:200],
                "display_url": url,
            })
            print(f"[crawler] 提取成功: {url[:60]}... ({len(text)}字)")

    print(f"[crawler] 完成: {len(articles)}/{len(search_results)} 条有效结果")
    return articles
