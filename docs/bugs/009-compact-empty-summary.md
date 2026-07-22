# 009 — Compact 空摘要失忆（推理模型 thinking 块）

**状态：** 已修复（2026-07-22）  
**关联：** [004 上下文压缩](./004-context-compaction.md) · GAIA L1 baseline 模式 C（`evals/gaia/BASELINE_ANALYSIS.md`）

---

## 现象

长对话或 web 检索多轮后触发 `compact_history`，压缩后的历史变成：

```text
{"role": "user", "content": "[Compacted]\n\n(empty summary)"}
```

其后只保留尾部几条消息。Agent 表现为：

- 以为「完全没有网络 / 没有证据」，改靠训练记忆瞎猜
- 重复已经搜过的查询（摘要里没有 Sources Tried）
- GAIA 例：Pie Menus 题 compact 后 3 次 `bash find`，最终答错作者首篇论文标题

日常 CLI 长检索同样会中——**不是评测专用 bug**。

---

## 复现条件

1. 使用推理模型（如 `deepseek-v4-flash`），回复含 `type=thinking` 块
2. 上下文超过 auto-compact 阈值（默认 `≈0.835 × model_context_window` tokens）
3. `summarize_history` 调 LLM 写结构化摘要

---

## 根因（两处叠加）

### 1. `extract_text` 只读 `type=text`

`summarize_history` 原先：

```python
return extract_text(response.content) or "(empty summary)"
```

`extract_text`（`harness/tools/dispatch.py`）只拼接 `type == "text"` 的块。  
推理模型常把完整摘要写进 `thinking` / `reasoning`，`text` 为空 → 得到 `""` → 落入 `"(empty summary)"`。

### 2. `max_tokens=2000` 对推理模型过小

thinking 先占预算，可见 text 被截断为空，加剧问题 1。

### 3. 管道无兜底

`compact_history` 无条件把摘要塞进历史，**空摘要也会替换全部旧消息**，比「不压缩」更糟。

---

## 修复（产品路径，非评测换皮）

| 改动 | 文件 |
|------|------|
| `extract_summary_text`：先 text，空则回退 thinking/reasoning | `harness/agent/compact/summarize.py` |
| `max_tokens` 2000 → 8000 | 同上 |
| 空结果返回 `SUMMARY_UNUSABLE`，不再用 `(empty summary)` 当真摘要 | 同上 |
| 摘要模板增加 `## Sources Tried` / `## Facts Gathered`（lookup 续作） | 同上 |
| `is_summary_unusable` → `compact_history` / `reactive_compact` **降级**：snip + 保留尾部 + 明确 notice，禁止空摘要替换 | `harness/agent/compact/pipeline.py` |

验证：`tests/test_compact.py`（`TestSummaryThinkingFallback`）。

---

## 与 004 的关系

004 Phase 1 解决了「无 tail / 无结构化模板 / micro 硬删」。  
009 是其后在**推理模型**上暴露的第二刀：模板再好，若提取路径读不到 thinking，仍会写成空摘要失忆。

---

## 仍观察

- 降级路径仍有损（snip），极端超长时 reactive_compact 仍可能需要更强裁剪
- 是否在 summarizer 调用时对 reasoning 模型关 thinking / 强制可见 text（provider 能力不一）
- GAIA 抬 `CONTEXT_LIMIT` 只减少触发次数，**不能替代本修复**
  （现已改为 `0.835×window`，触发更少，但仍依赖空摘要降级）
