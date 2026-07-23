"""Query expansion, modality routing, and result diversification."""

from __future__ import annotations

import hashlib
import os
import re

TABLE_HINTS = {
    "表格", "表中", "列表", "多少", "数量", "数值", "指标", "排名",
    "占比", "合计", "同比", "环比", "哪一年", "哪一项",
}
IMAGE_HINTS = {
    "图中", "图片", "图表", "示意图", "流程图", "架构图", "曲线",
    "柱状图", "折线图", "趋势", "坐标轴", "图例", "流程",
}
EXPANSIONS = {
    "趋势": ("走势", "变化", "增长", "下降"),
    "增长": ("增幅", "同比", "环比", "趋势"),
    "数量": ("数目", "合计", "总数"),
    "指标": ("数值", "参数", "性能"),
    "流程": ("步骤", "阶段", "过程"),
    "架构": ("结构", "组成", "模块"),
}


def _float_env(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def expand_lexical_query(query: str) -> str:
    """Append conservative Chinese synonyms for BM25 candidate recall."""
    additions: list[str] = []
    for trigger, synonyms in EXPANSIONS.items():
        if trigger in query:
            additions.extend(term for term in synonyms if term not in query)
    return f"{query} {' '.join(dict.fromkeys(additions))}".strip()


def preferred_modalities(query: str) -> set[str]:
    compact = re.sub(r"\s+", "", query.lower())
    preferred: set[str] = set()
    if any(hint in compact for hint in TABLE_HINTS):
        preferred.add("table")
    if any(hint in compact for hint in IMAGE_HINTS):
        preferred.add("image")
    return preferred


def _content_key(hit: dict) -> str:
    normalized = re.sub(r"\s+", "", hit.get("text", "")).lower()[:1000]
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def finalize_hits(query: str, hits: list[dict], *, top_k: int) -> list[dict]:
    """Normalize scores, boost intended modalities, dedupe, and diversify."""
    if not hits:
        return []

    raw_scores = [float(hit.get("score", 0.0)) for hit in hits]
    low, high = min(raw_scores), max(raw_scores)
    spread = high - low
    preferred = preferred_modalities(query)
    modality_bonus = _float_env(
        "HARNESS_RAG_MODALITY_BONUS", 0.2, minimum=0.0, maximum=1.0
    )

    rescored: list[dict] = []
    total = max(len(hits), 1)
    for rank, (hit, raw_score) in enumerate(zip(hits, raw_scores), start=1):
        if low >= 0 and high > 1e-12:
            normalized = raw_score / high
        elif spread > 1e-12:
            normalized = (raw_score - low) / spread
        else:
            normalized = 1.0 - (rank - 1) / total
        modality = hit.get("modality", "text")
        bonus = modality_bonus if modality in preferred else 0.0
        rescored.append(
            {
                **hit,
                "raw_score": round(raw_score, 6),
                "score": round(normalized + bonus, 6),
                "policy": f"modality:{modality}" if bonus else "diversified",
            }
        )
    rescored.sort(key=lambda item: float(item["score"]), reverse=True)

    best = max(float(item["score"]) for item in rescored)
    relative_floor = _float_env(
        "HARNESS_RAG_MIN_RELATIVE_SCORE", 0.1, minimum=0.0, maximum=1.0
    )
    max_per_page = _int_env(
        "HARNESS_RAG_MAX_PER_PAGE", 3, minimum=1, maximum=20
    )
    seen_content: set[str] = set()
    page_counts: dict[tuple[str, int, str], int] = {}
    selected: list[dict] = []
    for hit in rescored:
        if selected and float(hit["score"]) < best * relative_floor:
            continue
        content_key = _content_key(hit)
        if content_key in seen_content:
            continue
        source = hit.get("source", "")
        page = int(hit.get("page", 0) or 0)
        modality = hit.get("modality", "text")
        page_key = (source, page, modality)
        if page and page_counts.get(page_key, 0) >= max_per_page:
            continue
        seen_content.add(content_key)
        if page:
            page_counts[page_key] = page_counts.get(page_key, 0) + 1
        selected.append(hit)
        if len(selected) >= top_k:
            break
    return selected
