# RAG 仿写工作流

本地 RAG 服务 **长文档仿写**（技术报告 / 结题 / 实施方案），**不**用于联网查论文（那是 lookup mode + fetch）。

---

## 1. 放文档（语料）

在 **agent 工作目录**（`python main.py` 的 cwd）下建：

```text
files/
  样例/              # 格式参考 docx/md
  指标与交付要求.md   # 硬性指标与交付
```

支持后缀：`.md`、`.txt`、`.docx`。  
`files/` 默认 gitignore，语料只放本机。

---

## 2. 自动流程（writing mode）

用户消息含 **仿写 / 撰写 / 技术报告 / files/** 等 → 自动：

1. `[writing mode]` 追加仿写约束  
2. **`rag_index` 等价**：对 `files/` 建索引（`.rag/`）  
3. ephemeral 注入索引状态  
4. **WritingGuard**：`write_file` 到 `output/*.md` 前必须有本会话 `rag_search`

也可显式：

```text
/rag add D:\docs\样例报告.docx     # CLI：拷入 files/ 并建索引
/rag index files                   # CLI：重建索引
rag_index path="files"             # Agent 工具
load_skill("thesis-writing")       # 同样会触发索引
rag_search query="引言 编写目的 段落结构"
write_file path="output/01_引言.md" ...
```

不启动 Agent 时，可在项目根目录：

```sh
python main.py rag add path\to\报告.docx
python main.py rag index files
python main.py rag docs
python main.py rag select 1,3
python main.py rag ask "技术路线分几个阶段？"
python main.py rag status
```

### 文件模式（`/mode file`）

与 **direct**（普通 Agent）相对：进文件模式后，**每条普通消息都走「检索 → 回答」**，不再进 coding agent loop。

```text
/rag index files          # 先有索引
/mode file                # 进入时选：搜全部 / 指定文档
技术路线是什么？          # 直接问，自动 RAG
搜全部                    # 改范围
指定文档                  # 打开多选
/mode direct              # 退出，回到普通对话
```

| 模式 | 行为 |
|------|------|
| `direct` | 普通 Agent，不自动做文档 RAG 问答 |
| `file` | 句句 grounded 问答；范围 = 指定文档或全部 |
| `plan` / `orchestrate` | 原有规划 / 编排 |

提示符在文件模式下为 `[model|file] >`。

### 选文档提问（仍可用 `/rag ask`）

```text
/rag docs
/rag pick
/rag ask 报告的技术路线是什么？
```

选择与范围保存在 `.rag/selection.json`（`scope: all|selected`）。

环境变量：`HARNESS_RAG_QA_LLM=0` 只返回检索摘录不调用模型；`HARNESS_RAG_QA_CONTEXT_CHARS` 控制送入模型的上下文长度。

---

## 3. 架构

### 父子块（Parent-Child）

每个标题节（如 `1.1 编写目的`）生成：

| 类型 | `level` | 作用 |
|------|---------|------|
| **父块** | `parent` | 整节全文（最多 8000 字），不进入检索 |
| **子块** | `child` | 按 ~600 字切分，带 `parent_id`，**只检索子块** |

检索命中子块后，`rag_search` 自动附上父块整节上下文（默认最多 4000 字）。

```text
## 1.1 编写目的          ← 标题栈
├── 父块 parent_id=p_xxx   整节：「本报告旨在…项目背景…」
├── 子块 child#0           「本报告旨在…」          parent_id=p_xxx
└── 子块 child#1           「项目面向风云四号…」    parent_id=p_xxx
```

### 流水线

```text
ingest (parse) → chunking (parent+child, merge short) → chunks/*.jsonl
                    ↓
         parents.json + BM25/Chroma（仅子块）
                    ↓
         hybrid search (RRF) → rerank → 附父块 → rag_search 输出
```

存储：

```text
.rag/
  chunks/*.jsonl       # 父块 + 子块
  index/corpus.json    # 可检索子块（BM25）
  index/parents.json   # 父块查找表
  chroma/              # 子块向量
```

| 工具 | 作用 |
|------|------|
| `rag_index path="files"` | 解析语料并重建 BM25 + 向量索引 |
| `rag_status` | sources / 父块·子块数 / embedding / 检索模式 |
| `rag_search` | 子块混合检索 + 重排 + 父块上下文 |

### 环境变量

| 变量 | 默认 | 含义 |
|------|------|------|
| `HARNESS_WRITING_GUARD` | `1` | 写 output 前必须 rag_search |
| `HARNESS_RAG_HIT_CHARS` | `1500` | 每条命中子块最大字符 |
| `HARNESS_RAG_PARENT_CHARS` | `4000` | 附带的父块上下文最大字符 |
| `HARNESS_RAG_MODE` | `hybrid` | `hybrid` / `bm25` / `vector` |
| `HARNESS_RAG_EMBEDDING` | `auto` | `auto` / `hash` / `openai` / `bge-m3` |
| `HARNESS_RAG_RERANK` | `1` | 检索后 lexical 重排（`0` 关闭） |
| `HARNESS_RAG_RERANK_MODEL` | *(空)* | 设 cross-encoder 模型名启用深度重排 |
| `HARNESS_RAG_FETCH_K` | `20` | 融合前候选数 |
| `HARNESS_RAG_RRF_K` | `60` | RRF 常数 |

**Embedding 自动选择（`auto`）**：有 `OPENAI_API_KEY` → OpenAI；否则用本地 hash（CI/无网）；设 `HARNESS_RAG_EMBEDDING=bge-m3` 且安装 `sentence-transformers` 可走本地语义模型。

**可选深度重排**：

```sh
pip install sentence-transformers
export HARNESS_RAG_RERANK_MODEL=BAAI/bge-reranker-base
```

---

## 4. 评测

迷你语料：`evals/rag/fixtures/tiny_corpus/`  
金标查询：`evals/rag/gold_queries.yaml`

```sh
pytest tests/test_writing_mode.py tests/test_writing_guard.py \
  tests/test_rag_bootstrap.py tests/test_rag_retrieval.py -q
```

Python API：

```python
from harness.rag.eval import run_eval
report = run_eval("evals/rag/fixtures/tiny_corpus")
# report["recall_at_k"], report["mrr"]
```

---

## 5. 与 lookup 的分工

| 模式 | 场景 | 数据源 |
|------|------|--------|
| **lookup** | 有没有某论文、联网检索 | fetch / OpenAlex |
| **writing** | 仿写报告章节 | 本地 `files/` RAG |

同一条消息若像「查找论文」则只走 lookup，不走 writing。
