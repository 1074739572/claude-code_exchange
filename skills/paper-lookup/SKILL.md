---
name: paper-lookup
description: Look up academic papers (author + venue + year) with strict stop criteria. Use when user asks 查论文/有没有某人的 ICML/NeurIPS/ICLR/CVPR 论文, published at, OpenReview, OpenAlex — not for implementing features or rewriting local reports.
---

# Paper Lookup

## Success criteria (stop when met)

Return **as soon as** you can answer the user’s question with:

| Question shape | Done when you have |
|----------------|--------------------|
| 有没有 / 是否发表 | **有**：标题 + 作者 + 会议/年份 + 1 个来源链接；**没有**：明确说「公开检索未找到」+ 易混名/单位 |
| 列出某人某会论文 | 一份短列表（标题/链接），不必抠 PDF / affiliation HTML |
| 只要标题/链接 | 标题 + 链接即可，**禁止**继续为 poster board、日程页、单位核对再抓 |

Once the success row is satisfied → **plain-text answer, no more fetch/bash crawl**.

## Slot check (before tools)

Need at least: **author** (or clear unique name) **and** one of (venue | year | topic).

If a slot is missing and cannot be resolved from conversation → ask 1–3 questions, **no tools**.

Do **not** guess slots inside URL query strings or tool args.

## Means (preferred order)

1. OpenAlex / Semantic Scholar / DBLP / OpenReview **search or API** (small JSON/HTML)
2. University news / lab page search snippets
3. Only then: a single conference proceedings search page

**Forbidden as a main strategy:** repeatedly fetching huge Schedule / proceedings index pages, or re-fetching the same URL with tiny param changes.

## Budget

- Aim ≤ 6 web fetch / curl equivalents for one user question
- After 2 consecutive low-value results (robots / 403 / 429 / empty / shell-only OpenReview) → stop and answer with what you have
- Identical tool + identical args → do not retry; change strategy or conclude

## Answer format

Keep it short. Default:

```text
找到：《标题》（会议/期刊 · 年）
作者：…（高志伟单位：…）
链接：…
```

或未找到时 2–3 行即可。

Follow-ups（如「宁夏气象局哪来的」）→ **1–3 句**直答归属，不要再出大表、不要复盘工具过程。
User did not ask for a comparison table → do not invent one.

## Anti-patterns

- Finding the paper then continuing to “confirm affiliation / OpenReview HTML / poster #”
- Dumping multi-column markdown tables for a yes/no or “where did X come from” follow-up
- Putting `assume author is X` or caveats inside tool parameters
- Declaring “未找到” after only Google Scholar blocked by robots without trying OpenAlex/DBLP once
- Turning lookup into a coding / scraping-framework task
- Writing `check_affil.py` just to restate JSON the tool already returned — summarize in chat instead

## Relation to harness guards

`LookupGuard` / `RepeatGuard` may hard-block further fetches. If blocked → **answer immediately** with current evidence; do not invent another crawl loop.
---

