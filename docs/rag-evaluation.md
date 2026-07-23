# RAG 分层测试与评测

RAG 质量不能只看最终回答。系统将质量拆成四层：

```text
文档解析 → 检索排序 → 回答与引用 → 性能/费用
```

前一层失败时，后一层分数没有诊断意义。例如回答缺少数字，可能是 OCR 没提取、检索没召回，也可能只是生成模型遗漏。

## 1. 快速运行

无网络、无真实 VLM 的确定性评测：

```sh
python main.py rag eval
python main.py rag eval --output evals/results/rag/latest.json
```

评测命令默认强制使用确定性、离线的 `hash` embedding，避免因为本机存在 API Key 而产生网络调用。需要评估生产后端时显式传入 `--embedding bge-m3`、`openai` 或 `auto`。

指定自己的语料和金标：

```sh
python main.py rag eval \
  --corpus path/to/corpus \
  --gold path/to/gold.yaml \
  --output evals/results/rag/custom.json
```

退出码为 `0` 表示全部阈值通过，`1` 表示至少一个指标低于门槛，适合直接接入 CI。

完整回归：

```sh
pytest tests/test_rag_*.py tests/test_file_mode.py tests/test_tui_m1.py -q
```

## 2. 金标 schema

默认金标为 `evals/rag/gold_queries.yaml`：

```yaml
schema_version: 2
ks: [1, 3, 5, 10]
thresholds:
  recall_at_3: 0.75
  recall_at_5: 0.90
  mrr: 0.70
  ndcg_at_5: 0.75
  extraction_pass_rate: 1.0

queries:
  - id: quarterly_delivery
    category: table
    query: "第三季度交付多少套？"
    relevant:
      - source: quarterly.pdf
        page: 3
        modality: table
        expect_all: ["12", "套"]
        grade: 2
    top_k: 5
```

一个问题可以有多个 relevant target。`grade` 越大表示相关性越高；同一个 target 即使被重复 chunk 命中，也只计一次，避免重复内容抬高 nDCG。

旧字段 `expect_any`、`expect_source`、`expect_modality`、`expect_page` 仍兼容。

### 解析金标

```yaml
extraction:
  - source: quarterly.pdf
    modalities:
      text: 1
      table: 2
      image: 1
    facts:
      - id: delivery
        expect_all: ["交付数量", "12 套"]
        page: 3
        modality: table
```

`modalities` 表示最少应产生多少个对应块。`facts` 验证关键内容、页码和模态是否同时正确。

## 3. 指标含义

| 指标 | 诊断目标 |
|------|----------|
| `Recall@k` | 前 k 条中是否至少包含一个正确目标 |
| `MRR` | 第一个正确结果出现得是否足够靠前 |
| `nDCG@k` | 多个不同相关等级的目标排序是否合理 |
| `extraction_pass_rate` | 解析事实和模态断言通过比例 |
| `latency_ms_mean/p95` | 当前语料下检索平均和尾部延迟 |

报告同时按 `category` 分组。至少应包含：

- `text`
- `exact-term`
- `numeric`
- `semantic`
- `table`
- `image`
- `scanned`
- `cross-page`
- `hard-negative`

不要只看总平均值，纯文本问题容易掩盖图片和扫描页退化。

## 4. 回答规则评测

`harness.rag.eval.evaluate_answer` 不调用 LLM，只检查确定性规则：

```python
from harness.rag.eval import evaluate_answer

case = {
    "answer_expect": {
        "contains_all": ["12", "套"],
        "excludes": ["15 套"],
        "citation": {"source": "quarterly.pdf", "page": 3},
    }
}
result = evaluate_answer("交付 12 套。[quarterly.pdf，第 3 页]", case)
```

批量评测使用 `evaluate_answers(cases, answer_fn)`。`answer_fn` 可以是离线假模型、固定快照或真实 QA。PR 测试应使用确定性 provider；真实模型只放 nightly/manual job。

LLM-as-judge 只适合开放性完整度，不能替代数字、单位、source/page 和禁用内容的规则断言。

## 5. 数据集建设

建议先做到 100～300 题：

1. 每份真实文档挑选可核验事实，记录 source/page/modality。
2. 为同一事实编写关键词、自然语言、同义改写三种问法。
3. 加入术语相似但答案不同的干扰文档。
4. 图表问题必须记录关键值、趋势、坐标轴或图例。
5. 扫描件同时保留清晰、倾斜、低分辨率和中英混排样本。
6. 数据集拆分为开发集和冻结回归集，调参时不能只优化冻结集。

真实敏感 PDF 不应提交仓库。可以在 CI 机器挂载私有 corpus，只提交脱敏金标或合成 fixture。

## 6. CI 分层

### Pull Request

- hash embedding
- 禁止网络和真实 VLM
- 合成 PDF、单元测试、默认离线评测
- 目标 1～2 分钟

```sh
pytest tests/test_rag_*.py -q
python main.py rag eval --output evals/results/rag/pr.json
```

### Nightly

- 较大真实 PDF corpus
- 本地 OCR、BGE-M3、BGE reranker
- 对比上一份 JSON 基线
- 检查各 category、P95 和索引体积

### Weekly / Manual

- 真实 VLM OCR 和图片描述
- 最终回答与引用质量
- 记录模型名、endpoint、调用数、失败率、token/费用

评测时应固定 embedding、reranker 和 OCR/VLM 配置。模型或检索 schema 变化必须生成新基线，不能直接与旧环境比较。

## 7. 推荐门槛

初始门槛可设为：

```text
整体 Recall@5          >= 0.90
表格 Recall@5          >= 0.90
图片 Recall@5          >= 0.80
扫描页 Recall@5        >= 0.80
MRR                    >= 0.70
解析断言通过率          = 1.00
无答案回答误答率        <= 0.05
重复结果比例            <= 0.10
```

阈值应根据冻结测试集逐步收紧，不要在只有几道题时把偶然的 100% 当作真实上线质量。
