"""Built-in web search — no MCP, no robots.txt gate, no Chrome required.

Chinese queries prefer 360/so.com (Bing CN often returns irrelevant geo noise).
English / mixed queries use Bing RSS. Returns title/url/snippet for citation.
Prefer this over mcp__fetch on google/baidu/bing search pages.
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT = 12.0
_MAX_RESULTS = 8
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")

# 360 so.com: titles + display cites (real domains)
_SO_TITLE = re.compile(
    r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>\s*</h3>',
    re.IGNORECASE | re.DOTALL,
)
_SO_CITE = re.compile(r"<cite[^>]*>(.*?)</cite>", re.IGNORECASE | re.DOTALL)
_SO_MDURL = re.compile(r'data-mdurl="(https?://[^"]+)"', re.IGNORECASE)
_SO_SNIP = re.compile(
    r'class="res-desc"[^>]*>(.*?)</p>',
    re.IGNORECASE | re.DOTALL,
)

# Bing RSS
_RSS_ITEM = re.compile(r"<item>(.*?)</item>", re.IGNORECASE | re.DOTALL)
_RSS_TITLE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_RSS_LINK = re.compile(r"<link>(.*?)</link>", re.IGNORECASE | re.DOTALL)
_RSS_DESC = re.compile(r"<description>(.*?)</description>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str = ""


def _strip_html(text: str) -> str:
    cleaned = _TAG_RE.sub("", text or "")
    cleaned = html.unescape(cleaned)
    return _WS_RE.sub(" ", cleaned).strip()


def _http_get(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read(500_000)
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="ignore")


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _query_tokens(query: str) -> list[str]:
    tokens = _CJK_RUN_RE.findall(query)
    tokens.extend(_ASCII_WORD_RE.findall(query))
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def _is_relevant(hit: SearchHit, tokens: list[str]) -> bool:
    if not tokens:
        return True
    blob = f"{hit.title} {hit.url} {hit.snippet}".lower()
    matched = sum(1 for t in tokens if t.lower() in blob)
    # Require at least one solid token match; two when query is rich.
    need = 2 if len(tokens) >= 3 else 1
    return matched >= need


def _search_so(query: str, limit: int) -> list[SearchHit]:
    url = "https://www.so.com/s?" + urllib.parse.urlencode({"q": query})
    body = _http_get(url)
    titles = _SO_TITLE.findall(body)
    cites = [_strip_html(c).split()[0] if _strip_html(c) else "" for c in _SO_CITE.findall(body)]
    mdurls = [
        u
        for u in _SO_MDURL.findall(body)
        if "hao.360.com" not in u
        and "bing.com" not in u
        and "360kan.com" not in u
        and "so.com" not in u
    ]
    snips = [_strip_html(s) for s in _SO_SNIP.findall(body)]
    hits: list[SearchHit] = []
    for i, (href, title_html) in enumerate(titles):
        if len(hits) >= limit * 2:
            break
        title = _strip_html(title_html)
        if not title or "换一换" in title:
            continue
        real = ""
        cite = cites[i] if i < len(cites) else ""
        if i < len(mdurls):
            real = mdurls[i]
        elif cite and "." in cite:
            real = "https://" + cite.lstrip("/")
        elif href.startswith("http") and "so.com/link" not in href:
            real = href
        else:
            real = href if href.startswith("http") else ""
        if not real:
            continue
        snippet = snips[i] if i < len(snips) else ""
        hits.append(SearchHit(title=title, url=real, snippet=snippet))
    return hits


def _search_bing_rss(query: str, limit: int) -> list[SearchHit]:
    url = "https://cn.bing.com/search?" + urllib.parse.urlencode(
        {"q": query, "format": "rss", "mkt": "zh-CN"}
    )
    body = _http_get(url)
    hits: list[SearchHit] = []
    for block in _RSS_ITEM.findall(body):
        if len(hits) >= limit * 2:
            break
        titles = _RSS_TITLE.findall(block)
        links = _RSS_LINK.findall(block)
        descs = _RSS_DESC.findall(block)
        if not titles or not links:
            continue
        title = _strip_html(titles[0])
        href = _strip_html(links[0])
        snippet = _strip_html(descs[0]) if descs else ""
        if not title or not href:
            continue
        hits.append(SearchHit(title=title, url=href, snippet=snippet))
    return hits


def _format_hits(provider: str, query: str, hits: list[SearchHit]) -> str:
    lines = [f"web_search ({provider}) q={query!r} — {len(hits)} result(s):"]
    for i, hit in enumerate(hits, 1):
        lines.append(f"{i}. {hit.title}")
        lines.append(f"   {hit.url}")
        if hit.snippet:
            lines.append(f"   {hit.snippet[:220]}")
    return "\n".join(lines)


def run_web_search(query: str, max_results: int = 5) -> str:
    """Search the web and return a compact citeable result list."""
    q = (query or "").strip()
    if not q:
        return "Error: query is empty."
    try:
        limit = int(max_results)
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, _MAX_RESULTS))
    tokens = _query_tokens(q)

    # Chinese → so.com first; otherwise Bing RSS first.
    if _has_cjk(q):
        providers: list[tuple[str, object]] = [
            ("so", _search_so),
            ("bing", _search_bing_rss),
        ]
    else:
        providers = [
            ("bing", _search_bing_rss),
            ("so", _search_so),
        ]

    errors: list[str] = []
    for name, fn in providers:
        try:
            raw = fn(q, limit)
        except urllib.error.HTTPError as exc:
            errors.append(f"{name}: HTTP {exc.code}")
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        hits = [h for h in raw if _is_relevant(h, tokens)][:limit]
        if not hits:
            errors.append(f"{name}: no relevant results ({len(raw)} raw)")
            continue
        return _format_hits(name, q, hits)

    detail = "; ".join(errors) if errors else "unknown"
    return (
        f"web_search failed for q={q!r} ({detail}). "
        "Try a more specific query, or open a known URL with mcp__fetch__fetch. "
        "Baidu search pages need a real browser (Playwright + Chromium)."
    )
