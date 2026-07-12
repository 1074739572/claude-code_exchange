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
load_skill("thesis-writing")   # 同样会触发索引
rag_search query="引言 编写目的 段落结构"
write_file path="output/01_引言.md" ...
```

---

## 3. 工具

| 工具 | 作用 |
|------|------|
| `rag_index path="files"` | 手动重建索引 |
| `rag_status` | 查看 sources / chunk 数 |
| `rag_search` | BM25 检索（非向量语义） |

环境变量：

| 变量 | 默认 | 含义 |
|------|------|------|
| `HARNESS_WRITING_GUARD` | `1` | 写 output 前必须 rag_search |
| `HARNESS_RAG_HIT_CHARS` | `1500` | 每条命中 chunk 最大字符 |

---

## 4. 评测

```sh
pytest tests/test_writing_mode.py tests/test_writing_guard.py tests/test_rag_bootstrap.py tests/test_rag_retrieval.py -q
```

迷你语料：`evals/rag/fixtures/tiny_corpus/`（可进 git）。

---

## 5. 与 lookup 的分工

| 模式 | 场景 | 数据源 |
|------|------|--------|
| **lookup** | 有没有某论文、联网检索 | fetch / OpenAlex |
| **writing** | 仿写报告章节 | 本地 `files/` RAG |

同一条消息若像「查找论文」则只走 lookup，不走 writing。
