# 012 — Pie Menus：近重复 / 跑题 SERP / 次数硬顶掐死换源

**状态**：已修复（产品路径）并单题验证通过  
**暴露场景**：GAIA L1 `46719c30` — *"Pie Menus or Linear Menus, Which Is Better?" (2015)*  
**关联**：[010 LookupGuard 校准](./010-lookup-guard-calibration.md) · [005 工具空转](./005-tool-loop-drift.md) · [009 空摘要](./009-compact-empty-summary.md)（早期同题还曾撞过 compact 失忆）

## 题目在问什么

> Of the authors (First M. Last) that worked on the paper "Pie Menus or Linear Menus, Which Is Better?" in 2015, what was the title of the first paper authored by the one that had authored prior papers?

三步：

1. 找到 2015 这篇的作者  
2. 谁**在此之前已经发过论文**  
3. 这个人的**生平第一篇论文标题**

标准答案：`Mapping Human Oriented Information to Software Agents for Online Systems Usage`  
（作者侧：Pietro Murano 有先验；Iram N. Khan 无。）

## 症状（演进）

| 阶段 | Run / 行为 | 结果 |
|------|------------|------|
| Baseline | compact 空摘要 → 失忆瞎猜 | ❌（见 009） |
| 修 009/010 后 | 首搜 junk/空 → Jaccard near-dup 连 block → force → `unverified` | ❌ 零证据 |
| 放宽 near-dup 后 | 可换词，但 soft_stale 烧满后连 ACM/OpenAlex **fetch 也被拦** | ❌ |
| 仍有次数硬顶时 | 已确认 Murano/Khan，预算 10 次用尽，首篇标题靠记忆猜错 | ❌ |
| 去掉次数硬顶后 | OpenAlex 拉到 2001 首篇 | ✅ `run_20260722T152040Z` |

## 根因（叠了三层）

1. **Near-dup 过紧**  
   失败或跑题 SERP（如 Blender「Better Pie Menus」插件页）被当成成功检索进 Jaccard 历史 → 换词全被拦 → 零证据 `unverified`。

2. **Soft-stale 误伤换源**  
   连续空搜达到 `stale_limit` 后，连「打开具体 URL」也被全局禁网。研究题的正确动作恰恰是换 OpenAlex / ACM。

3. **联网次数硬顶不合理**  
   日常默认 ≤6、GAIA ≤10。多跳事实题（搜 → 作者 → 作品列表 → 首篇）正常就要十次以上。Claude Code 等也不用固定次数硬掐。Pie Menus 卡在「作者已确认、差一篇标题」。

## 修复

| 改动 | 位置 |
|------|------|
| Jaccard 只对比**成功且主题相关**的检索；失败/跑题 SERP 可换词；完全相同 query 仍禁 | `lookup_guard.py` |
| `_web_search_on_topic`：最长 query token 须出现在 SERP，否则 `soft_stale` | 同上 |
| Soft-stale **只拦继续 search**，不拦带 `url` 的 fetch | 同上 |
| **默认取消** `HARNESS_LOOKUP_FETCH_LIMIT` 硬顶（`0`/未设 = 无限）；需要时再设正整数 | `lookup_fetch_limit()` · GAIA `web_fetch_limit=None` |
| Prompt 去掉「尽量 ≤6」硬数字，改效率收口表述 | `prompts/lookup.py` |

仍保留：失败 URL/host、单站配额、连续 block → `LOOKUP_FORCE_ANSWER`。

## 验证

```bash
# 单元
pytest tests/test_lookup_guard.py tests/test_lookup_guard_loop.py -q

# 单题（Windows 建议 UTF-8）
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'
python -m evals.gaia --task-id 46719c30-f4c3-4cad-be07-d5cb21eee6bb --level 1 --limit 1
```

通过记录：`evals/results/gaia/run_20260722T152040Z`  
- pred ≈ gt（大小写/连字符差异，scorer 归一化后 PASS）  
- tools=13，~102s  
- 链路：OpenAlex 确认作者 → Murano 有先验 → 2001 首篇标题

## 教训

- Guard 应拦**空转模式**（同 query、同 host、同失败 URL），不要拦**换源与加深度**。  
- 固定联网次数对多跳检索是假效率；用 soft-stale + near-dup + host 配额更贴真实 thrash。  
- GAIA 暴露的问题改共享 LookupGuard，不要做评测专用放行。
