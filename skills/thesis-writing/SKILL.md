---
name: thesis-writing
description: Write or rewrite long technical reports/thesis chapters using local RAG over files/样例. Use when user asks to 仿写、改写、撰写结题/技术报告/章节，或 mentions files/样例 and reference documents.
---

# Thesis & Technical Report Writing Skill

You assist with **writing or rewriting** long Chinese technical reports (技术报告、结题报告、实施方案).  
Reference material lives in:
- `files/样例/` — **format/style** examples (technical reports, plans)
- `files/指标与交付要求.md` — **mandatory indicators & deliverables** (what to write, what to achieve)

Retrieve via **local RAG** — never paste entire reference files into context.

**First step for any thesis/report task:** `load_skill("thesis-writing")` if not already loaded, then follow this skill.

---

## 0. Resume（跨会话续写，自动）

Harness **自动保存**到 `.project/`：

| 文件 | 内容 |
|------|------|
| `.project/state.json` | 章节进度、当前章、输出路径、备注 |
| `.project/history.json` | 完整对话历史 |

**重启 `python main.py` 后**：
- 自动加载历史对话 + 进度横幅
- 输入 `/resume` 查看章节清单
- 直接说「继续写第 X 章」即可，**不必从零规划**

Agent 工具：

```
project_status              # 查看进度
project_set_chapter         # 标记章节 in_progress / done
project_note notes="..."    # 保存备注
project_init reset=true     # 仅当要完全重来时
```

写完一章后 `write_file` 到 `output/XX_*.md` 会**自动**把该章标为 done。

---

## 1. One-time setup (per corpus change)

Before writing, ensure the index exists:

```
rag_status
```

If empty or corpus changed:

```
rag_index path="files"
```

This indexes both `files/样例/` (format) and `files/指标与交付要求.md` (constraints).  
Index artifacts: `.rag/chunks/`, `.rag/index/corpus.json`.

---

## 2. Core workflow (every section)

For **each chapter or section** you write or rewrite:

```
1. rag_search  → retrieve style/structure examples
2. Plan        → outline bullets matching reference patterns
3. write_file  → draft into an output path (e.g. output/01_引言.md)
4. Self-check  → structure aligned, no sentence-level copy
```

**Never** skip `rag_search` before drafting a new section.  
**Never** `read_file` whole reference docx files (too large); use RAG instead.

---

## 3. How to call `rag_search`

### Tool parameters

| Parameter | When to use |
|-----------|-------------|
| `query` | Chinese keywords: section topic + intent (结构 / 段落 / 实验 / 总结) |
| `top_k` | Default `8`; use `5` for narrow topics, `10` for broad chapters |
| `source` | Optional filename filter, e.g. `12  CWRF区域气候模式重点区域和流域尺度技术报告.docx` |
| `chapter` | Exact chapter title filter, e.g. `引言` or `流域尺度CWRF气候预测百分位数订正算法` |
| `include_captions` | `false` for body text; `true` only when writing figure/table captions |

### Constraint checks (指标与交付)

Before finalizing any chapter, search the requirements doc:

```
rag_search query="性能指标 空间范围 2920 时次 预警时效" source="指标与交付要求.md"
rag_search query="交付 模型源代码 研制报告 实施方案" source="指标与交付要求.md"
```

Ensure draft sections explicitly address FY-4 全通道、4 km 分辨率、0–1 小时预警、交付清单等硬性条款。

### Query recipes (copy and adapt)

| Writing task | Example query |
|--------------|---------------|
| 引言 / 编写目的 | `编写目的 技术报告 引言 段落结构` |
| 项目背景 | `项目背景 政策 意义 段落展开` |
| 研究目标 | `研究目标 总体目标 考核指标 小节结构` |
| 研究方法 | `研究方法 技术路线 实验方案` |
| 数据与指标 | `数据 验证 评价指标 模式` |
| 实验结果 | `实验结果 分析 月度 季尺度 延伸期` |
| 流域对比 | `长江流域 海河流域 黄河流域 对比结构` |
| 算法章节 | `订正算法 机器学习 集合 实验方案` |
| 本章小结 | `总结与展望 本章 归纳 段落结尾` |
| 全文总结 | `总结与展望 全文 结论` |

### Source hints

| Document (under `files/样例/`) | Best for |
|--------------------------------|----------|
| `12 …技术报告.docx` | Full structure, methods, experiments, detail |
| `13 …总结报告.docx` | Concise summaries, executive tone |
| `5 …实施方案.docx` | Implementation plan, milestones, organization |

Prefer **技术报告** for section structure; use **总结报告** for brevity; use **实施方案** for plan-style sections.

---

## 4. Multi-pass retrieval (important)

One search is usually not enough. Use **2–3 targeted searches** per chapter:

```
Pass A — structure:  rag_search query="第X章 章节结构 小节标题"
Pass B — prose:      rag_search query="X.X 段落 过渡句 表述"
Pass C — domain:     rag_search query="CWRF 订正 实验" chapter="…"
```

Then synthesize; do not concatenate reference text.

---

## 5. Rewriting rules (仿写约束)

1. **学结构**：章节顺序、标题层级、小节划分参照检索结果  
2. **学语气**：技术报告体 — 客观、陈述式、少口语  
3. **学套路**：如「长江 / 海河 / 黄河」平行叙述、「月度与季尺度 / 延伸期」分述  
4. **禁止照抄**：不得整句复制参考原文；数据、项目名替换为用户实际内容  
5. **标明未知**：没有的用户数据用 `[待补充]`，不要编造实验数字  
6. **输出路径**：建议 `output/<章节编号>_<标题>.md`，最后可合并

---

## 6. Example session

User: 「仿照样例写引言中的编写目的」

```
rag_status
rag_search query="编写目的 技术报告 引言" top_k=5 include_captions=false
rag_search query="项目背景 气候预测 段落" top_k=5 source="12  CWRF区域气候模式重点区域和流域尺度技术报告.docx"
write_file path="output/01_引言_编写目的.md" content="..."
```

User: 「写第7章订正算法实验方案」

```
rag_search query="订正算法 实验方案 月度 季尺度" chapter="流域尺度CWRF气候预测百分位数订正算法" top_k=8
rag_search query="多变量订正 实验设计" top_k=5
write_file path="output/07_订正算法_实验方案.md" content="..."
```

---

## 7. Troubleshooting

| Problem | Action |
|---------|--------|
| `RAG index is empty` | Run `rag_index path="files/样例"` |
| No hits | Broaden query; remove `chapter` filter; try synonyms (研究方法 / 技术路线) |
| Wrong chapter retrieved | Add `chapter="精确章标题"` from `rag_search` hit metadata |
| Output too like original | Re-search with `top_k=3`; rewrite in your own words; change order of points |

---

## 8. After loading this skill

Confirm to user:

- RAG index status (`rag_status` or assume indexed)  
- Which reference doc(s) you will mirror  
- Output file plan (`output/*.md`)  

Then proceed section by section with `rag_search` before each draft.
