# 011 — Auto-compact：50KB 字符硬限过早压缩

**状态**：已修复（产品路径）  
**关联**：[004 上下文压缩](./004-context-compaction.md) · [009 空摘要失忆](./009-compact-empty-summary.md)  
**暴露场景**：GAIA web 检索 / 日常查网页 — 两三次 fetch 就触发 compact

## 症状

- 默认 `CONTEXT_LIMIT = 50000`（**字符**）一碰就压上下文。
- 单页 fetch 常 10–50KB，研究任务几乎必然过早 compact → 丢细节 / 叠 009 空摘要问题。
- 对 DeepSeek/Qwen **1M** 窗口模型：只用了窗口的约 **5–8%** 就开始压，远比 Claude Code 激进。

## 根因

| 层 | 问题 |
|----|------|
| 阈值单位 | 固定字符预算，不跟模型 `context_window` |
| 行业对照 | Claude Code ≈ `0.835 × window`（token）；Cline ≈ 75% |
| 覆盖语义 | `HARNESS_CONTEXT_LIMIT` 曾是字符，易与 token 混淆 |

## 修复

触发改为 Claude Code 同款：

```text
estimate_tokens(messages)  ≳  0.835 × model_context_window  →  compact
```

- `estimate_tokens` ≈ `json.dumps(messages)` 字符数 `/ 4`
- 窗口：`models.json` 的 `context_window` → 内置表 → 默认 128K
- Env：
  - `HARNESS_AUTOCOMPACT_PCT`（默认 0.835，也可用 83.5）
  - `HARNESS_CONTEXT_WINDOW`（强制窗口 tokens）
  - `HARNESS_CONTEXT_LIMIT`（**绝对 token 阈值**，绕过比例；语义已从字符改为 token）
- GAIA 默认同日常比例规则（不再硬塞 200K 字符），仍可传绝对 token 覆盖；`compact_tail` 默认 10

### 主要文件

- `harness/agent/compact/sizing.py` — `estimate_tokens` / `should_autocompact` / threshold
- `harness/agent/compact/pipeline.py` — `prepare_context` 用 token 判断
- `harness/settings.py` — `context_limit()` 委托 threshold
- `config/models.json` + `harness/models.py` — `context_window` 字段
- `evals/gaia/agent_run.py` — 默认走比例规则

### 验证

```bash
pytest tests/test_compact.py -q
```

DeepSeek 1M 下约 **835K tokens** 才 auto-compact（旧：~50KB 字符）。
