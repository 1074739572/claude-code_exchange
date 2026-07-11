# Bug & 改进记录

本目录记录真实使用中的问题、根因，以及整条链路上的修复。  
**不是路线图**：下面「仍可商量」只是观察项，下一步做什么一起定。

上游与已做能力总览见 [README.md](../../README.md)。

---

## 索引

| ID | 标题 | 状态 | 一句话 |
|----|------|------|--------|
| [001](./001-todo-drift.md) | Agent 偏移（任务表 · 话题 · 会话） | A 已修；B/C 大部分已修 | 「活干了表不对 / 问 A 答 B / 打断 400」 |
| [002](./002-prompt-cache-vs-dynamic-context.md) | Prompt 缓存命中 | 分层已落地 | static / ephemeral 拆开，命中从 ~0% 拉起来 |
| [003](./003-resume-opt-in.md) | Resume OpenCode 模式 | 已实施 | 默认全新；续项目要 `/resume project` |
| [004](./004-context-compaction.md) | 上下文压缩丢信息 | Phase 1 + 最新 user 优先 | compact 留 tail + 结构化摘要 + tool 落盘；摘要不压过本条用户话 |
| [005](./005-tool-loop-drift.md) | 工具空转与目标漂移 | 部分缓解 | 同 URL 死循环 fetch；意图展示≠重写工具调用 |

相关能力（非 bug 单）：本地 `/usage` 用量统计（`.project/usage/`，提示符显模型）；SWE-bench Lite 评测（`python -m evals.swebench`）。

---

## 四者怎么串起来

```text
启动会话边界 ──► 003 Resume（默认不灌旧论文）
每轮怎么拼 prompt ──► 002 缓存分层（static 稳、动态进 ephemeral）
长了怎么压上下文 ──► 004 compact（摘要+tail+落盘+最新 user）
模型跟不跟任务 ──► 001 偏移（todo / 话题 / 打断）
工具空转 / 检索漂移 ──► 005（重复调用 · 手段取代目的 · 意图展示）
```

| 用户痛点 | 主要文档 | 004 有没有帮到 |
|----------|----------|----------------|
| 重启又跟旧论文 | **003** | 无关 |
| 账单命中率低 | **002** | 略有（时间改分钟，利于 `if_unchanged`） |
| compact 后跑偏、忘路径 | **001-B / 004** | **有**（模板 + tail + persist + 最新 user 置顶） |
| todo 表和进度不一致 | **001-A** | 几乎无（靠 todos.json + 注入） |
| Ctrl+C 后 400 | **001-C** | 无关（靠 repair / undo） |
| 同一 fetch 刷屏、搜着搜着偏题 | **005** | 间接（大结果易触发 compact；主因是循环与收口） |

防偏移和省缓存**不是二选一**：动态内容放 ephemeral（002），模型仍看得见 todos（001）。

---

## 已落地（按主题）

| 主题 | 做了什么 | 文档 |
|------|----------|------|
| Todo 真相 | 每轮注入全表、3 轮 reminder、Rich Tasks、磁盘持久化 | 001-A |
| 本条用户意图 | `latest_user_query` 进 ephemeral | 001-B |
| 打断 / orphan tool | repair + abort 回滚 | 001-C |
| 缓存分层 | static / dynamic / ephemeral + `if_unchanged` | 002 |
| 默认全新会话 | `/clear` 全清；resume opt-in | 003 |
| 压缩保真 | compact 留 5 条 tail；六段摘要；micro 落盘；时间分钟级；**最新 user 覆盖摘要旧目标**；`agent/compact/` 模块化 | 004 |
| 用量可见 | `/usage` 日/周/月/年；提示符 `[model]` | （功能） |
| 工具空转 | RepeatGuard；工具 UI 摘要；调工具前展示同轮 text 意图 | 005 |

---

## 仍可商量（有痛点再做）

按「你现在最常撞到什么」选，不按编号强制顺序：

| 候选 | 痛点 | 大致做法 | 关联 |
|------|------|----------|------|
| ~~① compact 不压过最新用户话~~ | ~~摘要里旧目标绑架本轮~~ | **已做**：compact 末尾强制 `[Current user request]` | 001-B、004 |
| **② snip / 预热压缩** | >50 条硬切；只靠 50KB 才 compact | 语义边界 snip；或 soft limit 提前瘦身 | 004 |
| **③ 解释模式** | 问「为什么偏移」仍去改文件 | 检测 meta 问句 → 本轮禁 write/edit | 001-B |
| **④ 多 agent 隔离** | 同 cwd 共享 `.project/` | worktree 约定或 `HARNESS_PROJECT_DIR` | 003 |
| **⑤ memory 写回** | 用户纠正不进 `.memory/` | compact/纠正时 append constraints | 004 |
| **⑥ 缓存再抠** | 长任务真实命中仍波动 | slim ephemeral；少频繁换模型 | 002 |
| **⑦ 工具空转收口** | 同 URL 死循环、搜完不答 | 默认 max_rounds；失败黑名单；收口提醒 | 005 |

**① 已落地。** ⑤/⑦ 与长检索体感强相关时可优先。

---

## 文档约定

每条记录尽量含：现象 → 背景 → 根因 → 已改 → 为何这么改 → 相关文件 → 仍观察。  
状态用语：`已实施` / `部分缓解` / `仍观察`（避免写死 Phase 路线图）。
