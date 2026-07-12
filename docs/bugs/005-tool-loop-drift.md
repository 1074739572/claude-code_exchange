# 005 — 工具空转与目标漂移（检索死循环 · 意图展示）

**状态：** 部分缓解（RepeatGuard · LookupGuard · micro_compact 防嵌套 · MCP 超时温和返回）  
**影响：** 长检索 / MCP fetch / 任何「手段取代目的」的多轮工具任务  
**关联：** [001 偏移 B](./001-todo-drift.md) · [004 压缩](./004-context-compaction.md)  
**证据会话：**
- `.project/session_1783772951.jsonl`（2026-07-11，Pu Keyang / ICML 2026）
- `.transcripts/transcript_1783839076.jsonl`（2026-07-12，南信大 ICML 2026；403/robots 后仍换 URL）

---

## 现象

用户要一个可验收答案（例如：「有没有某作者的 ICML 论文？」），终端却长时间出现：

```text
● mcp__fetch__fetch  url=https://proceedings.mlr.press/v235/
  → 5154 chars …
● mcp__fetch__fetch  url=https://proceedings.mlr.press/v235/   ← 同一 URL 再来
  → 5154 chars …
…（重复很多次）
```

体感是「中间在复读」，且任务越跑越偏：从「有没有论文」滑到「猜 MLR 单篇 URL 规则 / 抠 affiliation」，迟迟不收口。

同会话粗统计（`session.jsonl`）：

| 指标 | 约值 |
|------|------|
| 带工具的 assistant 回合 | ~66 |
| `mcp__fetch__fetch` | ~68（约一半以上工具调用） |
| 同一 `…/v235/` 目录页 | ~24 次 |
| 最长连续同 URL | ~5 |
| tool_result 总长 | ~1.3MB |
| compact 痕迹 | 很多次 |
| 纯文本收口回答 | 极少 |

---

## 这不是 UI 画了两遍

两条链路要分清：

| 通道 | 给谁 | 当时发生了什么 |
|------|------|----------------|
| 终端 | 人 | 每次真实 tool 调用都打一行 → **看起来像复读** |
| `tool_result` → 模型 | 模型 | 同一页内容反复进上下文 → **真的在空转** |

所以问题是 **agent 行为循环 + 目标漂移**，不是渲染 bug。

---

## 2026-07-12 补充：失败不换口 · compact 套娃 · 超时体感

### 现象（用户原话）

> 查找网页 tool 超时 / 报错，为什么那么长时间仍然不返回？

终端表现（`terminals/3.txt`、`transcript_1783839076.jsonl`）：

- OpenAlex / OpenReview / DBLP / Semantic Scholar **快速返回错误**（403、robots、429），并非 harness 卡死 120s
- 模型 **换 URL 继续 fetch**，迟迟不说「有/没有」
- `micro_compact` 把旧 `tool_result` **重复包裹** `<persisted-output>`，模型在上下文里看不清已查到的 JSON
- `compact` 摘要 `Remaining Work` 写「再试 Semantic Scholar」，与 lookup 收口规则冲突

### 根因（三层）

| 层 | 机制 | 后果 |
|----|------|------|
| **Harness** | 工具失败只进 `tool_result`，**loop 不停止**；lookup 约束仅 prompt | 错误 → 模型再试 → 再错误 |
| **Compact** | `persist_recallable_output` 对已包裹内容再次包裹 | 套娃 preview，模型以为「没查到」 |
| **模型** | 403/robots 后仍换参重试；compact 摘要推动「继续爬」 | 用户体感「一直 fetch、不回答」 |

MCP `future.result(timeout=120)` 超时抛 `TimeoutError` 时，此前**未捕获**，可能整轮 loop 崩溃（与 bash 的 `Error: Timeout (120s)` 不一致）。

### 已改（2026-07-12）

| 项 | 行为 |
|----|------|
| **LookupGuard** | lookup 模式：`≤6` 次 fetch（`HARNESS_LOOKUP_FETCH_LIMIT`）；连续 `2` 次无效结果硬拦（`HARNESS_LOOKUP_STALE_LIMIT`）；robots/403/429 的 host 黑名单 |
| **micro_compact 防嵌套** | `is_persisted_output()` — 已 `<persisted-output>` 不再二次包裹 |
| **MCP / dispatch 超时** | 120s 超时与其它异常 → 错误字符串，不崩溃 loop |
| **compact 摘要** | lookup 任务 `Remaining Work` 不得写「再试更多 URL」，应写「现在回答 有/没有」 |
| **cli** | `context["lookup_mode"]` 驱动 LookupGuard |

### 验证

```sh
pytest tests/test_lookup_guard.py tests/test_lookup_guard_loop.py tests/test_compact.py -q
```

手动：lookup 题连续 403/robots 后应出现 `[LookupGuard] Blocked`，模型被迫文字收口。

---

## 案例：已找到论文仍不停（Pu Keyang · ICML 2026）

比「找不到死磕」更冤的一种：**答案已经有了，子目标没停，继续烧 token。**

### 用户原话

```text
查找一下 pu keyang 南京信息工程大学 icml2026 的论文
```

（`session_1783772951.jsonl` 第 43 行）

### 找到时刻（第 121–123 行）

```text
**Found "Keyang Pu"** at line 15956! Let me get the full paper entry context.
…
Found the paper! Let me get more details - the OpenReview link and full HTML context.
```

**已定位论文：**

| 字段 | 内容 |
|------|------|
| 标题 | When Generalized Zero-Shot Learning Meets PU Learning: A Plug-and-Play Framework for Seen-Class Bias Mitigation |
| 作者 | Long Tang, Keyang Pu, Yingjie Tian |
| 会议 | ICML 2026 · Poster Session 6 · board **#3805** |

此时用户要的「有没有 / 哪篇」**已可回答**；agent 却把子目标抬成主目标（OpenReview 链接、poster PDF、南信大 affiliation、在 Schedule 大页里再确认 #3805），**找到后仍继续 fetch 同一 Schedule 页**，用户三次抱怨「又陷入无限循环」才停。

### 从发问到「找到」花了多少（用量对齐估算）

数据来源：`.project/session_1783772951.jsonl` 行号 + `.project/usage/2026-07-11.jsonl` 19:xx 时段（按 LLM 轮次对齐，非逐条时间戳一一对应）。

| 阶段 | LLM 轮次 | 工具调用 | 输入 token（估） | 输出 token（估） |
|------|----------|----------|------------------|------------------|
| 用户发问 → 说出 Found the paper | **30** | **45**（fetch **36**） | **≈ 65.6 万**（发问后 30 轮） / **≈ 88.9 万**（含发问前预热 47 轮） | **≈ 1.4 万** / **≈ 1.7 万** |
| **找到之后**（抠 affiliation / #3805 / OpenReview） | +42+ | Schedule 连刷 | **额外 ≈ 275 万 input**（19:xx 第 48–201 次） | **≈ 6.3 万** |
| 当日全量（含爬题等其它任务） | 436 次调用 | — | **≈ 760 万 input** | **≈ 17 万** |

同段会话内大页特征：到「找到」前已有 **4 次** Schedule `tool_result` 各约 **10 万字符**；`tool_result` 新内容合计约 **66 万字符**（每次 API 仍带全历史，计费远高于「新文本」本身）。

### 对照：摘要检索应怎样收口

| 你的 agent（找到时） | 合理 lookup 行为 |
|---------------------|------------------|
| 30 轮 + 36 次 fetch，≈65–89 万 input 才说出 Found | 几次搜索摘要 → 报标题/作者/链接 |
| 找到后不停，再烧 ≈275 万 input | 标题出来即回答用户，缺 affiliation 可一句带过 |
| 用户三次说「又循环了」 | 预算到或「有/没有」达成即停工具 |

### 根因（本案例特有）

1. **无「任务完成」判定** — 模型不认为「标题 + 作者」= 可交付，非要 HTML 里抠齐链接/单位。  
2. **`更多内容可用` 诱发续爬** — Schedule 截断暗示「下一页还有」，模型把「再 fetch 一次」当未完成任务。  
3. **compact 摘要固化子目标** — 摘要写「paper was found, however OpenReview/affiliation still being extracted」，下一轮继续搜 Schedule 而非先答用户。  
4. **Lookup 约束当时未上线** — 2026-07-11 当晚会话跑在改代码之前；`[Lookup mode]` 自动追加尚未生效。

---

## 根因（叠在一起）

1. **无进展仍重复同一招**  
   相同工具 + 相同参数（尤其同一 URL）连续调用；失败（robots / 404）也换同质 URL 硬试。

2. **手段取代目的**  
   子目标（发现 URL 模式、读 raw HTML）在 todo / compact 摘要里被抬成主目标，用户要的「清单或没有」被推迟。

3. **大结果撑爆上下文 → 反复 compact**（见 004）  
   大 HTML/JSON 进对话 → compact → 摘要保留「继续研究 MLR」→ 再搜 → 再胀。  
   虽有 `[Current user request]`，但中间轮次仍可被「还差一步就查清」绑架。

4. **主循环默认几乎无限轮**  
   eval 有 `max_rounds`，日常 CLI 默认不截断 → 空转可以很长。

5. **终端曾只晒工具、不晒意图**  
   模型若在同轮 `text` + `tool_use` 里写了「为什么调」，带工具的回合里 text 曾被跳过；结束才可能甩出来，用户更难判断「它在干嘛 / 是否已偏」。

---

## 其他 agent 通常怎么压这类问题

| 手段 | 做什么 |
|------|--------|
| 回合预算 | 每轮用户请求限制工具/LLM 次数，到期强制总结 |
| 卡住检测 | 同参重复、同失败连打 → 拦截或改策略 |
| 失败黑名单 | robots / 404 记域或 URL，禁止同质重试 |
| 目标锚定 | compact 后反复对齐「用户原话 + 成功标准」 |
| 检索分包 | explore 子 agent 只回短摘要，主上下文不吞全文 |
| 大结果落盘 | 对话只留指针（与 004 persist 同方向） |
| Todo 验收化 | todo 必须对应「可给用户的答案」，中间步骤超时取消并收口 |

共性：**不靠模型自觉，靠硬护栏 + 收口提醒。**

---

## 「调工具前显示为什么」——可行吗？会不会很复杂？

**可行，而且不必让模型「重新写一遍工具调用」。**

同一次 assistant 响应里本来就可以有：

```text
[text]     去读一下 sessions.py / 查一下 ICML 目录
[tool_use] read_file / mcp__fetch__…
```

这是**同一轮** API 返回的两个 block，不是二次请求。  
Harness 只需：**有 text 就展示；没有也不拦工具。**

不推荐：

- 再调一次模型「专门生成 why」（贵、慢、易假）
- 给每个 tool schema 强塞 `reason`（常被忽略或灌水）

推荐：

- UI：展示同轮前置 `text`（短摘要）
- Prompt（可选轻推）：调工具前写一句意图；与 `Act, don't explain` 冲突时可去掉，只保留展示

---

## 已做

| 项 | 说明 | 位置 |
|----|------|------|
| **RepeatGuard** | 相同工具+相同参数连续满 N 次（默认 3，`HARNESS_REPEAT_LIMIT`）则拦截，并回写提示 | `harness/agent/repeat_guard.py` · `loop.py` |
| **工具 UI 摘要** | 默认 compact：`● name 摘要` + `→ 结果摘要`；`verbose`/`off` 可切 | `harness/ui/tool_display.py` · `renderer.py` |
| **重复调用折叠展示** | `↻ ×N` / `⊘ blocked` | `renderer.tool_repeat` |
| **调工具前展示意图** | 同轮 `text` → `› …`；最终纯文本回答仍在回合结束打印 | `loop.py` · `renderer.tool_intent` · `cli.print_turn_assistants` |
| **Prompt 轻推** | identity：调工具前一句短意图（可再弱化/删除） | `harness/prompts/sections.py` |
| **Lookup mode 自动约束** | 检测查找题 → 追加收口规则；`context.lookup_mode` 驱动 LookupGuard | `harness/prompts/lookup.py` · `hooks.py` · `cli.py` |
| **LookupGuard** | lookup 模式硬拦截：超预算 / 连续无效 fetch / robots 主机重试 | `harness/agent/lookup_guard.py` · `loop.py` |
| **micro_compact 防嵌套** | 已 `<persisted-output>` 的结果不再二次包裹 | `harness/agent/compact/persist.py` · `layers.py` |
| **MCP 超时温和返回** | 120s 超时返回错误字符串，不崩溃 loop | `harness/mcp/client.py` · `dispatch.py` |

---

## 仍观察 / 可接着做

| 候选 | 痛点 | 大致做法 |
|------|------|----------|
| **主循环默认 max_rounds** | 空转可无限 | 如 25 轮到期强制总结并停工具 |
| ~~**失败 URL / robots 黑名单**~~ | 挡了还撞墙 | **lookup 模式已做**：同 host robots/403/429 后不再试 |
| **收口提醒** | 搜了很久仍不答用户；**已找到仍续爬** | 每 K 轮对照最新用户话：能答则停搜；标题/条目出现即强制总结 |
| **任务完成判定** | 「找到论文」不停 | lookup 成功标准写死：有标题即交付，affiliation 可选 |
| **fetch 结果强制落盘+短预览** | 大 HTML 喂进对话 | MCP/fetch 路径走 persist 阈值 |
| **检索走 explore task** | 主 agent 自己吞网 | 子 agent 只回条目列表 |
| **弱化/去掉意图 prompt** | 与 Act 风格打架 | 只保留「有 text 就显示」 |

---

## 相关文件

- `harness/agent/repeat_guard.py`
- `harness/loop.py`
- `harness/ui/tool_display.py` · `harness/ui/renderer.py`
- `harness/cli.py`（`print_turn_assistants` 跳过已现场展示的 tool-round text）
- `harness/prompts/sections.py`
- `harness/prompts/lookup.py`
- `tests/test_lookup_mode.py`
- `tests/test_repeat_guard.py`
- 运行时：`.project/session.jsonl` · `.project/session_*.jsonl` · `.project/usage/` · `.transcripts/transcript_*.jsonl`

---

## 一句话

**长检索空转 = 重复工具调用 + 目标被手段绑架 + 大结果引发反复 compact；终端复读是症状。**  
**已找到仍不停**（Pu Keyang 案例）= 缺任务完成判定 + 子目标（链接/单位）压过用户要的「有/没有」。  
展示「为什么调工具」= 把同轮已有 `text` 给人看，**不是**让模型重写工具调用协议。
