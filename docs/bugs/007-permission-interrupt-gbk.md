# 007 — 权限确认卡住 · Esc 退不出 · Windows GBK 崩

**状态：** 已缓解  
**影响：** `[permission] destructive command` / `Allow? [y/N]` 时按 Esc/Ctrl+C；或 bash 输出含非 GBK 字节  
**关联：** [001-C 打断](./001-todo-drift.md) · [005 漂移](./005-tool-loop-drift.md) · [006 终答](./006-final-answer-buried.md)  
**证据：** 2026-07-16 会话 — 用户让 agent 跑 Vanna，模型误开 `main.py` / `start cmd`；权限提示后 Esc 仍卡；随后 `UnicodeDecodeError: 'gbk' codec...`

---

## 现象

```text
[permission] destructive command
  cd … && python -c "… start cmd … run_cli() …"
  Allow? [y/N]
Stopping… (Esc or Ctrl+C)
Exception in thread Thread-… (_readerthread):
  UnicodeDecodeError: 'gbk' codec can't decode byte …
Interrupted — rolled back 28 message(s)
```

体感：**已经打断，但终端还挂着 / 报错刷屏**；回滚后也不敢再输入。

---

## 根因（三层）

| 层 | 机制 | 后果 |
|----|------|------|
| **权限** | `permission_hook` 用阻塞 `input()` | Esc 只置 cancel 标志，`input()` 仍等 Enter |
| **按键抢占** | `InterruptListener` 后台 `getch()` 吃掉任意键 | `y`/`n` 可能被吞；与 `input()` 抢 stdin |
| **编码** | `run_bash` `text=True` 无 encoding → Windows 默认 GBK | 工具输出非 GBK 时 reader 线程炸 |

另：`"rm "` 子串匹配可能误伤；嵌套 `python main.py` / `start cmd` / `run_cli()` 本不该当成「用户产品」去弹权限开新窗口。

---

## 已改

| 项 | 行为 | 位置 |
|----|------|------|
| 可取消权限 | `ask_allow()` 轮询 y/n/Esc；认 `is_cancelled` | `harness/ui/permission_prompt.py` |
| 暂停键轮询 | 权限期间 `pause_key_poll`；非中断键 `ungetch` | `harness/ui/interrupt_listener.py` |
| 取消即退出回合 | PreToolUse 拒绝且 cancel → `finalize` + return | `harness/loop.py` |
| 破坏性匹配 | 词边界 regex，减少误伤 | `harness/hooks.py` |
| 禁嵌套 agent | `main.py` / `run_cli` / `start cmd` 直接拒绝并说明 | `harness/hooks.py` |
| bash UTF-8 | `encoding="utf-8", errors="replace"` | `harness/tools/filesystem.py` |

---

## 相关：目标漂移（同会话）

用户配/跑 **Vanna**，选模型与数据后 agent 去读本仓库 `harness/cli.py`、`python main.py`。  
见 [005](./005-tool-loop-drift.md) 补充：goal stickiness + identity 写明「harness ≠ 用户产品」。

---

## 相关文件

```text
harness/ui/permission_prompt.py
harness/ui/interrupt_listener.py
harness/hooks.py
harness/tools/filesystem.py
harness/loop.py
harness/prompts/goal_stickiness.py
harness/prompts/sections.py
```
