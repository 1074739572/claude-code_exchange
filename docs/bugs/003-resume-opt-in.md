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
| `/resume` | 看磁盘上 session + todos + 论文摘要（**只读**） |
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
| `harness/project/session_store.py` | `continue_session_on_startup()`、`bootstrap_from_transcript_enabled()`；`bootstrap_session` 默认返回 `[]`；`format_session_line` 区分模式 |
| `harness/project/tools.py` | `run_project_clear(clear_project=True)` 默认全清；`/clear session` 反向开关 |
| `harness/cli.py` | `/clear` 解析改为 `sub in ("session","chat","history")` 才保留项目 |
| `harness/prompts/sections.py` | 删 thesis 一句，改为通用「opt-in via load_skill」 |
| `harness/project/resume.py` | `format_resume_status` 文案改 OpenCode；新增 `_continue_flag()` |

---

## 用户用法

```text
# 通用 agent（默认就是 OpenCode 全新）
python main.py
> 写实施方案 …

# 想续论文（显式）
/resume project
> 继续写第 3 章 …

# 想清掉一切换题
/clear              # 默认就全清

# 只清对话，留论文表
/clear session

# 想让重启自动续对话
$env:HARNESS_CONTINUE_SESSION=1
python main.py
```

---

## 多子 agent / 队友协作

| 系统 | 谁看得见 | 子 agent 是否共享 |
|------|----------|-------------------|
| `todo_write`（session todos） | 主 agent 动态 prompt | ❌ `task` 子 agent 隔离，无 todo_write 工具 |
| `.tasks/` 板 | Lead + teammate | ✅ 队友协作共享，靠磁盘 + claim_task |
| `state.json` 论文章节 | `project_*` / `/resume project` | ❌ 子 agent 默认不看，除非 prompt 里写 |

子 agent（`harness/agents/runner.py`）从 `[{user: prompt}]` 起跑，看不到父 session 或 todos。  
队友（`spawn_teammate`）共享 `.tasks/`，不是 todos.json。  
`/clear` 清的是 **主 agent 的 session + todos + 论文项目表**，不影响队友的 `.tasks/`（那是另一个生命周期）。

---

## 测试

`tests/test_resume.py` — 验证默认 off、opt-in env、注入 marker、空 state。
