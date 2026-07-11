# Bug & 改进记录

本目录记录 `improved_harness` 在真实使用中发现的问题、根因，以及整条链路上的修复（不是最小 patch 备忘）。

每条记录建议包含：现象、背景、根因、改进、为何这么改、相关文件、遗留观察。

## 索引

| ID | 标题 | 状态 | 日期 |
|----|------|------|------|
| [001](./001-todo-drift.md) | Agent 偏移（任务表 · 话题 · 会话状态） | A 类 v1 已修复；B/C 部分已修复 | 2026-07 |
| [002](./002-prompt-cache-vs-dynamic-context.md) | API 缓存命中率优化（分层上下文 + 实验验证） | Phase 1 已实施 | 2026-07 |
| [003](./003-resume-opt-in.md) | Resume 改成 OpenCode 模式（默认全新，opt-in 续） | 已实施 | 2026-07 |
| [004](./004-context-compaction.md) | 上下文压缩丢信息（tail + 结构化摘要 + persist） | Phase 1 已实施 | 2026-07 |

总览与上游说明见仓库根目录 [README.md](../../README.md)。
