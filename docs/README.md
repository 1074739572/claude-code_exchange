# 文档索引

本目录记录 **improved_harness** 的设计取舍、踩坑修复与阶段性改动。  
用户向总览见 [README.md](../README.md)；模块职责见 [ARCHITECTURE.md](../ARCHITECTURE.md)。

---

## 快速导航

| 你想了解… | 去看 |
|-----------|------|
| 项目是什么、怎么跑 | [README.md](../README.md) |
| 模块怎么拆、数据落哪 | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| 问题编号与关联关系 | [bugs/README.md](./bugs/README.md) |
| 本地能力回归怎么评 | [evals.md](./evals.md) |
| 2026-07-07 大改总览 | [CHANGELOG-2026-07-07.md](./CHANGELOG-2026-07-07.md) |
| 2026-07-12 会话 / lookup / 评测 | [CHANGELOG-2026-07-12.md](./CHANGELOG-2026-07-12.md) |

---

## Bug & 改进记录（`bugs/`）

按编号记录「现象 → 根因 → 改了什么 → 仍观察」。**不是路线图**。

| ID | 标题 | 状态 |
|----|------|------|
| [001](./bugs/001-todo-drift.md) | Agent 偏移（任务表 · 话题 · 会话） | A 已修；B/C 大部分已修 |
| [002](./bugs/002-prompt-cache-vs-dynamic-context.md) | Prompt 缓存命中 | 分层已落地 |
| [003](./bugs/003-resume-opt-in.md) | Resume OpenCode 模式 | 已实施 |
| [004](./bugs/004-context-compaction.md) | 上下文压缩丢信息 | Phase 1 + 最新 user 优先 |
| [005](./bugs/005-tool-loop-drift.md) | 工具空转与目标漂移 | 部分缓解（RepeatGuard · Lookup mode） |

五条线的关系见 [bugs/README.md](./bugs/README.md) 里的「四者怎么串起来」图。

---

## 文档约定

每条 bug 记录尽量包含：

1. **现象** — 用户看到什么  
2. **根因** — harness 哪一层出了问题  
3. **已改** — 代码锚点与行为变化  
4. **仍观察** — 未承诺、有痛点再做  

状态用语：`已实施` / `部分缓解` / `仍观察`（避免写死 Phase 路线图）。

---

## 运行时数据（与文档交叉引用）

```text
.project/
  active_session.json
  sessions/<id>/
    session.jsonl      # 对话
    session.meta.json  # 标题 / 时间
    todos.json         # 本会话 todo（A 层）
  state.json           # 长任务档案（B 层，论文章节等）
  usage/               # token 流水
```

- **A（会话 + todos）**：跟 session；`/clear` 结束当前 id，旧目录保留。  
- **B（state.json）**：单槽长任务；`/resume project` 显式注入；`/clear` 默认删除。

详见 [003-resume-opt-in.md](./bugs/003-resume-opt-in.md)。
