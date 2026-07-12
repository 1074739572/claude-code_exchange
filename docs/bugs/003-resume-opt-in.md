# 003 — Resume 改成 OpenCode 模式（默认全新，opt-in 续）

**状态：** 已实施（2026-07）  
**关联：** [001 偏移](./001-todo-drift.md)（少自动灌论文 → 少 B 类跑偏）· [002 缓存](./002-prompt-cache-vs-dynamic-context.md) · [004 压缩](./004-context-compaction.md)（长跑保真，与启动边界正交）

---

## 问题

`/clear` + 换模型后，agent 仍跟旧 **论文 8 章任务**，原因：

1. 启动时 **自动注入** `[Session resumed] … Continue chapter X`
2. `/clear` **保留** `.project/state.json`（论文表留着）
3. 空 session 时 **自动从 `.transcripts/` bootstrap**，旧对话被灌回
4. static system 写死 `Thesis rewrite … resumes on restart`

每次都得 `/clear all` 才干净 → 太麻烦。

---

## 成熟项目怎么做

| 产品 | Resume 行为 |
|------|-------------|
| **Claude Code** | `claude -c` **显式续对话**；默认 `claude` 就是新对话；Task 托盘独立 |
| **OpenCode** | 新 session → 新 todo（SQLite FK cascade）；项目规则在 AGENTS.md，**opt-in** |
| **Gemini CLI** | session 文档 + 可选 `.tracker/`；Plan 模式单独 workflow |

共同点：**对话恢复 ≠ 业务项目恢复**；要续就显式说，否则默认全新。

---

## 我们的方案：默认 OpenCode，opt-in Claude Code

### 默认行为（无需任何 env）

| 动作 | 效果 |
|------|------|
| `python main.py` 启动 | **全新对话**（不自动 load `session.jsonl`、不 bootstrap transcript） |
| 启动 banner | 显示「OpenCode 模式」；磁盘上若有旧 session，提示如何续 |
| `/clear` | **一次清干净**：session + todos + state.json |
| `/clear session` | 轻量版：只清对话，保留 state.json |
| `/resume` | 列出会话（序号 + 标题 + 创建时间）+ 长任务一行 |
| `/resume <N>` 或 `/resume <标题>` | **切换**到该会话，加载 messages/todos，显示最后一条预览 |
| `/resume delete <N>` | 删除列表中的会话目录 |
| `/resume delete project` | 删除长任务 `state.json` |
| `/resume project` | **opt-in** 注入 `[Resume context]` 一条 user 消息 |
| static system | **不再提** thesis；只说「特殊工作流用 load_skill，长项目不自动注入」 |

### 想恢复旧行为（重启续 session）

```bash
HARNESS_CONTINUE_SESSION=1     # 重启时自动 load session.jsonl（Claude Code -c 风格）
HARNESS_BOOTSTRAP_TRANSCRIPT=1 # session.jsonl 也没有时，从 .transcripts/ 引导（最旧的兜底）
HARNESS_AUTO_RESUME=project    # 启动时再自动注入 thesis（不推荐，仅兼容老脚本）
HARNESS_WELCOME_PROJECT=1      # Welcome 显示章节行
```

---

## 代码锚点

| 文件 | 改动 |
|------|------|
| `harness/project/session_registry.py` | `sessions/<id>/`、active 指针、legacy 迁移、会话列表 |
| `harness/project/session_store.py` | 读写落到 session 目录；`bootstrap` 默认新 session；`clear` 换 id 保留旧目录 |
| `harness/todos/state.py` | `todos.json` → `sessions/<id>/todos.json` |
| `harness/project/tools.py` | `/clear` 文案与「保留旧 session todos」 |
| `harness/project/resume.py` | 区分 session 列表 vs `state.json` 长任务 |
| `harness/project/session_store.py` | `continue_session_on_startup()`、`bootstrap_from_transcript_enabled()`；`bootstrap_session` 默认返回 `[]`；`format_session_line` 区分模式 |
| `harness/project/tools.py` | `run_project_clear(clear_project=True)` 默认全清；`/clear session` 反向开关 |
| `harness/cli.py` | `/clear` 解析；首条用户话写入 session title |
| `harness/prompts/sections.py` | 删 thesis 一句，改为通用「opt-in via load_skill」 |
| `harness/project/resume.py` | `format_resume_status` 文案改 OpenCode；新增 `_continue_flag()` |

---

## 用户用法

```text
# 通用 agent（默认就是 OpenCode 全新）
python main.py
> 写实施方案 …

# 看有哪些会话
/resume

# 切到第 2 个会话（或 /resume 你现在的任务是什么）
/resume 2

# 想续论文（显式）
/resume project
> 继续写第 3 章 …

# 想清掉一切换题
/clear              # 默认就全清

# 只清对话，留论文表
/clear session

# 删某个旧会话
/resume delete 3

# 删长任务档案
/resume delete project

# 想让重启自动续对话
$env:HARNESS_CONTINUE_SESSION=1
python main.py
```

---

## 存储分层（2026-07 起：todos 跟 session）

```text
.project/
  active_session.json              # 当前会话 id
  sessions/<id>/
    session.jsonl                  # 对话
    session.meta.json              # 标题 / 时间 / 持久化游标
    todos.json                     # A：本会话任务（1 session ↔ 1 todos）
  state.json                       # B：长任务档案（论文章节），单槽，opt-in
  usage/                           # 用量（跨 clear 保留）
```

| 层 | 文件 | `/clear` | 换 session |
|----|------|----------|------------|
| 对话 + todos (A) | `sessions/<id>/` | 结束当前 id，**目录保留**（含 todos） | 新 id 空 todos；旧 todos 不跟过来 |
| 长任务 (B) | `state.json` | 默认删除；`/clear session` 保留 | **不动**；`project_init` 会整份覆盖 |

`/resume`：列会话目录 + 当前 todos；`/resume project`：只注入 B，不改 A。  
旧版扁平 `.project/session.jsonl` / `todos.json` 启动时迁移进 `sessions/<id>/`。


| 系统 | 谁看得见 | 子 agent 是否共享 |
|------|----------|-------------------|
| `todo_write`（session todos） | 主 agent 动态 prompt | ❌ `task` 子 agent 隔离，无 todo_write 工具；todos 在 `sessions/<id>/todos.json` |
| `.tasks/` 板 | Lead + teammate | ✅ 队友协作共享，靠磁盘 + claim_task |
| `state.json` 论文章节 | `project_*` / `/resume project` | ❌ 子 agent 默认不看；与 session **分开**，单槽 |

子 agent（`harness/agents/runner.py`）从 `[{user: prompt}]` 起跑，看不到父 session 或 todos。  
队友（`spawn_teammate`）共享 `.tasks/`，不是 todos.json。  
`/clear` 清的是 **主 agent 的 session + todos + 论文项目表**，不影响队友的 `.tasks/`（那是另一个生命周期）。

---

## 测试

`tests/test_resume.py` — 验证默认 off、opt-in env、注入 marker、空 state。
