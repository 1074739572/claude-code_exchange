# 本轮改动总览（2026-07-12）

> 接续 [2026-07-07](./CHANGELOG-2026-07-07.md)：会话与 todos 分桶、工具空转护栏、评测套件、resume UX。

---

## 一、问题诊断（写入 `docs/bugs/`）

| 编号 | 问题 | 状态 |
|------|------|------|
| [003](./bugs/003-resume-opt-in.md) | 多会话 + todos 跟 session；`/resume N` 切换 | 已实施 |
| [005](./bugs/005-tool-loop-drift.md) | 同 URL 死循环；找到仍续爬；**失败仍换 URL / compact 套娃** | 部分缓解 |

---

## 二、改动清单

### 1. Session 分桶（todos 跟会话）

**`harness/project/session_registry.py`**（新增）
- `.project/sessions/<id>/` 布局
- `active_session.json` 指针
- 旧版扁平 `session.jsonl` / `todos.json` 启动迁移

**`harness/project/session_store.py`**
- 读写落到 session 目录
- `clear` 结束当前 id、保留旧目录

**`harness/todos/state.py`**
- `todos.json` → `sessions/<id>/todos.json`

**`state.json`（B 层）** 不变：单槽长任务，`/resume project` opt-in。

### 2. `/resume` UX

**`harness/project/resume.py`**
- `/resume` — 精简列表（序号 + 标题 + 创建时间）
- `/resume <N>` 或 `/resume <标题>` — 切换会话，显示最后一条预览
- `/resume delete <N>` — 删会话目录
- `/resume delete project` — 删 `state.json`

### 3. 工具空转（005）

| 项 | 位置 |
|----|------|
| RepeatGuard（同参连续 N 次拦截） | `harness/agent/repeat_guard.py` |
| LookupGuard（lookup 预算 / 无效结果 / host 黑名单） | `harness/agent/lookup_guard.py` · `loop.py` |
| micro_compact 防 persisted 嵌套 | `harness/agent/compact/persist.py` · `layers.py` |
| MCP / dispatch 超时温和返回 | `harness/mcp/client.py` · `tools/dispatch.py` |
| Lookup mode 自动约束 | `harness/prompts/lookup.py` · `hooks.py` · `cli.py` |
| 空回复 nudge（thinking-only → 强制 text） | `harness/messages/blocks.py` · `loop.py` |

### 3b. 本地 RAG 仿写串联

| 项 | 位置 |
|----|------|
| writing_mode 检测 + 约束 | `harness/prompts/writing.py` · `hooks.py` |
| 自动 `rag_index`（files/） | `harness/rag/bootstrap.py` · `cli.py` |
| WritingGuard（写 output 前须 rag_search） | `harness/agent/writing_guard.py` · `loop.py` |
| 检索结果截断 | `harness/rag/tools.py`（`HARNESS_RAG_HIT_CHARS`） |
| write 子 agent 加 rag_search | `config/agents.json` |
| 文档 | [rag.md](./rag.md) · `evals/rag/fixtures/tiny_corpus/` |

证据会话见 [005-tool-loop-drift.md](./bugs/005-tool-loop-drift.md)。

### 4. 评测套件

| 命令 | 说明 |
|------|------|
| `python -m evals` | 本地回归（permissions / modes / tools / compact / simulated） |
| `python -m evals --live` | 可选真 LLM 冒烟 |
| `python -m evals.swebench` | SWE-bench Lite 流水线 |

详见 [evals.md](./evals.md)。

### 5. 测试

| 文件 | 覆盖 |
|------|------|
| `tests/test_session_scoped_todos.py` | session 目录、todos 隔离、迁移 |
| `tests/test_lookup_mode.py` | lookup 关键词检测与约束注入 |
| `tests/test_repeat_guard.py` | 重复调用拦截 |
| `tests/test_lookup_guard.py` | LookupGuard 预算/无效结果/host 黑名单 |
| `tests/test_lookup_guard_loop.py` | mock loop 集成 |
| `tests/test_compact.py` | micro_compact 防 persisted 嵌套 |


---

## 三、用户视角的行为变化

### 之前
```text
.project/session.jsonl + .project/todos.json   # 扁平，并行 agent 易覆盖
/resume                                        # 长状态 dump
```

### 现在
```text
.project/sessions/<id>/session.jsonl + todos.json
/resume              # 短列表
/resume 2            # 切到第 2 个会话
/resume delete 1     # 删列表中的会话
查找类问题           # [lookup mode] + LookupGuard 硬拦无效 fetch
```

---

## 四、相关文件锚点

```text
docs/README.md
docs/evals.md
docs/bugs/003-resume-opt-in.md
docs/bugs/005-tool-loop-drift.md

harness/project/session_registry.py
harness/project/session_store.py
harness/project/resume.py
harness/todos/state.py
harness/prompts/lookup.py
harness/agent/repeat_guard.py
harness/agent/lookup_guard.py
harness/agent/compact/persist.py

evals/
tests/test_session_scoped_todos.py
tests/test_lookup_mode.py
tests/test_repeat_guard.py
tests/test_lookup_guard.py
tests/test_lookup_guard_loop.py
tests/test_compact.py
```
