# 本轮改动总览（2026-07-07）

> 起因：agent `/clear` + 换模型后仍跟旧「论文 8 章」任务；中断后 400；缓存命中率低。
> 目标：对齐 Claude Code / OpenCode 的 resume 边界，把通用 agent 与长期项目解耦。

---

## 一、问题诊断（写入 `docs/bugs/`）

| 编号 | 问题 | 状态 |
|------|------|------|
| [001](./bugs/001-todo-drift.md) | Agent 偏移：任务表（A）· 话题/目标（B）· 会话/工具链（C）三类 | A 类 v1 已修复；B/C 部分缓解 |
| [002](./bugs/002-prompt-cache-vs-dynamic-context.md) | API 缓存命中率 ~0%：动态字段写进 static | Phase 1 已实施 |
| [003](./bugs/003-resume-opt-in.md) | Resume 默认灌论文 + 空 session 自动 bootstrap transcript | 已实施 OpenCode 模式 |

---

## 二、改动清单

### 1. Resume 改成 OpenCode 模式（默认全新，opt-in 续）

**`harness/project/session_store.py`**
- 新增 `continue_session_on_startup()` —— `HARNESS_CONTINUE_SESSION=1` 才重启续 session（默认 off）
- 新增 `bootstrap_from_transcript_enabled()` —— `HARNESS_BOOTSTRAP_TRANSCRIPT=1` 才从 transcript 引导（默认 off）
- `bootstrap_session()` 默认返回 `[]`，不再自动 load session.jsonl / 引导 transcript
- `format_session_line()` 区分 OpenCode 模式文案

**`harness/project/tools.py`**
- `run_project_clear(clear_project=True)` —— **`/clear` 默认全清** session + todos + state.json
- `/clear session` 走 `clear_project=False`，只清对话保留论文表

**`harness/cli.py`**
- `/clear` 解析改为：`sub in ("session","chat","history")` 才走轻量版，否则全清
- `/help` 文案更新为 OpenCode 模式说明
- 启动 auto-inject thesis 仅在 `HARNESS_AUTO_RESUME=project` 时触发

**`harness/prompts/sections.py`**
- 删 static system 里的 `Long thesis/report workflows: load_skill(thesis-writing), then /resume project`
- 改为通用：「Specialized workflows opt-in via load_skill; long-running project context is never injected automatically」

**`harness/project/resume.py`**
- `format_resume_status()` 文案改中文 + OpenCode 模式说明
- `_continue_flag()` 显示 `HARNESS_CONTINUE_SESSION` 状态
- `inject_project_context` / `project_context_message` 全改中文

### 2. 中断 + 回滚（B/C 类偏移）

**`harness/ui/interrupt_listener.py`**（新增）
- SIGINT + Esc 监听，停 in-flight turn

**`harness/project/session_undo.py`**（新增）
- `abort_inflight_turn()` —— 回滚 user + 部分 tool 消息
- `undo_last_turn()` —— 撤销最近一轮
- `resolve_turn_start()` —— compact 后修 stale `turn_start`
- `_SKIP_PREFIXES` 包含 `[Session resumed]` / `[Resume context]` 不参与回滚

**`harness/ui/prompt_input.py`**（新增）
- 中断后重做 query 输入

**`harness/messages/repair.py`**（新增）
- 修复 orphan `tool_use` → API 400
- `repair_tool_pairing()` 在 `loop.py` 与 CLI 启动调用

### 3. 缓存分层（002）

**`harness/prompts/`**（新增模块，替换旧 `harness/prompts.py`）
- `static.py` —— 不变的 identity / tools / workspace / skills
- `dynamic.py` —— 每轮变的 todos / latest_user_query / time
- `ephemeral.py` —— session context、`if_unchanged` 策略
- `sections.py` —— PROMPT_SECTIONS 模板

**`harness/usage.py`**（新增）
- `cache_read_input_tokens` = hit, `input_tokens` = miss 解析

**`scripts/run_cache_experiment.py`** + `harness/prompts/cache_experiment.py`
- 模拟 + live 验证缓存策略

### 4. Todo 系统（001 A 类）

**`harness/todos/`**（新增模块）
- `state.py` —— `_CURRENT` 内存 + `.project/todos.json` 持久化
- `format.py` —— `format_todos_for_prompt` / `_for_cli` / `format_todos_tool_result` / `format_todo_reminder` / `format_todos_welcome_line`（全中文化）
- `schema.py` —— TodoWrite 工具 schema（only one in_progress 纪律）
- `__init__.py` 导出

**`harness/loop.py`**
- 每 LLM 回合无 `todo_write` → `note_llm_round_without_todo_update()`
- 每 3 轮 reminder 带完整列表
- `had_todo_write` 跟踪

**`harness/tools/registry.py`**
- `todo_write` tool 注册 + 完整 description

### 5. Bug 修复

| 问题 | 位置 | 修复 |
|------|------|------|
| `/model` 打开 mode picker | `cli.py` `_match_cli_command()` | 改成精确匹配，加测试 |
| `WORKDIR` NameError | `dynamic.py`, `compact.py` | 加 import |
| `checkpoint_history` UnboundLocalError | `cli.py` `run_cli()` | 去掉 inner import |
| `bootstrap_mcp_servers` 缺失 | `cli.py` | 恢复 import |
| Stale `turn_start` after compact | `session_undo.py` | `resolve_turn_start()` |

### 6. UI / 模式 / 模型选择

**`harness/ui/welcome.py`** —— Rich Session 面板，中文化（已恢复 / Session / Tasks 行）
**`harness/ui/model_picker.py`** + `mode_picker.py` + `terminal_menu.py` —— ↑↓ 选择器
**`harness/modes/`** —— 模式注册表 + runtime
**`harness/agents/`** —— typed subagent + per-role model binding（`config/agents.json`）
**`harness/agent/cancel.py`** —— 取消信号
**`harness/messages/sanitize.py`** —— 消息清洗

### 7. 测试（`tests/`）

| 文件 | 覆盖 |
|------|------|
| `test_resume.py` | OpenCode bootstrap / clear / inject marker / env opt-in |
| `test_cli_commands.py` | `/model` 不再误开 mode picker |
| `test_session_undo.py` | 中断回滚 / orphan 跳过 / truncate |
| `test_message_repair.py` | orphan tool_use 修复 |
| `test_dynamic_prompt.py` | dynamic 字段含 WORKDIR / latest_user_query |
| `test_usage.py` | 缓存命中解析 |

**22 个用例全过。**

---

## 三、用户视角的行为变化

### 之前
```text
python main.py → 自动 load session.jsonl + 自动灌论文 8 章
/clear         → 清对话，论文表留着 → agent 仍跟旧任务
两个 agent 并行 → 共享 .project/todos.json → 互相覆盖
```

### 现在（OpenCode 模式，默认）
```text
python main.py → 全新对话（不读盘，不灌论文）
/clear         → 一次清干净 session + todos + state.json
/clear session → 只清对话，保留论文表
/resume project → 显式注入论文上下文
两个 agent 并行 → 仍共享 .project/（建议用 git worktree 隔离）
```

### 想恢复旧行为
```bash
HARNESS_CONTINUE_SESSION=1    # 重启续 session（Claude Code -c 风格）
HARNESS_BOOTSTRAP_TRANSCRIPT=1 # 空 session 时从 transcript 引导（旧兜底）
HARNESS_AUTO_RESUME=project    # 启动自动注入 thesis（旧默认，不推荐）
HARNESS_WELCOME_PROJECT=1      # Welcome 显示章节行
```

---

## 四、当时仍观察（不是路线图）

| 项 | 说明 |
|----|------|
| 多 agent 并行的 cwd 分桶 | `.project/` 仍按 cwd 共享；可用 git worktree 隔离 |
| 001 B 类（compact 摘要压过最新 user 意图） | 仅 focus 注入缓解 |
| 子 agent 共享 todo | `task` 子 agent 无 todo_write；协作可用 `.tasks/` |
| thesis `current_chapter` 脏数据 | 可用 `/clear` 或手动修正 |

---

## 五、相关文件锚点

```text
docs/bugs/001-todo-drift.md
docs/bugs/002-prompt-cache-vs-dynamic-context.md
docs/bugs/003-resume-opt-in.md
docs/bugs/README.md

harness/cli.py
harness/loop.py
harness/project/{resume,session_store,state,tools,transcript,session_undo}.py
harness/prompts/{static,dynamic,ephemeral,sections,cache_experiment}.py
harness/todos/{state,format,schema}.py
harness/messages/{repair,sanitize}.py
harness/agents/{registry,runner,schema}.py
harness/modes/{registry,runtime}.py
harness/ui/{welcome,interrupt_listener,prompt_input,model_picker,mode_picker,terminal_menu}.py
harness/usage.py
harness/agent/cancel.py

tests/test_{resume,cli_commands,session_undo,message_repair,dynamic_prompt,usage}.py

scripts/run_cache_experiment.py
config/{agents,modes,modes.example}.json
```
