# 评测（mini-eval / SWE-bench）

本仓库有两套评测，目的不同：

| 套件 | 命令 | 评什么 | 要 API 吗 |
|------|------|--------|-----------|
| **mini-eval** | `python -m evals` | harness 基础设施是否坏了 | 默认不要 |
| **mini-eval live** | `python -m evals --live` | 真 LLM 能否听话、会调 read_file | 要 |
| **SWE-bench Lite** | `python -m evals.swebench --limit 1` | 端到端改代码出 patch | 要 |

结果目录：`evals/results/`（gitignore）。

---

## mini-eval 在评什么

**不是**「agent 聪不聪明」，**不是**像 Pu Keyang 检索那种任务质量分。  
它是 **改 harness 后的回归体检**：权限、模式、工具注册、压缩、loop 接线。

### 六类 case（`evals/cases/`）

| 类别 | 测什么 | 方式 |
|------|--------|------|
| `permissions` | deny-list、危险 bash 确认、路径逃逸、MCP destructive | 直接调 `permission_hook` |
| `modes` | plan 藏 write/bash；orchestrate 开 task | 切 mode 看 `get_tool_pool()` |
| `tools` / `mcp` | schema↔handler 对齐、mcp.json 配置、启动告警过滤 | 静态检查 |
| `compact` | 最新 user、micro_compact 落盘 | 构造假 messages |
| `simulated` | mock LLM 跑真 `agent_loop`（bash 成功 / sudo 被拒） | 无 API |
| `live` | 真模型 PONG、read README | 要 `--live` + key |

**未覆盖**（在 `tests/` 里）：lookup mode、RepeatGuard、`/resume` 切换删除。

### 打分

```text
score = pass / (pass + fail) × 100%
```

`skip` 和 `warn` **不进分母**。`warn` 用于记录已知 gap（如 plan 模式未 gate `mcp__*`）。

### 三层思路

```text
第 1 层：单点断言（permissions / modes / tools / compact）
第 2 层：模拟 loop（simulated）— 假 LLM 按剧本调工具
第 3 层：真 LLM 冒烟（live，可选）
```

---

## SWE-bench Lite

```sh
pip install -r requirements-eval.txt
python -m evals.swebench --limit 1
python -m evals.swebench --limit 1 --eval   # 需 Docker；官方 resolve 打分
```

克隆目标仓库 → 本 harness 跑 agent → 产出 patch。更接近「解题能力」，更重、依赖网络/Docker。

---

## 相关文件

```text
evals/runner.py          # 入口聚合
evals/cases/*.py         # 各 case 模块
evals/report.py          # 终端报告 + latest.json
evals/swebench/          # SWE-bench 流水线
requirements-eval.txt    # 可选依赖（datasets/pyarrow）
```
