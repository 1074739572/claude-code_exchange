# 013 — 工具历史渐进改写导致 DeepSeek 缓存命中率低

**状态：** 已修复；回归与 DeepSeek live A/B 均通过
**日期：** 2026-07-23
**关联：** [002 Prompt 缓存](./002-prompt-cache-vs-dynamic-context.md) · [004 上下文压缩](./004-context-compaction.md) · [011 Auto-compact 阈值](./011-autocompact-token-threshold.md)

## 现象

静态 system、tools 和 ephemeral 分层稳定以后，受控实验的缓存命中率已经很高，但真实长任务仍可能出现：

- DeepSeek `cache_read_input_tokens` 偏低；
- 工具调用越多，命中率没有随历史增长而稳定上升；
- 大文件、shell、MCP、`rag_search` 返回较多内容后，后续数轮 miss 明显增加；
- 没有换模型、没有改 system，也会发生缓存前缀突然缩短。

这说明问题不只在 system 前缀，持久化的 `messages` 历史本身也在变化。

## 缓存原理

DeepSeek 自动缓存请求的精确 token 前缀。相邻请求理想结构是：

```text
请求 N:   [tools][system][历史 A][本轮新增尾巴]
请求 N+1: [tools][system][历史 A][上一轮回答][新工具结果][本轮新增尾巴]
          └────────────── cache hit ──────────────┘
```

历史增长不是问题。只要旧内容逐字不变，下一轮可以命中更长前缀。

真正破坏缓存的是对旧历史做原地修改：

```text
请求 N:   [tools][system][旧 tool 全文][后续历史]
请求 N+1: [tools][system][旧 tool 的 compact wrapper][后续历史]
                              ↑ 第一个差异从这里开始，后面全部 miss
```

因此本次修复的核心不只是“少放 token”，而是建立约束：

> 工具结果首次进入历史时就定型；进入历史后只追加，不做渐进改写。只有明确的上下文检查点可以整体替换历史。

## 为什么原来会这么做

旧版 `prepare_context()` 每次调用模型前执行：

```text
tool_result_budget
  → snip_compact
  → micro_compact
  → compact_history（达到 token 阈值时）
```

这些函数的原始目标是合理的：

- `tool_result_budget`：避免单轮多个大结果撑爆请求；
- `micro_compact`：只保留最近几个工具结果全文，旧结果落盘后换成 preview；
- `snip_compact`：消息超过固定数量时裁掉中间历史；
- `compact_history`：接近模型窗口时生成摘要并保留 tail。

问题在于执行时机。大结果先以全文进入历史并发送给模型，后续轮次才逐步替换。每替换一次，缓存从该历史位置开始失效。`snip_compact` 达到 50 条后也可能连续改变历史中段。

这是“上下文控制优先”的旧设计，没有把 provider 的精确前缀缓存作为一等约束。

## 根因

### 1. 工具结果后处理

旧逻辑在 `messages.append(...)` 之后才控制大小。此时全文已经成为缓存前缀的一部分。

### 2. `micro_compact` 是渐进式的

`KEEP_RECENT_TOOL_RESULTS=3` 时，第 4、5、6 个工具结果到来会依次把更早的结果替换为 persisted wrapper。连续多个请求都在改旧前缀。

### 3. `snip_compact` 每轮执行

达到消息数量阈值后，裁剪边界随新消息移动。即使总 token 尚未接近模型窗口，也可能不断产生新历史形状。

### 4. 大结果同时放大 miss

`read_file`、shell、MCP、RAG 等工具的长输出第一次出现时本来就属于新 token。如果不在入场前限制，它们会制造很大的 miss 尾巴，并在之后被二次改写。

## 修复后的架构

### 阶段一：工具结果入场定型

所有同步工具结果和取消后的补全结果统一经过：

```text
tool handler 原始结果
  → build_user_content()
  → stabilize_tool_results()
  → messages.append()
```

默认策略：

- 单个工具结果最多 `12000` 个模型可见字符；
- 同一个并行工具轮共享 `40000` 字符预算；
- 未超限结果原样进入历史；
- 超限结果全文写入 `.task_outputs/tool-results/`；
- 模型只收到稳定的 head/tail preview、原始字符数和全文路径；
- 原始 result 字典不被修改；
- tool id 经过路径安全处理，`../` 等内容不能逃出落盘目录；
- 同一 tool id 冲突时覆盖旧文件，避免 resumed session 指向陈旧内容。

模型侧 wrapper 示例：

```text
<persisted-output truncated original_chars="58231">
Full output: .../.task_outputs/tool-results/toolu_123.txt
Preview:
...头部...
--- omitted 46400 chars; use read_file for full output ---
...尾部...
</persisted-output>
```

头尾都保留是因为：

- 文件头通常含标题、schema、命令和上下文；
- 文件尾常含测试总结、异常栈末端、最终统计；
- 中间全文仍可通过 `read_file` 按需召回。

配置项：

```bash
HARNESS_TOOL_RESULT_MAX_CHARS=12000
HARNESS_TOOL_ROUND_MAX_CHARS=40000
```

### 阶段二：普通轮次 append-only

未达到上下文阈值时，`prepare_context()` 现在是 no-op：

```python
if should_autocompact(messages):
    messages[:] = compact_history(messages)
return messages
```

正常工具循环只允许在末尾追加 assistant/tool_result/user 消息，不再逐轮调用：

- `tool_result_budget`
- `micro_compact`
- `snip_compact`

旧函数暂时保留给兼容测试和摘要失败时的显式降级路径，但不再改写正常 agent loop 的历史。

### 阶段三：检查点压缩

只有两种情况允许整体替换历史：

1. `estimate_tokens(messages)` 达到约 `0.835 × context_window`；
2. API 明确返回 prompt-too-long，再执行 `reactive_compact`。

检查点会生成结构化摘要、保留最近 tail，并强化最新用户请求。它会造成一次预期的缓存冷启动，但之后重新进入 append-only 增长。

```text
稳定增长 ──► 检查点（一次 cold start）──► 稳定增长 ──► 下个检查点
```

旧行为则更接近：

```text
增长 ─► micro 改旧结果 ─► miss ─► 再改旧结果 ─► miss ─► snip 移边界 ─► miss
```

## 系统不变量

本次改动把以下约束写进代码和测试：

1. **入场定型**：超长工具结果在第一次 append 前完成落盘和 preview。
2. **历史不可变**：未达到检查点时，`prepare_context()` 不修改任何已发送消息。
3. **前缀增长**：追加新轮次后，先前消息序列化结果保持一致。
4. **可召回**：裁剪不等于删除，全文路径始终可供 `read_file` 使用。
5. **有界输入**：单结果和并行工具轮都有模型可见预算。
6. **路径安全**：模型或 provider 生成的 tool id 不能控制任意写入路径。
7. **检查点明确**：只有主动 token 阈值和 reactive overflow 可以重写历史。

## 相关改动

| 文件 | 作用 |
|------|------|
| `harness/agent/compact/persist.py` | 入场预算、稳定 head/tail wrapper、全文落盘、路径安全 |
| `harness/agent/background.py` | `build_user_content()` 作为统一 tool result 入场边界 |
| `harness/agent/compact/pipeline.py` | 普通 `prepare_context()` 改为 append-only；保留检查点压缩 |
| `harness/agent/compact/__init__.py` | 导出稳定化配置和 API |
| `.env.example` | 新增单结果、并行轮和检查点配置说明 |
| `tests/test_compact.py` | 入场、总预算、路径安全、历史不可变、前缀增长回归 |
| `docs/bugs/002-prompt-cache-vs-dynamic-context.md` | 缓存总设计补充 Phase 2 |
| `docs/bugs/004-context-compaction.md` | 压缩策略更新为入场定型 + 检查点 |

## 验证

已执行：

```bash
python -m pytest tests/test_compact.py \
  tests/test_dynamic_prompt.py \
  tests/test_llm_cache_log.py \
  tests/test_message_repair.py \
  tests/test_lookup_guard_loop.py \
  tests/test_writing_guard_loop.py \
  tests/test_empty_reply_nudge.py -q

python -m pytest tests/test_rag_retrieval.py \
  tests/test_rag_qa.py \
  tests/test_rag_commands.py \
  tests/test_file_mode.py -q
```

Agent/cache/loop 与 RAG/file-mode 相关回归均通过，修改文件无 IDE lint 错误。

测试重点不是只断言“输出变短”，还验证：

- `stabilize_tool_output()` 保存完整原文并同时保留头尾；
- 多工具结果共享轮次预算；
- 恶意 tool id 不会目录穿越；
- `build_user_content()` 确实经过统一入口；
- 未达到阈值时 `prepare_context()` 前后 deep-equal；
- 追加新轮次后旧消息的序列化前缀不变。

## 如何观察真实效果

本地回归只能证明历史稳定，不能伪造 DeepSeek 服务端命中。真实长任务应观察：

```text
[cache] hit=... miss=... (...%)
```

健康表现：

- 第 2 个工具回环起 hit 应大于 0；
- 同模型、同会话内 hit token 总体随历史增长；
- 大工具结果出现时 miss 会增加一次，但后续不应因 micro/snip 连续重置；
- 只有 compact 检查点、换模型、静态 prompt/tool schema 改变时出现可解释冷启动。

命中率仍可能受 provider 缓存过期、负载路由、模型切换、tool schema 变化和动态 ephemeral 更新影响。因此本修复保证的是“客户端不主动破坏旧前缀”，不承诺每次请求的服务端命中百分比。

## 2026-07-23 DeepSeek Live A/B

使用 `deepseek-v4-flash` 做了 7 轮真实 API 对照。两组具有独立实验前缀，避免互相借用缓存；每轮新增一个 20000 字符的模拟工具结果：

```bash
python scripts/run_cache_experiment.py --live \
  --model deepseek-v4-flash \
  --rounds 7 \
  --result-chars 20000 \
  --output evals/cache/live_append_only_ab_20260723.json
```

结果（第 1 轮为必然冷启动，汇总使用第 2～7 轮）：

| 指标 | 旧版渐进改写 | 新版 append-only | 变化 |
|------|-------------:|----------------:|-----:|
| warm cache hit rate | 26.3% | 76.8% | **+50.5 个百分点** |
| warm hit tokens | 38272 | 90368 | +136.1% |
| warm miss tokens | 107426 | 27290 | **-74.6%** |

`micro_compact` 从第 5 轮开始改写旧结果后，差异更明显：

| 第 5～7 轮汇总 | 旧版渐进改写 | 新版 append-only |
|----------------|-------------:|----------------:|
| cache hit rate | 12.1% | **83.6%** |
| miss tokens | 84553 | **13689** |

逐轮新版命中率为：

```text
round 1:  0.0%  cold start
round 2: 70.5%
round 3: 47.1%
round 4: 65.6%
round 5: 74.1%
round 6: 79.6%
round 7: 94.5%
```

逐轮仍有 provider 缓存分块、写入时机和路由造成的波动，但趋势符合设计：新版历史增长后 hit 总体上升；旧版开始改写历史后命中率降到约 11%～14%。

原始报告保存在 `evals/cache/live_append_only_ab_20260723.json`，可用于后续重复实验比较。该结果是受控合成工具循环，不等同于所有真实业务会话都固定提升 50.5 个百分点；它直接验证了本次修改针对的“历史渐进改写”变量。

## 取舍

- 过长结果不会一次性全部给模型看；需要时模型要再调用 `read_file`。
- 头尾裁剪是确定性的，不是模型语义蒸馏，成本低且不会引入额外 API 调用。
- 检查点仍会冷启动，但它是低频、可解释、可记录的边界。
- `12000/40000` 是上下文质量和 miss 成本的默认平衡，可按模型窗口与任务类型调整。

本次没有移除 compact，而是把“每轮渐进修改”改成“入场一次定型 + 低频检查点”。这样同时保留上下文安全、信息可召回和缓存前缀稳定性。
