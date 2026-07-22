# GAIA 改进规划（知识点全整理 + 分层改进方案）

> 基于 `run_20260722T080507Z`（L1 5/10 = 50%）的失败分析。
> 详细逐题归因见 `BASELINE_ANALYSIS.md`。本文档是**行动规划**：哪层要改、为什么、怎么改、什么顺序。

---

## 一、知识点回顾（当前认知的全貌）

### 1. GAIA 是什么、怎么评分
- 466 题验证集，L1（≤5 步）/ L2（5–10 步）/ L3（长链路），只看 **FINAL ANSWER 精确匹配**（quasi-exact match）。
- 归一化规则：数字去 `$ % ,`；字符串去冠词/空白/小写；列表按 `,`/`;` 分列后逐项比。
- **中间过程不给分**：搜索 20 次和 2 次拿到相同答案，得分一样。所以「效率」不影响分数，但影响是否在预算内拿到答案。

### 2. 我的 agent 当前架构（与 GAIA 相关的部分）
```
evals/gaia/run.py          评测入口（加载题→逐题跑→评分→落盘）
evals/gaia/agent_run.py    单题执行（组 prompt→agent_loop→提取 FINAL ANSWER→兜底 finalize）
evals/gaia/prompt.py       GAIA 官方答题模板 + 工具纪律 + 强制收尾 prompt
evals/gaia/scorer.py       官方评分逻辑 + FINAL ANSWER 提取
harness/loop.py            核心循环（LLM→工具→guard→注入 nudge）
harness/agent/lookup_guard.py  web 预算/stale/单站/近重复 拦截
harness/agent/compact/     上下文压缩（summarize→只留摘要+尾部5条）
harness/prompts/sections.py    系统 prompt（"You are a coding agent"）
harness/tools/registry.py      工具池 + 工具描述
```

### 3. 五种失败模式（一句话版）
| 模式 | 病 | 病根层 |
|------|----|--------|
| A 单位读错 | "how many thousand hours" 答了 17000 而非 17 | **Prompt 层**（缺语义澄清步骤）|
| B guard 太紧 | 单个 PDF 404 被放大成"全局 web 不行"，2 次就放弃 | **Guard 层**（计数维度粗）|
| C compact 失忆 | 推理模型摘要写进 thinking 块，compact 只读 text 块 → "(empty summary)" | **Compact 层**（确定代码 bug）|
| D 记忆当事实 | 被 block 后退回参数记忆，自信报错 | **Guard+Prompt 层**（block 不升级 + 不区分证据/记忆）|
| E 视频缺口 | 无 YouTube/视频工具，只能瞎猜 | **工具层**（能力缺口）|

### 4. 本轮已完成的改动（不用重做）
- LookupGuard：近重复查询检测（Jaccard≥0.6 拦截）、单站配额（默认 4 次）、`HARNESS_LOOKUP_HOST_LIMIT` / `HARNESS_LOOKUP_DUP_THRESHOLD` 环境变量。
- loop：60% 预算处注入一次性收尾提醒。
- GAIA eval 默认预算降到 `web_fetch_limit=10, web_stale_limit=2`。
- `_force_finalize`：max_rounds 或无答案时，无工具跑 2 轮强制产出 FINAL ANSWER。
- **✅ CONTEXT_LIMIT → token 比例触发**：默认 `estimate_tokens ≳ 0.835 × context_window`（对齐 Claude Code）；`models.json` 的 `context_window`；绝对覆盖仍用 `HARNESS_CONTEXT_LIMIT`（**tokens**）。GAIA 默认走同一规则 + `compact_tail=10`。
- **✅ 研究纪律收归共享路径（纠偏「评测换皮」）**：
  - 撤回 `GAIA_SYSTEM_PROMPT` + `system_override`（不为过测单独换身份）。
  - `harness/prompts/lookup.py` 抽出 `RESEARCH_DISCIPLINE`，写入日常 `LOOKUP_CONSTRAINT`。
  - identity 改为「coding agent that also answers factual / research questions」。
  - GAIA `build_user_prompt` 只保留评分格式，并 `append_lookup_constraint`；`lookup_mode=True`。
  - 原则：评测暴露问题 → 改日常也会走的能力；FINAL ANSWER 才留在 evals/。
- **✅ Compact 空摘要失忆（模式 C）**：`docs/bugs/009-compact-empty-summary.md` —
  thinking 回退提取 + 不可用则降级保留近期消息，禁止 `(empty summary)`。
- **✅ LookupGuard 校准（模式 B/D）**：`docs/bugs/010-lookup-guard-calibration.md` —
  hard_fail vs soft_stale；连续 block → strip tools + `LOOKUP_FORCE_ANSWER`。

### 5. 新发现的两个隐藏问题（本次整理时确认）
- **身份错位**：GAIA 评测跑的是 `"You are a coding agent. Follow Resolve → Act → Close"` 的系统 prompt（`sections.py`），里面全是 coding 任务的纪律（deixis 消解、工作目录、thesis 技能目录）。研究型问答任务用 coding persona，工具选择和行为习惯都会偏。
- **CONTEXT_LIMIT=50000 字符太小**（`settings.py:47`）：web 任务一页 fetch 就 10–50KB，两三次就触发 compact。**模式 C 的触发频率被这个放大了**——compact 本身有 bug，又特别容易被触发。

---

## 二、改进方案（按层分组，每层标注：软改/硬改、预期收益、风险）

> 你的直觉是对的：**很多问题在 prompt 层就能修，不需要硬编码。**
> 原则：先软后硬——prompt 改动零风险可以先铺开；代码改动逐个验证。

### 第 1 层：Prompt 层（软改动，优先做，零回归风险）

#### 1.1 答题开头 prompt 加「语义澄清」步骤 —— 治模式 A ✅
共享 `RESEARCH_DISCIPLINE`：先复述 WHAT / 单位与格式再动手。
GAIA `GAIA_ANSWER_INSTRUCTIONS` + `build_user_prompt` 同步要求一行复述。

#### 1.2 FINAL ANSWER 前加「边界条件核对清单」—— 治模式 A + 格式分 ✅
共享 `ANSWER_BOUNDARY_CHECK`（单位 / 格式 / 类型）。
GAIA：`GAIA_ANSWER_INSTRUCTIONS`、`GAIA_SCORING_REMINDER`、`FORCE_FINAL_ANSWER_PROMPT` 均含清单。

#### 1.3 「证据 vs 记忆」纪律 —— 治模式 D ✅ 已落入共享层
已写入 `harness/prompts/lookup.py` 的 `RESEARCH_DISCIPLINE`（日常 LOOKUP_CONSTRAINT + GAIA 共用）。
不要再塞进 eval-only 文案。

#### 1.4 「fetch 后先读再搜」流程化 —— 治 over-fetch ✅ 已落入共享层
同上，在 `RESEARCH_DISCIPLINE`。

#### 1.5 失败换源策略表 —— 治模式 B 的 agent 侧 ✅ 已落入共享层（简版）
`RESEARCH_DISCIPLINE` 含换源原则；更细的站点表可后续再补进 lookup.py。

#### 1.6 身份错位 —— ❌ 不要「评测换皮」，✅ 改共享身份 + 走 lookup 路径
**纠偏（已落地）**：
- 撤回 `GAIA_SYSTEM_PROMPT` / `system_override`（那是为过测换皮）。
- identity：`coding agent that also answers factual / research questions` + 查事实短纪律。
- GAIA：`lookup_mode=True` + `append_lookup_constraint`；user prompt 只留 FINAL ANSWER 评分格式。
- 原则：评测暴露问题 → 修日常也会走的能力。

### 第 2 层：Compact 层（P0 硬 bug，必须修）

#### 2.1 `summarize.py` 修 thinking 块丢失 —— 治模式 C ✅ 已修复
见 `docs/bugs/009-compact-empty-summary.md`：`extract_summary_text` 回退 thinking；`max_tokens=8000`。

#### 2.2 空摘要兜底：宁可不 compact，不要失忆 ✅ 已修复
`is_summary_unusable` → pipeline 降级为 snip + 保留尾部，禁止 `(empty summary)` 替换历史。

#### 2.3 摘要模板加「已试 URL + 已得事实」段 ✅ 已补
`## Sources Tried` / `## Facts Gathered`。

#### 2.4 CONTEXT_LIMIT / tail 可配置 ✅ 已升级为 token 比例
默认 `0.835 × model_context_window`（`HARNESS_AUTOCOMPACT_PCT` / `HARNESS_CONTEXT_WINDOW` / `HARNESS_CONTEXT_LIMIT` token 绝对覆盖）；GAIA 默认同规则 + tail 10。

### 第 3 层：Guard 层（校准）✅ 已完成

#### 3.1 stale 计数分维度 —— 治模式 B ✅
- `classify_fetch_result` → `ok` / `hard_fail` / `soft_stale`
- URL 404/robots/403 → 只 ban URL（robots/403/429 再 ban host），**不加**全局 `consecutive_stale`
- 全局 stale 只对 soft（空结果 / 无关 / 失败搜索）计数

#### 3.2 block 消息重写 —— 配合 1.3 治模式 D ✅
证据尾巴统一：`THIS conversation`；禁止 memory 当事实；tentative guess 可。

#### 3.3 连续 block 硬升级 —— 治 guard 不服从 ✅
`note_block` → `finalize_latched`（`HARNESS_LOOKUP_BLOCK_ESCALATE` 默认 2）→
loop 注入 `LOOKUP_FORCE_ANSWER` + `strip_tools_until_answer`。

见 `docs/bugs/010-lookup-guard-calibration.md`。

### 第 4 层：评测/收尾层（小改动）

#### 4.1 `_force_finalize` prompt 升级 ✅
`FORCE_FINAL_ANSWER_PROMPT` 已含 `ANSWER_BOUNDARY_CHECK`（重读题、查单位、查格式）。

#### 4.2 results.jsonl 加失败模式便签
落盘时记录 `n_blocked`（被 guard 拦了几次）、`compacted`（是否发生过 compact）、
`web_calls`。下次分析不用翻 transcript 就能定位模式。

### 第 5 层：工具层（能力缺口，最后做）

#### 5.1 YouTube transcript 工具 —— 治模式 E
`youtube-transcript-api`（纯 HTTP，不用装浏览器）拿字幕；字幕答不了视觉题就认。
L1 里视频题占比小，优先级最低。

#### 5.2 Wikipedia REST API 工具（可选，性价比高）
`en.wikipedia.org/api/rest_v1/page/summary|html/<title>` 干净 JSON，比 fetch
整页 HTML 省 90% token，还降低 compact 触发率。GAIA 大量题指向 Wikipedia。

#### 5.3 学术检索 fallback（可选）
`arxiv.org/abs/` / Semantic Scholar API 作为论文题的标准路径（配合 1.5）。

---

## 三、执行顺序（每阶段跑一次 L1×10 验证）

```
阶段 1（共享 lookup 纪律 + identity）✅ 已完成
  RESEARCH_DISCIPLINE → LOOKUP_CONSTRAINT；identity 承认查事实；
  GAIA 去掉 system_override，lookup_mode=True，prompt 只留评分格式。
  ✅ 1.1 读题复述 + 1.2 ANSWER_BOUNDARY_CHECK / FINAL ANSWER 核对清单

阶段 2（compact 修复）✅ 已完成
  2.1 thinking 回退 + 2.2 空摘要降级 + 2.3 Sources/Facts + 2.4 CONTEXT_LIMIT
  文档：docs/bugs/009-compact-empty-summary.md

阶段 3（guard 校准）✅ 已完成
  3.1 stale 分维度 + 3.2 block 文案 + 3.3 连续 block 硬升级
  文档：docs/bugs/010-lookup-guard-calibration.md
  验证：单元/loop 测试；建议重跑 L1×10

阶段 4（收尾 + 工具，按需）
  4.1 finalize 清单 ✅（并入 FORCE_FINAL_ANSWER_PROMPT）
  仍待：4.2 结果便签 + 5.2 Wikipedia API + 5.1 YouTube
  验证：L1 全量（53 题）跑一次做新 baseline
```

**预期总收益**：L1 从 50% 到 70–80%（救回 A/B/C/D 四类中的 3 类；E 需要工具）。

---

## 四、你问的三个点，对应到方案里

| 你的直觉 | 对应方案 | 判断 |
|----------|----------|------|
| 「回答开始的 prompt 就可以改」 | 共享 identity + LOOKUP_CONSTRAINT（日常也生效），不是 GAIA 换皮 | ✅ 已纠偏落地 |
| 「边界条件」 | 1.2 `ANSWER_BOUNDARY_CHECK` + 3.1 guard 边界 | ✅ 已落地 |
| 「语义澄清，不只是硬编码」 | 研究纪律进 lookup.py；FINAL ANSWER 才留 evals/ | ✅ |

一句话：**评测只加评分格式；查事实纪律改产品共享路径。阶段 1–3 + 1.1/1.2 已落地；下一优先工具层（Wiki/YouTube）或重跑 L1×10。**
