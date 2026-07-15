"""Lookup-mode detection and constraint injection.

When the user asks a feasibility / lookup question (e.g. "查某某的 ICML 论文"
or "你可以爬取到吗"), we auto-append a short constraint block to their message
before it reaches the model. This keeps the user's original wording intact while
steering the agent toward "answer first, don't crawl whole sites".

Detection is keyword-based (no model call, no skill load) so it fires every
time without relying on the agent's discretion.
"""

from __future__ import annotations

import re

# Keywords that signal a lookup / feasibility question (not an implementation task).
# Mixed CN/EN on purpose — users type both.
_LOOKUP_HINTS = [
    # Chinese
    "查找", "查一下", "有没有", "是不是", "是否", "论文", "顶会", "录用",
    "爬取到吗", "能不能爬", "可以爬", "能不能查", "可以查到",
    "搜一下", "搜索", "帮我搜", "有哪些论文", "发过",
    # English
    "find paper", "lookup", "search for", "is there a paper",
    "published at", "accepted at", "icml", "neurips", "iclr", "cvpr",
    "can you crawl", "can you scrape", "can you fetch",
]

# Negations / contexts that mean "actually implement, not lookup".
_IMPLEMENTMENT_HINTS = [
    "改", "修", "实现", "重构", "添加", "删除", "写一个", "写代码",
    "加一个", "加个", "fix", "implement", "refactor", "add ", "edit ",
    "write_file", "edit_file", "loop.py", "hooks.py",
]


def is_lookup_query(query: str) -> bool:
    """True when a user message looks like a lookup/feasibility question.

    Heuristic: contains a lookup keyword AND is not dominated by implementation
    keywords. Short queries with a lookup verb win; long code-change requests
    that happen to mention "论文" lose.
    """
    if not query or not query.strip():
        return False
    low = query.lower()
    has_lookup = any(k in low for k in _LOOKUP_HINTS)
    if not has_lookup:
        return False
    # If the message is clearly about modifying code, don't hijack it.
    impl_hits = sum(1 for k in _IMPLEMENTMENT_HINTS if k in low)
    lookup_hits = sum(1 for k in _LOOKUP_HINTS if k in low)
    # Implementation intent outweighs a stray lookup keyword.
    if impl_hits >= 2 and impl_hits >= lookup_hits:
        return False
    return True


LOOKUP_CONSTRAINT = (
    "\n\n[Lookup mode — auto]\n"
    "成功标准：找到就给标题+来源链接；找不到就明确说「公开检索未找到」，"
    "并简要列出易混名/易混单位。\n"
    "槽位：作者/会议/年份等关键检索条件若仍模糊且上下文消不了，"
    "先用纯文字问用户 1–3 个问题，禁止用 fetch/bash 参数去猜。\n"
    "手段：优先用搜索摘要（搜索引擎 / OpenReview / OpenAlex / 学院喜报等）；"
    "禁止反复抓同一大页（如会议 Schedule / proceedings 目录）塞进对话。\n"
    "预算：联网类调用尽量 ≤6 次；连续无新信息就收口回答，不要换 URL 硬试。\n"
    "收口：先回答用户「有/没有」，再附来源；不要为了「拿证据」而无限抓页。\n"
    "篇幅：最终回答 ≤8 行；追问单位/作者时用 1–3 句直接说清归属，"
    "禁止再铺大表或复述整篇检索过程。\n"
    "护栏：LookupGuard 会硬性拦截超预算/连续无效 fetch，被拦后必须文字回答用户。\n"
)


def augment_query(query: str) -> str:
    """Return the user query with a lookup constraint appended when appropriate.

    The original wording is always preserved verbatim at the front; the
    constraint is appended so the model sees both the intent and the rules.
    """
    if not is_lookup_query(query):
        return query
    return query.rstrip() + LOOKUP_CONSTRAINT
