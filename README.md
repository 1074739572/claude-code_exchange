# Improved Harness

基于 `s20_comprehensive` 的**模块化改进版** Agent Harness：同一套循环，拆成可维护的包结构，内置 skills，并预留真实 MCP 接入。

## 目录结构

```
improved_harness/
├── main.py                 # CLI 入口
├── requirements.txt
├── .env.example
├── config/
│   └── mcp.json            # MCP server 配置（stdio）
├── skills/                 # 内置技能（从仓库 skills/ 复制）
│   ├── agent-builder/
│   ├── mcp-builder/
│   ├── code-review/
│   └── pdf/
└── harness/                # 核心包
    ├── settings.py         # 路径、LLM 客户端、常量
    ├── loop.py             # agent_loop（主循环）
    ├── cli.py              # 交互式 CLI
    ├── hooks.py            # PreToolUse / PostToolUse / Stop
    ├── prompts.py          # system prompt 组装
    ├── context.py          # 记忆、MCP、队友状态
    ├── skills_loader.py    # scan_skills + load_skill
    ├── tasks.py            # 持久化任务图
    ├── worktree.py         # git worktree 隔离
    ├── tools/
    │   ├── filesystem.py   # bash / read / write / edit / glob
    │   ├── todo.py
    │   ├── dispatch.py
    │   └── registry.py     # 27 个内置工具 + handler 表
    ├── agent/
    │   ├── compact.py      # 四层压缩
    │   ├── recovery.py     # 429/529/max_tokens 恢复
    │   ├── background.py   # 慢 bash 后台执行
    │   ├── cron.py         # 定时任务
    │   └── subagent.py     # 一次性子 Agent
    ├── teams/
    │   ├── bus.py          # MessageBus
    │   ├── protocol.py     # plan/shutdown 协议
    │   └── teammate.py     # 持久队友线程
    └── mcp/
        ├── config.py       # 读取 config/mcp.json
        ├── base.py         # MockMCPClient
        ├── mock.py         # docs / deploy 教学 mock
        ├── client.py       # RealMCPClient（官方 SDK stdio）
        └── pool.py         # connect_mcp + assemble_tool_pool
```

## 快速开始

```sh
cd improved_harness
cp .env.example .env          # 填入 ANTHROPIC_API_KEY 和 MODEL_ID
pip install -r requirements.txt
python main.py
```

在**你的工作区目录**（`cwd`）运行 Agent；skills 从本包的 `skills/` 加载，任务/邮箱/worktree 状态写在 cwd 下的 `.tasks/`、`.mailboxes/` 等。

## 与 s20 单文件版的差异

| 项 | s20 `code.py` | improved_harness |
|----|---------------|------------------|
| 结构 | 单文件 ~2100 行 | 按子系统拆包 |
| Skills | 依赖仓库根 `skills/` | 自带 `skills/` |
| MCP | 仅 mock | mock + `config/mcp.json` 真实 stdio |
| 权限 | deploy 名字匹配 | 读 MCP `destructive` 元数据 |
| 启动 | 手动 connect | 可 `bootstrap_mcp_servers()` 预连 |

## 内置 Skills

| 名称 | 用途 |
|------|------|
| agent-builder | Agent 架构与子 Agent 模式 |
| mcp-builder | 搭建 MCP Server |
| code-review | 代码审查 |
| pdf | PDF 处理 |

Agent 在 system prompt 中看到目录，需要时用 `load_skill("mcp-builder")` 加载全文。

## 配置 MCP

编辑 `config/mcp.json`：

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:/your/workspace"]
    }
  }
}
```

启动时会自动连接；也可在对话中说 `connect_mcp docs` 连接 mock 服务器。

## 改进路线图

见 [ARCHITECTURE.md](ARCHITECTURE.md)。
