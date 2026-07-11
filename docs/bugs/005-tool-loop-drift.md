# 005 — 工具空转与目标漂移（检索死循环 · 意图展示）

**状态：** 部分缓解（RepeatGuard + 工具 UI 摘要 + 调工具前展示模型 text）  
**影响：** 长检索 / MCP fetch / 任何「手段取代目的」的多轮工具任务  
**关联：** [001 偏移 B](./001-todo-drift.md) · [004 压缩](./004-context-compaction.md)  
**证据会话：** `.project/session.jsonl`（约 2026-07-11，查「南信大 Puke Yang / ICML」）

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

---

## 仍观察 / 可接着做

| 候选 | 痛点 | 大致做法 |
|------|------|----------|
| **主循环默认 max_rounds** | 空转可无限 | 如 25 轮到期强制总结并停工具 |
| **失败 URL / robots 黑名单** | 挡了还撞墙 | 同 URL/同错误类限次 |
| **收口提醒** | 搜了很久仍不答用户 | 每 K 轮对照最新用户话：能答则停搜 |
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
- `tests/test_repeat_guard.py`
- 运行时：`.project/session.jsonl` · `.transcripts/transcript_*.jsonl`

---

## 一句话

**长检索空转 = 重复工具调用 + 目标被手段绑架 + 大结果引发反复 compact；终端复读是症状。**  
展示「为什么调工具」= 把同轮已有 `text` 给人看，**不是**让模型重写工具调用协议。
