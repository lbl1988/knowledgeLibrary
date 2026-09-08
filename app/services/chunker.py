# -*- coding: utf-8 -*-
"""文本切分 —— 与本地版保持一致的算法"""


def chunk_text(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    """按字符数切分，带重叠"""
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap
    return chunks
