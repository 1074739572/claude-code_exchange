# Improved Harness

基于 [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 的 Agent Harness 改进版。

上游是一套「从零拆解 Claude Code 式 harness」的教学仓库；本仓库从其中的综合章 **`s20_comprehensive`**（单文件 `code.py`）出发，拆成可维护的包，并在真实使用中持续修问题、加能力。

本仓库远程：https://github.com/1074739572/claude-code_exchange

---

## 代码从哪来

| 项 | 说明 |
|----|------|
| 上游仓库 | https://github.com/shareAI-lab/learn-claude-code |
| 逻辑基线 | `s20_comprehensive/code.py`（约 2100 行单文件综合版） |
| 教学对应 | s01–s20：loop / tools / hooks / todo / subagent / skills / compact / memory / recovery / tasks / background / cron / teams / worktree / MCP |
| 本仓库做了什么 | 模块化拆包 + 多模型 / RAG / 会话与压缩 / UI 等工程化改进（见下表） |

克隆上游（对照用）：

```sh
git clone https://github.com/shareAI-lab/learn-claude-code
cd learn-claude-code
```

---

## 我们做了哪些改进

相对上游 `s20` 单文件版，以及后续在真实任务里踩坑后的修复：

### 结构与基础设施

| 改进 | 说明 |
|------|------|
| 包结构拆分 | 单文件 → `harness/` 按子系统拆包，便于测试与替换 |
| Skills 自包含 | 自带 `skills/`，不依赖上游仓库根目录 |
| MCP 双模式 | `RealMCPClient`（stdio）+ `MockMCPClient`；配置在 `config/mcp.json` |
| MCP 权限元数据 | 用 `destructive` 等元数据驱动确认，而不是按名字硬匹配 |
| 多模型 Provider | Anthropic + OpenAI 兼容路由；CLI `/model` 选择 |
| RAG 检索 | `harness/rag/`：文档切块、索引、工具侧检索 |

### 会话与任务（真实使用踩坑后）

| 改进 | 说明 | 记录 |
|------|------|------|
| Resume OpenCode 模式 | 默认全新会话；`/clear` 一次清干净；续项目需 `/resume project` 显式 opt-in | [003](docs/bugs/003-resume-opt-in.md) |
| Todo 持久化与提醒 | `.project/todos.json`；每轮注入；多轮无更新时 reminder | [001](docs/bugs/001-todo-drift.md) |
| 中断与回滚 | Esc / SIGINT 停当前轮；orphan `tool_use` 修复，避免 API 400 | [001](docs/bugs/001-todo-drift.md) |
| Prompt 缓存分层 | static / dynamic / ephemeral 分离，提高 cache hit | [002](docs/bugs/002-prompt-cache-vs-dynamic-context.md) |
| 上下文压缩 Phase 1 | compact 保留尾部；结构化摘要；micro_compact 落盘可恢复；时间默认分钟粒度 | [004](docs/bugs/004-context-compaction.md) |
| Compact 输入预算 | 按模型上下文自适应；识别 DeepSeek `30720` 等超限错误 | — |

### 交互与体验

| 改进 | 说明 |
|------|------|
| 欢迎页 / Session 面板 | Rich UI，中文状态行 |
| 模型 / 模式选择器 | 终端 ↑↓ 菜单 |
| 中文 CLI 文案 | `/help`、`/resume`、`/clear` 等 |
| 模式与子 Agent 配置 | `config/modes*.json`、`config/agents.json` |
| 本地用量统计 | `.project/usage/` 按日流水；`/usage` 日/周/月/年 + 字符柱；提示符显示当前模型 |

问题与取舍的详细说明在 [`docs/bugs/`](docs/bugs/README.md)，按编号记录「现象 → 根因 → 改了什么」。

后续改什么不写死路线图——有新痛点再一起商量，改完补一条 bug 记录即可。

---

## 目录结构

```
improved_harness/
├── main.py                 # CLI 入口
├── requirements.txt
├── .env.example
├── config/                 # mcp / agents / modes 配置
├── skills/                 # 内置技能
├── tests/                  # 单元测试
├── docs/
│   ├── bugs/               # 问题与改进记录（001–004…）
│   └── CHANGELOG-*.md      # 阶段性改动总览
├── scripts/                # 实验与文档构建脚本
└── harness/                # 核心包
    ├── loop.py             # agent 主循环
    ├── cli.py              # 交互式 CLI
    ├── settings.py         # 路径与常量
    ├── llm.py / models.py  # 调用与模型表
    ├── context.py          # 记忆等上下文
    ├── hooks.py            # Pre/Post tool hooks
    ├── skills_loader.py
    ├── tasks.py / worktree.py / usage.py
    ├── agent/              # compact/ + recovery / cancel / cron / background
    │   └── compact/        # sizing · messages · persist · layers · summarize · pipeline
    ├── prompts/            # static / dynamic / ephemeral
    ├── project/            # session / resume / clear / undo
    ├── todos/              # todo 状态与格式化
    ├── tools/              # filesystem / registry / dispatch
    ├── providers/          # Anthropic / OpenAI-compat
    ├── rag/                # 检索
    ├── mcp/                # MCP 客户端与池
    ├── teams/              # 多队友
    ├── modes/ / agents/    # 模式与 typed subagent
    ├── messages/           # repair / sanitize
    └── ui/                 # welcome / picker / interrupt
```

运行时落盘（相对工作目录 cwd）：

| 路径 | 内容 |
|------|------|
| `.project/` | session、todos、state、history |
| `.transcripts/` | compact 前完整备份 |
| `.memory/MEMORY.md` | 长期记忆 |
| `.tasks/` / `.mailboxes/` / `.worktrees/` | 任务图、队友邮箱、worktree |
| `.rag/` | RAG 索引与 chunks |

---

## 快速开始

```sh
cd improved_harness
cp .env.example .env          # 填入 API Key 与 MODEL_ID
pip install -r requirements.txt
python main.py
```

在**你的工作区目录**（cwd）跑 Agent；skills 从本包 `skills/` 加载；会话与任务状态写在 cwd 下的 `.project/` 等目录。

常用命令：`/help`、`/model`、`/usage`、`/clear`、`/resume`、`/resume project`。

提示符形如 `[qwen-max] >`。`/usage` 查看今日输入/输出/命中率（字符直方图）；`/usage week|month|year` 看历史。数据在 `.project/usage/`，`/clear` 不会删。

## MCP（可选插件）

`config/mcp.json` 已预置两个公用 server（启动时自动连接；成功静默，失败才告警）：

| 名字 | 作用 | 本机需要 |
|------|------|----------|
| **fetch** | 拉网页转 markdown | `pip install -r requirements.txt`（含 `mcp-server-fetch`） |
| **playwright** | 浏览器自动化 | 已装 **Node.js**（首次 `npx` 会拉包） |

连上后工具名形如 `mcp__fetch__fetch`、`mcp__playwright__…`。某个 server 缺依赖时只会在启动日志里报失败，不影响其它能力。不想用某个时，从 `mcp.json` 删掉对应条目即可。

---

## 与上游 s20 的对照（一眼）

| 项 | 上游 `s20_comprehensive/code.py` | 本仓库 |
|----|----------------------------------|--------|
| 结构 | 单文件 | `harness/` 分包 |
| Skills | 依赖仓库根 `skills/` | 自带 `skills/` |
| MCP | 多为 mock | mock + 真实 stdio |
| 模型 | 偏 Anthropic 教学默认 | 多 Provider + `/model` |
| 会话 | 教学向 | OpenCode 默认全新 + opt-in resume |
| 压缩 | 基础四层 | 尾部保留 + 结构化摘要 + tool 落盘 |

更细的模块职责见 [ARCHITECTURE.md](ARCHITECTURE.md)。
