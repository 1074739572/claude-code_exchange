# 004 — 上下文压缩与缓存前缀稳定性

**状态：** Phase 2 已实施：工具结果入场定型 + 检查点压缩（2026-07）
**关联：** [001 偏移 B/C](./001-todo-drift.md) · [002 缓存](./002-prompt-cache-vs-dynamic-context.md)（时间分钟级）· [003 Resume](./003-resume-opt-in.md)（正交：启动边界 vs 压上下文）

---

## 对 001 / 002 的影响（摘要）

| 目标 | 004 是否帮忙 |
|------|----------------|
| 少任务偏移（B：摘要绑架） | **有** — 六段模板 + 保留 tail 5 + **末尾 `[Current user request]` 覆盖摘要旧目标** |
| 少路径幻觉（C3：micro 硬删） | **有** — 落盘可 `read_file` |
| 提高缓存命中（002） | **显著** — 普通轮次不再改写旧消息，缓存前缀可随历史增长 |
| Resume 默认全新（003） | **无关** |

---

## 现象

长任务（读大文件、多轮 tool、写多章报告）进行到一半后，agent 开始：

- 忘记用户指定的样例路径、章节结构、交付格式
- 重复已做过的步骤，或跳到无关任务
- 对已读过的 docx / 大段 tool 输出答「没有上下文」

用户侧常见触发：对话估算 token 超过 `≈0.835 × context_window` 后触发 `compact_history`。旧实现还会在每次 LLM 调用前用 `micro_compact` 改写已经发送过的 tool 结果。
（旧行为：固定 50KB 字符硬限，web 任务过早压缩。）

---

## 背景

旧版 `prepare_context()` 在每轮 LLM 调用前按层压缩：

```
tool_result_budget → snip_compact → micro_compact → compact_history（若达到 token 阈值）
```

这既有信息完整性问题，也有缓存问题：

| 层级 | 设计意图 | 实际缺陷 |
|------|----------|----------|
| `compact_history` | 超限时 LLM 摘要 | **只留 1 条摘要**，无尾部消息（`reactive_compact` 才有 tail） |
| `micro_compact` | 旧 tool 结果瘦身 | **硬删**为 `[Earlier tool result compacted]`，无磁盘路径 |
| 逐轮调用 `micro_compact` | 渐进释放上下文 | 每轮可能重写更早的消息，破坏 DeepSeek 的精确前缀缓存 |
| 逐轮调用 `snip_compact` | 限制消息条数 | 达到 50 条后历史中段随轮次变化，持续制造冷启动 |
| `summarize_history` | 续作所需信息 | 自由文本 prompt，**无固定章节**，约束易丢 |
| `build_session_context` | 动态 ephemeral | `Current time` 精确到秒，**每轮都变**，破坏 `if_unchanged` 缓存 |

`reactive_compact`（API 报 prompt too long 时）已经做对：摘要 + `_keep_tail(5)`。`compact_history` 却没对齐。

---

## 根因（结构问题，不是模型「忘了」）

1. **主动压缩与被动压缩行为不一致** — 50KB 触发的 `compact_history` 比 overflow 触发的 `reactive_compact` 更激进，长任务更容易在「正常路径」丢上下文。
2. **micro 层删除不可恢复** — `tool_result_budget` 大输出会 `persist_large_output` 写盘；`micro_compact` 却直接覆盖字符串，agent 无法 `read_file` 找回。
3. **摘要无 schema** — 模型自由发挥，用户约束、文件路径、剩余步骤在压缩后分布随机。
4. **ephemeral 时间戳噪声** — 秒级时间让动态上下文每轮不同，浪费 token 且降低 prompt cache 命中。
5. **瘦身时机错误** — 大输出先以全文进入历史，之后才被 `tool_result_budget` / `micro_compact` 改写；已经发出的历史不再是 append-only。

---

## 对标（为何这么改）

| 产品 | 可借鉴点 |
|------|----------|
| **Claude Code** | 多层 cascade；摘要后保留 tail + `compact_boundary`；大输出落盘 |
| **OpenCode** | **固定摘要模板**（Goal / Constraints / Files / …）；prune 旧 tool 而非硬删 |
| **Cursor** | 短规则层在压缩后仍存活 |
| **Gemini CLI** | tool distillation 写磁盘；双阈值主动/被动压缩 |

Phase 1 取舍：**先对齐 OpenCode 模板 + Claude Code tail 保留 + persist-not-delete**。  
更重的 memory / soft limit 不写进固定路线，见文末「仍观察」。

---

## Phase 1 改进（已实施）

### 1. `compact_history` 保留尾部（对齐 `reactive_compact`）

```python
# harness/agent/compact.py
tail = _keep_tail(messages, count=COMPACT_TAIL_COUNT)  # 5
compacted = [{"role": "user", "content": f"[Compacted]\n\n{summary}"}, *tail]
```

压缩后上下文 = **结构化摘要 + 最近 5 条消息**（含 tool_use/tool_result 配对）。

### 2. 结构化摘要模板

`summarize_history` 要求模型按固定标题输出：

- `## Goal`
- `## User Constraints`
- `## Changed Files`
- `## Key Findings`
- `## Remaining Work`
- `## Do NOT Forget`

### 3. `micro_compact` 落盘而非硬删

新增 `persist_recallable_output()`：对 >120 字符的旧 tool 结果写入 `.tool_results/{tool_use_id}.txt`，上下文保留路径 + 500 字 preview。agent 可用 `read_file` 恢复全文。

### 4. 动态时间默认分钟粒度

`build_session_context` 默认 `time_granularity="minute"`；可用环境变量恢复秒级：

```bash
HARNESS_TIME_GRANULARITY=seconds   # 默认 minute
```

同一分钟内 ephemeral 上下文不变，利于 `if_unchanged` 跳过重复注入。

### 5. 最新用户话覆盖摘要旧目标（001-B）

`compact_history` / `reactive_compact` 在摘要 + tail 之后，**强制**追加（或升级末条为）：

```text
[Current user request]
This is the latest user instruction. It overrides any conflicting
goals, remaining work, or older tasks in a [Compacted] summary above.

{用户原话}
```

摘要 prompt 也要求 Goal 必须跟「时间上最新的真实用户指令」，冲突时最新胜出。  
跳过 tool_result、`[Compacted]`、`[Scheduled]` 等 harness 注入，避免误把系统消息当用户意图。

## Phase 2 改进（缓存稳定性）

### 1. 工具结果首次入场前定型

所有同步工具结果统一经过 `build_user_content()`，并在追加到 `messages` 之前调用
`stabilize_tool_results()`：

- 单个结果默认最多 `12000` 个模型可见字符；
- 同一并行工具轮默认共享 `40000` 字符预算；
- 超限结果全文写入 `.task_outputs/tool-results/{tool_use_id}.txt`；
- 历史中只保留固定的头尾 preview、原始长度和 `read_file` 路径；
- tool id 会做路径安全处理，不能通过 `../` 写出目标目录。

可配置：

```bash
HARNESS_TOOL_RESULT_MAX_CHARS=12000
HARNESS_TOOL_ROUND_MAX_CHARS=40000
```

`read_file`、`rag_search`、shell/MCP 等工具都走同一个入口，因此无需在每个工具里维护一套互相不一致的截断规则。

### 2. 普通轮次保持 append-only

现在 `prepare_context()` 在未达到阈值时是 no-op，不再逐轮调用：

- `tool_result_budget`
- `snip_compact`
- `micro_compact`

这三个函数保留为兼容/显式降级能力，但不再进入正常 agent loop。一次请求发出的历史，在检查点前不会被后续轮次改写。

### 3. 只在显式检查点重写历史

只剩两类边界会创建新历史：

1. token 估算达到 `HARNESS_AUTOCOMPACT_PCT`（默认 83.5%）时执行 `compact_history`；
2. API 明确返回 prompt-too-long 时执行 `reactive_compact`。

每个边界会造成一次预期的缓存冷启动，之后重新开始稳定增长；不会像旧版渐进 micro/snip 那样连续多轮失效。

---

## 具体例子：CWRF 实施方案

**场景：** 用户要求参照 `files/样例/5 CWRF…实施方案.docx` 写 `output/plan/`，agent 用 tool 读出 ~30KB docx，再写多章 markdown。

### 修复前

1. 读 docx → tool_result 占满上下文  
2. `micro_compact` 把早期章节结构替换成 `[Earlier tool result compacted]`  
3. 超 50KB → `compact_history` **只剩一条自由摘要**  
4. 下一轮 agent 不知道样例路径、章节编号、已写 `02_项目管理方案.md` → 重写或跑偏  

### 修复后

1. 读 docx 的结果首次入场就变成稳定 preview + `Full output: .task_outputs/tool-results/….txt`
2. 后续工具轮只追加消息，已发送前缀保持不变，可被 DeepSeek 继续命中
3. 达到 token 阈值 → 摘要含 **User Constraints** + **Changed Files** + **最近 5 轮**
4. 末尾 **`[Current user request]`** 重申「写 CWRF…」——即使摘要仍写着「验 ch07」也以本条为准
5. 若仍缺细节 → `read_file` 恢复 persisted 全文

---

## 相关文件

| 模块 | 变更 |
|------|------|
| `harness/agent/compact/` | 入场预算、落盘 preview、append-only prepare、检查点摘要与 tail |
| `harness/agent/background.py` | `build_user_content()` 作为所有 tool result 的统一入场边界 |
| `harness/prompts/dynamic.py` | `default_time_granularity()`、`HARNESS_TIME_GRANULARITY` |
| `tests/test_compact.py` | 入场预算、路径安全、历史不可变、tail / focus / reactive fallback |
| `tests/test_dynamic_prompt.py` | 时间粒度默认与 env |

---

## 仍观察（有痛点再商量）

| 项 | 说明 |
|----|------|
| `snip_compact` 无语义硬切 | 仅在摘要不可用的降级检查点使用，不再逐轮执行 |
| 超长单次结果 preview | 当前按字符做确定性头尾裁剪，不是按语义段落蒸馏 |
| 自动 memory 写回 | 用户纠正未写入 `.memory/` |
| transcript 消费 | `.transcripts/` 已写但未用于恢复决策 |
| 推理模型空摘要 | **已单独立项修复** → [009](./009-compact-empty-summary.md) |

总览与候选下一步见 [bugs README](./README.md)。

---

## 验证

```bash
python -m unittest tests.test_compact tests.test_dynamic_prompt -v
```

用例覆盖：工具结果首次落盘与总预算、恶意 tool id 路径安全、阈值前历史不可变、`compact_history` 尾部、`[Current user request]` 覆盖旧摘要目标、摘要六段标题和时间粒度。
