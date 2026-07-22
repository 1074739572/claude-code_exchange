# GAIA L1 Baseline 分析

- **Run**: `evals/results/gaia/run_20260722T080507Z`
- **命令**: `python -m evals.gaia --level 1 --limit 10`
- **总分**: `accuracy 5/10 = 50%` (level_1 5/10, errors=0, 1159s ≈ 19min)
- **日期**: 2026-07-22
- **当时配置**: `web_fetch_limit=18`, `web_stale_limit=3`, `max_rounds=50`, 已启用 `web_budget` LookupGuard

## 逐题归因

| # | task | 题目（简） | gt | 预测 | 工具 | 耗时 | 结果 | 失败模式 |
|---|------|-----------|-----|------|------|------|------|---------|
| 1 | e1fc63a2 | Kipchoge 跑到月球「多少**千**小时」 | 17 | 17000 | 21 | 112s | ❌ | A 读题/单位 |
| 2 | 8e867cd7 | Mercedes Sosa 2000–2009 录音室专辑数 | 3 | 3 | 6 | 178s | ✅ | （被 block 后靠记忆蒙对）|
| 3 | ec09fa32 | 乒乓球游戏选哪个球胜率最高 | 3 | 3 | 4 | 373s | ✅ | 纯推理+模拟 |
| 4 | 5d0080cb | Leicester 论文鱼袋体积 m³ | 0.1777 | 0.177 | 2 | 61s | ❌ | B guard 太紧 |
| 5 | a1e91b78 | YouTube 视频同时最多几种鸟 | 3 | 7 | 11 | 45s | ❌ | E 能力缺口(视频) |
| 6 | 46719c30 | "Pie Menus or Linear Menus" 作者首篇论文标题 | Mapping Human Oriented… | FFitts Law… | 3 | 240s | ❌ | C compact 空摘要 |
| 7 | 4b6bb5f7 | Doctor Who S9E11 官方剧本第一场标题 | THE CASTLE | THE CONFESSION DIAL | 11 | 54s | ❌ | D 该 fetch 却用记忆 |
| 8 | cffe0e32 | Secret Santa 谁没送礼 (docx) | Fred | Fred | 16 | 44s | ✅ | 文件解析+推理 |
| 9 | 2d83110e | 反写句子 "left" 的相反词 | Right | right | 1 | 3s | ✅ | 平凡 |
| 10 | 5cfb274c | 绿格能否哈密顿回路 (xlsx) | No | no | 13 | 49s | ✅ | openpyxl+图论 |

## 失败模式（5 个失败 = 5 种不同病因，非单一模式）

### A — 读题/单位错误（Kipchoge）
- 题目明确 "how many **thousand hours**" + "Round to nearest 1000, no comma"。
- agent 算对 17,056 小时，却报 17000 而非 17（千小时）。**数据对，单位读错。**
- 21 次 web 调用并非失败主因，失败在最后一步读题。

### B — Guard 太紧，合法 fetch 被 block（fish bag）⭐
- 只 2 次工具，PDF 在 `journals.le.ac.uk` 被 LookupGuard 判 stale/404 block。
- 转从 HuggingFace 二手讨论捞到 0.177，离真值 0.1777 只差一位。
- **guard 误杀合法 PDF fetch**。与"over-fetch"诊断相反。

### C — compact 把上下文清空（Pie Menus）⭐⭐最严重 ✅ 已修（009）
- transcript 首条 = `{"role":"user","content":"[Compacted]\n\n(empty summary)"}` —— compact 产生了**空摘要**。
- agent thinking: "I'm completely blocked from all network access. I'll have to rely on my training data."
- 之后 3 次 bash `find` 本地文件失败，纯靠记忆猜作者+首篇论文，全错。
- **compaction bug**：整段搜索历史压成 "(empty summary)"，agent 彻底失忆。
- **修复**：`docs/bugs/009-compact-empty-summary.md`（thinking 回退 + 空摘要降级）。

### D — 该 fetch 却退回记忆且记错（Doctor Who）
- 7 次 web_search + 3 次 fetch，全 stale/空（剧本站 robots/404）。
- LookupGuard 3 连 stale 后 block；block 后 agent 又硬撞 3 次（**guard 不服从问题确认**）。
- 最后退回参数记忆，自信报 "THE CONFESSION DIAL"——官方剧本第一场是 "THE CASTLE"。
- **block 后无"换策略"引导**，直接退回错误记忆。

### E — 真能力缺口（YouTube 鸟类）
- 需看视频数同时出镜鸟种。harness 无 YouTube/视频理解能力。瞎猜 7（gt=3）。
- 非 prompt 可修，需加视频工具或接受放弃。

## 关键结论（修正"over-fetch"诊断）

1. **真正的 over-fetch thrash 只 Mercedes Sosa 一例，且它还过了**。L1 里 over-fetch 不是主要失分点。
2. **最危险是 compact 空摘要（模式 C）**——把能做的题变纯瞎猜。优先级最高。
3. **LookupGuard 两头不对**：对 Kipchoge 太松（21 次放行），对 fish bag 太紧（2 次 block 合法 PDF）。stale-limit=3 在 Doctor Who 正好卡在该 fetch 时。
4. **block 后退回参数记忆且自信报错**（模式 D）比"不读 fetched 页面"更常见。agent 无"无法验证→换策略/存疑"引导。
5. **读题/单位**（模式 A）是模型 reading comprehension，但"finalize 前重读题+查单位"步骤能救。
6. **真本事题全过**：ping-pong、Secret Santa、绿格哈密顿、反写句子。harness 工具+推理链路本身 work，问题集中在**需外部 web 验证的具体事实题**。

## 修复优先级

| 优先级 | 修复 | 能救回 | 状态 |
|--------|------|--------|------|
| 🔴 P0 | **修 compact 不产生空摘要**：compact 时强制先输出 "Facts gathered + URLs tried" 再压；或禁止 web_budget 模式下自动 compact。 | Pie Menus (C) | TODO |
| 🟠 P1 | **LookupGuard 重新校准**：区分"404/robots 的具体 URL"（只 block 该 URL）与"搜索整体 stale"（才 block 整类）。PDF fetch 不被 stale-limit 误杀。 | fish bag (B) | TODO |
| 🟠 P1 | **block 后引导换策略/存疑**：block 消息加 "Do NOT answer from memory for specific facts you couldn't verify; try a different source type or state uncertainty." | Doctor Who (D) | TODO |
| 🟡 P2 | **finalize 前重读题+查单位**：`_force_finalize` / FINAL ANSWER 前注入 "Re-read the question. Check units / 'how many thousand' phrasing. Verify your number matches what was asked." | Kipchoge (A) | TODO |
| 🟡 P2 | **guard 连续 block 升级**：连续 2–3 次 block 就强制 `_force_finalize`，不让模型继续撞+退回记忆。 | Doctor Who (D) | TODO |
| ⚪ P3 | **视频能力**：接 YouTube transcript API 或 yt-dlp。 | YouTube (E) | TODO |

**预期收益**：P0+P1+P2 预计把 L1 从 5/10 提到 7–8/10（救回 Pie Menus / fish bag / Doctor Who / Kipchoge 中 3 道），不依赖换模型。

## 失败模式机制详解（为什么会出现）

> 当前模型 = `deepseek-v4-flash`（推理模型，回复含 `thinking` 块）。

### 模式 C — compact 把上下文清空（最致命，确定的代码 bug）

**调用链**：`loop` 每轮跑 `prepare_context`（`compact/pipeline.py:68`）→ 体积超 `CONTEXT_LIMIT` 时 `compact_history`（`pipeline.py:42`）→ `summarize_history`（`pipeline.py:49`）。

**病根在 `compact/summarize.py:46-66`**：

```python
response = create_message(model_id=get_model(), messages=[...], max_tokens=2000)
return extract_text(response.content) or "(empty summary)"
```

- `extract_text`（`tools/dispatch.py:19`）只取 `block_type == "text"` 的块，**`thinking` 块被完全丢弃**。
- 推理模型把摘要写进 `thinking` 通道，`text` 块为空 → `extract_text` 返回 `""` → `"" or "(empty summary)"` → **`"(empty summary)"`**。

**两个 bug 叠加，必然清空**：
1. `extract_text` 只读 `text` 块，丢弃 `thinking` 块 —— 推理模型的摘要若只活在 thinking 里就丢了。
2. `max_tokens=2000` 对推理模型太小 —— thinking 吃光预算，text 块被截断成空。

任一单独触发都会让摘要判定为空。然后 `_build_compacted`（`pipeline.py:33`）把上下文替换成 `{"role":"user","content":"[Compacted]\n\n(empty summary)"}` + 最后 5 条 → 彻底失忆。Pie Menus 那题就是这么变成纯瞎猜的。

**修法**：`summarize.py` 的 `extract_text` 改成"先取 text 块，没有就回退取 thinking 块"；`max_tokens` 从 2000 提到 8000+。

### 模式 A — Kipchoge 单位读错（prompt 缺一步，非代码 bug）

题目 "how many **thousand hours**" + "Round to nearest 1000, no comma"。
- 正解：17000 小时 = 17 千小时 → 答 **17**。
- agent：算对 17056，理解成"四舍五入到 1000 = 17000" → 答 **17000**。

机制：短语歧义 + `_force_finalize` 的 prompt 只说 "output FINAL ANSWER: <best short answer>"，**没有"重读题目、核对单位"这一步**。算对了数，死在最后一步没回去对单位。

### 模式 B — fish bag guard 太紧（计数维度太粗）

`lookup_guard.py:64` 的 `is_low_value_fetch_result`：fetch 返回 404 / 短错误页 → 判 stale → `consecutive_stale += 1`。

机制：**guard 把"这个 URL 404"正确识别成低价值，但反应是"全局 web stale 计数 +1"，而不是"只 ban 这个 URL，换个源再试"。** agent 看到连着失败，又没有"论文 404 → 试 Google Scholar / arXiv / ResearchGate"的 fallback，2 次就放弃，从二手讨论捞到 0.177（真值 0.1777，差一位）。

根因：**stale 计数是"全局 web"维度，把"一个坏 URL"放大成"整个 web 方向不行"。** 应 per-URL ban + 全局 stale 分开计。

### 模式 D — Doctor Who 该 fetch 却用记忆（guard 不硬停 + 不区分 findings vs 记忆）

`loop.py:285-307`：guard block 时只把 block 消息塞进 `tool_result` 然后 `continue`，**不停止 loop、不强制 finalize**：

```python
if lookup_block:
    results.append({"type":"tool_result", ..., "content": lookup_msg})
    continue    # 下一轮 LLM 照常调用，模型可无视 block 再叫工具
```

机制链路：
1. 7 web_search + 3 fetch，剧本站全 robots/404 → 全 stale
2. `consecutive_stale >= 3` → guard block，喊 "Answer NOW with partial findings"
3. **"partial findings" 在模型眼里 = "我脑子里的知识"**，它不区分"刚 fetch 到的"和"训练时记住的"
4. 模型无视 block 又硬撞 3 次（block 只是文字，loop 没硬停）—— **guard 不服从**
5. 最终退回参数记忆，自信报 "THE CONFESSION DIAL"（官方剧本第一场是 "THE CASTLE"）

两个机制问题：
- **block 后无"换策略/存疑"引导**，模型把记忆当 findings 用。
- **block 不升级**：连续被 block N 次还是返回同一段文字，没有"连续 2 次 block → 强制 `_force_finalize`"的硬升级。

### 模式 E — YouTube 能力缺口（非 prompt 可修）

harness web 工具只有 `web_search`（Bing/so.com RSS）、`mcp__fetch__fetch`（HTTP 抓 HTML）、`mcp__playwright__*`（浏览器导航）。**没有任何工具能拿 YouTube 视频内容或 transcript。** agent 搜不到、抓不到视频帧，只能瞎猜 7（gt=3）。需加 YouTube transcript API 或 yt-dlp 工具。

### 机制总览图

```
推理模型摘要写进 thinking ──┐
compact 只读 text 块 ──────┘  → (empty summary) → 失忆        [模式 C, 最致命]
max_tokens=2000 太小 ──→ thinking 吃光预算 → text 空 ──┘(加成 C)

guard 把单 URL 404 放大成全局 stale ──→ agent 2 次就放弃        [模式 B]

guard block 只塞文字不硬停 ──→ 模型无视继续撞 + 退回记忆 ──┐
block 喊 Answer NOW 但不区分 findings vs 记忆 ────────────┘ → 自信报错  [模式 D]

_force_finalize 不要求重读题/核对单位 ──→ 算对数死在单位上      [模式 A]

无视频工具 ──→ 瞎猜                                        [模式 E]
```

**归类**：C/D 是架构 bug（compact 提取逻辑 + guard 不升级），A 是 prompt 缺一步，B 是 guard 计数维度太粗，E 是工具缺口。**只有 C 是确定的代码 bug，其余是设计缺陷。**

## 复现

```powershell
python -m evals.gaia --level 1 --limit 10
# 结果写入 evals/results/gaia/run_<timestamp>/
#   summary.json / results.jsonl / predictions.jsonl / <task_id>.messages.json
```
