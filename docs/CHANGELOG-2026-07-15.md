# 本轮改动总览（2026-07-15）

> 接续 [2026-07-12](./CHANGELOG-2026-07-12.md)：在 lookup 护栏与 RAG/file 模式之上，补任务落锚、终端步骤 UI、以及本地 skills 扩充。

---

## 一、动机

| 现象 | 目标 |
|------|------|
| 指代模糊仍直接调工具，工具参数里写「注意事项」 | Resolve → 消歧/反问 → 再行动 |
| 终端每条工具都刷 `→ 结果预览` | 只看步骤 + 最终改了哪些文件 |
| `HARNESS_TOOL_UI=verbose` 等多档兼容 | 去掉模式矩阵，单一行为 |
| skills 偏少，查论文缺「何时停」纪律 | 补纸质检索 / 调试 / 共创等常用 skill |

---

## 二、改动清单

### 1. 任务落锚（Query Grounding）

| 项 | 位置 |
|----|------|
| identity：Resolve → Act → Close；终答尽量短 | `harness/prompts/sections.py` |
| grounding：消歧 / 不清则反问不调工具 / 禁止参数里写假设 | 同上 + `static.py` 装配 |
| GroundingGuard：首轮「强指代 + 无意图文本」裸 tool → 拦截 | `harness/agent/grounding_guard.py` · `loop.py` |
| lookup 约束：缺槽位先问；终答 ≤8 行 | `harness/prompts/lookup.py` |
| 静默追加约束，不再打印 `[lookup mode]` / `[writing mode]` 横幅 | `harness/hooks.py` |

### 2. 工具终端 UI（单一行为）

| 项 | 位置 |
|----|------|
| `›` 意图 + `●` 步骤；成功结果不出 `→` | `harness/ui/renderer.py` · `tool_display.py` |
| 仅错误 / Guard 显示 `→` | `is_failure_tool_output` |
| 回合末 `Changed files:`（write/edit） | `harness/ui/turn_summary.py` · `loop.py` |
| **删除** `HARNESS_TOOL_UI` compact/verbose/off 矩阵 | — |
| 默认静默每轮 `[cache] hit=` / `[compact] transcript`（[006](./bugs/006-final-answer-buried.md)） | `llm.py` · `agent/compact/pipeline.py` |

完整 tool_result **仍进对话给模型**，只是终端不刷。

### 3. Skills 扩充（`skills/`）

| Skill | 用途 |
|-------|------|
| `paper-lookup` | 查作者/会议论文：成功标准与停条件 |
| `systematic-debugging` | 复现→假设→修→验证 |
| `office-docx` | 轻量 python-docx（不依赖 LibreOffice scripts） |
| `frontend-design` / `doc-coauthoring` / `skill-creator` | Anthropic 官方 prompt 技能（本地 catalog） |
| `requirements-clarity` | 此前已有，长需求澄清 |

注意：catalog description 会进静态 system，勿无限制堆 skill。

### 4. 文档 / 测试

- `docs/bugs/005-tool-loop-drift.md` — 补 grounding 根因与工具 UI 说明
- `docs/bugs/006-final-answer-buried.md` — 终答看不见：A compact 后 turn_start 漏打；B cache/compact 刷屏掩盖
- `README.md` — 工具展示说明更新
- `tests/test_grounding.py` · `tests/test_tool_ui.py` · `tests/test_llm_cache_log.py`

---

## 三、超算 / 远端同步

推送目标：GitHub `origin` → `https://github.com/1074739572/claude-code_exchange.git`（`main`）。

超算上更新：

```sh
cd <improved_harness 目录>
git pull origin main
# 若之前有本地改动冲突，先 stash 或确认后再 pull
```

本机若遇 SSL：`git -c http.sslVerify=false push origin main`（历史环境常见）。

---

## 四、相关文件锚点

```text
docs/CHANGELOG-2026-07-15.md
docs/bugs/005-tool-loop-drift.md
README.md

harness/prompts/sections.py
harness/prompts/static.py
harness/prompts/lookup.py
harness/hooks.py
harness/agent/grounding_guard.py
harness/loop.py
harness/ui/tool_display.py
harness/ui/renderer.py
harness/ui/turn_summary.py

skills/paper-lookup/
skills/systematic-debugging/
skills/office-docx/
skills/frontend-design/
skills/doc-coauthoring/
skills/skill-creator/
skills/requirements-clarity/

tests/test_grounding.py
tests/test_tool_ui.py
tests/test_llm_cache_log.py
docs/bugs/006-final-answer-buried.md
```
