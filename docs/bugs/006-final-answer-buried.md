# 006 — 最终回答看不见（漏打 · 刷屏掩盖）

**状态：** 两档均已缓解  
**影响：** 多轮工具 / compact 之后，用户以为「没有总结」或「回答被盖住」  
**关联：** [001-C 打断/索引](./001-todo-drift.md) · [002 缓存](./002-prompt-cache-vs-dynamic-context.md) · [004 压缩](./004-context-compaction.md) · [005 工具空转](./005-tool-loop-drift.md)  
**证据：**
- **A（漏打）**：2026-07-15 上午修复 commit `4a21e20`；回归 `tests/test_print_turn_assistants.py`
- **B（刷屏）**：2026-07-15 下午会话（用户：「总结呢 / 回答又被掩盖」）；`.transcripts/transcript_1784101630.jsonl` 一带

同属「终答对用户不可见」，但根因不同，曾分开撞过两次。

---

## 两次现象对照

| | **A · 终答漏打（上次）** | **B · 终答被刷屏盖住（这次）** |
|--|--------------------------|--------------------------------|
| 用户体感 | 整轮结束屏幕是空的，没有 Assistant 面板 | 面板其实有，但上面一百行 `hit=` / compact，找不到 |
| 模型是否写进 history | **写了** | **写了** |
| `print_turn_assistants` | **没打出来**（切片越界） | 打出来了 |
| 典型触发 | 本回合中途 auto compact，历史变短 | 长工具链 + 每轮 LLM 打 cache 行 |

---

## A — compact 后 `turn_start` 失效（上次原因）

### 现象

长任务触发 `compact_history` → `messages[:]` 被换成更短列表。CLI 里轮初记下的：

```python
turn_start = len(history)   # 例如 48
```

compact 后 `len(history)` 可能只有十几。回合结束：

```python
print_turn_assistants(history, turn_start=48)
# 旧实现：for msg in messages[48:]  → 空切片 → UI 空白
```

用户侧：**答案在 session 里，终端零终答。**

### 根因

`turn_start` 是 **compact 前** 的列表下标；压缩重写历史后变成 stale index（与 001-C 里 abort 用的 `resolve_turn_start` 同类问题）。

### 已改（2026-07-15 · `4a21e20`）

| 项 | 行为 | 位置 |
|----|------|------|
| 打印前解析 | `resolve_turn_start(messages, turn_start)` 对齐**当前**用户轮 | `harness/cli.py` |
| docstring | 写明 compact 缩短 history 时不得用旧下标硬切 | 同上 |
| 回归测试 | stale `turn_start=48` + 短 history 仍打印终答 | `tests/test_print_turn_assistants.py` |

```text
compact 重写 messages → len 变短
print_turn_assistants 必须 resolve_turn_start，不能 messages[旧 turn_start:]
```

---

## B — 诊断行刷屏盖住面板（这次原因）

### 现象

```text
● read_file  harness/loop.py
   hit=9088 miss=6154 (60%) out=143
● read_file  harness/llm.py
   hit=10112 miss=2067 (83%) out=217
…（十几轮，每轮一行 hit/miss）
  [compact] transcript saved: …\transcript_….jsonl
› 不是 你的总结呢 我怎么又没看到
…
╭─ Assistant ─╮
│ （其实打过了，被埋在上面） │
╰─────────────╯
```

另有一种**时机错觉**：工具链未结束时只有 `›` 意图句，终答面板要等无 `tool_use` 的回合才由 `print_turn_assistants` 打出。

### 根因

1. **每轮 LLM 默认打印** `[cache] hit=… miss=…`（`llm._log_cache_usage`）——本为调 002 缓存，却当 UI 噪音。  
2. **compact 默认 print** 落盘路径——对日常用户无用。  
3. **与 005 叠加** — 步骤行已经很长，再叠诊断行，面板更靠下。

用量仍进 `.project/usage/`（`/usage`）——**记账**与**刷屏**应拆开。

### 已改（2026-07-15 下午）

| 项 | 行为 | 位置 |
|----|------|------|
| cache 行默认静默 | 仍 `record_usage`；仅 `HARNESS_VERBOSE=1` 打印 | `harness/llm.py` |
| compact 路径默认静默 | transcript 仍写 `.transcripts/`；verbose 才 print | `harness/agent/compact/pipeline.py` |
| 步骤 UI 保留 | `›` + `●` + 错误 / `Changed files` | `renderer.py` · `tool_display.py` |
| 测试 | 默认不 muted；verbose 才 muted | `tests/test_llm_cache_log.py` |

```sh
set HARNESS_VERBOSE=1   # 需要看 cache / compact 路径时
python main.py
```

---

## 通道分工（避免再混）

| 通道 | 给谁 | 备注 |
|------|------|------|
| `●` / `›` | 人 | 步骤，保留 |
| `[cache]` / `[compact] transcript` | 调试 | 默认关；verbose 开 |
| Assistant Panel | 人 | `print_turn_assistants`；须能打出且不被淹 |
| session.jsonl | 模型/归档 | A 案里「有历史无面板」即证据 |

---

## 为何拆成 A + B 仍放在 006

- 用户话术都是「怎么没看见回答 / 总结呢」。  
- A 是 **打印管道坏了**；B 是 **打印对了但噪音太大**。修 A 不解 B，修 B 不解 A。  
- 和 005（空转不停）不同：006 假定内容已有，卡在**对用户的可见交付**。

---

## 相关文件

```text
harness/cli.py                         # print_turn_assistants + resolve_turn_start
harness/project/session_undo.py        # resolve_turn_start
harness/llm.py                         # cache 静默
harness/agent/compact/pipeline.py      # compact 路径静默
harness/ui/renderer.py
tests/test_print_turn_assistants.py    # A
tests/test_llm_cache_log.py            # B
docs/CHANGELOG-2026-07-15.md
```

---

## 仍观察

| 项 | 说明 |
|----|------|
| 长 `›` 意图句 | 半成品总结塞进 intent，截断成一行，误以为答完了；可再议升格为面板 |
| compact 后催「再讲一遍」 | 摘要丢细节 → 属 004 |
| Panel 弱分隔 | 「本回合结论」标题是否要做，有抱怨再加 |

---

## C — loop 返回前未打印（2026-07-16）

### 现象

工具链很长或夹着 `[permission]` / 编码异常时，模型已把终答写入 history，但 CLI 在 `agent_loop` 返回后才 `print_turn_assistants`；中间一炸，用户以为「又吞了」。

### 已改

| 项 | 行为 | 位置 |
|----|------|------|
| loop 内打印 | 无 tool 的收口回合立刻 `emit_final_assistant` | `harness/loop.py` · `harness/ui/final_answer.py` |
| 防双打 | 消息标 `_ui_final_printed`；`print_turn_assistants` 跳过 | `harness/cli.py` |
