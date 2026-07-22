# Day 5-7：RAG（检索增强生成）

## 一、什么是 RAG

**RAG = Retrieval-Augmented Generation**

核心思想：**先检索外部知识，再让 LLM 基于检索结果生成回答。**

解决了 LLM 的三大问题：
1. **知识过时** — 模型训练数据截止日期之后的信息
2. **幻觉** — 模型编造不存在的事实
3. **缺乏私有知识** — 企业内部文档、用户个人数据

---

## 二、RAG 完整流程

```
用户输入
    │
    ▼
┌─────────────┐    ┌─────────────────┐
│   Query      │───▶│  Embedding Model │
│  (问题 Embed)│    │  向量化         │
└─────────────┘    └────────┬────────┘
                            │
                            ▼
                    ┌─────────────────┐
                    │  向量数据库      │
                    │  (FAISS/Pinecone) │
                    │  相似度检索      │
                    └────────┬────────┘
                            │
                            ▼
                    ┌─────────────────┐
                    │  检索结果        │
                    │  (Top-K 段落)    │
                    └────────┬────────┘
                            │
                            ▼
                    ┌─────────────────┐
                    │  Prompt + 上下文  │
                    │  组装 prompt     │
                    └────────┬────────┘
                            │
                            ▼
                    ┌─────────────────┐
                    │      LLM        │
                    │   生成回答       │
                    └─────────────────┘
```

---

## 三、索引阶段（Indexing）

### 3.1 文档加载（Document Loading）
```python
from langchain_community.document_loaders import (
    TextLoader, PyPDFLoader, 
    WebBaseLoader, CSVLoader
)

loader = PyPDFLoader("document.pdf")
documents = loader.load()
```

### 3.2 文本分割（Chunking）— 最关键的优化点
```python
from langchain.text_splitter import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter
)

# 最常用的分割器
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,       # 每块 500 token
    chunk_overlap=50,     # 重叠 50 token（保留上下文）
    separators=["\n\n", "\n", "。", "！", "？", " ", ""]
)

chunks = text_splitter.split_documents(documents)
```

**Chunking 策略对比**：
| 策略 | 适用场景 | chunk_size |
|------|---------|-----------|
| 固定大小分割 | 通用 | 300-500 token |
| 语义分割 | 长文档 | 按段落 |
| 递归分割（推荐） | 混合内容 | 500-1000 token |
| 按 Markdown 结构 | 技术文档 | 按标题 |

### 3.3 向量化 + 存储
```python
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# 创建向量库
vectorstore = FAISS.from_documents(
    documents=chunks,
    embedding=embeddings
)

# 持久化
vectorstore.save_local("faiss_index")

# 加载
vectorstore = FAISS.load_local("faiss_index", embeddings)
```

---

## 四、检索阶段（Retrieval）

### 4.1 基础检索
```python
retriever = vectorstore.as_retriever(
    search_type="similarity",  # 相似度检索
    search_kwargs={"k": 4}     # 返回 Top-4
)

docs = retriever.invoke("什么是 RAG？")
```

### 4.2 高级检索策略

#### MMR（最大边际相关性）
```python
retriever = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={
        "k": 4,
        "fetch_k": 20,     # 先取 20 个候选
        "lambda_mult": 0.5  # 多样性参数
    }
)
# MMR 在相关性和多样性之间做平衡
```

#### HyDE（假设文档嵌入）
- 先用 LLM 生成一个"假设回答"
- 用假设回答的 Embedding 去检索
- 能更好地匹配语义

#### Self-Query（自查询）
```python
from langchain.chains.query_constructor import attribute_info

# 定义元数据字段
metadata_field_info = [
    attribute_info(
        name="source",
        description="信息来源",
        type="string",
    ),
    attribute_info(
        name="date",
        description="日期",
        type="date",
    ),
]

self_query_retriever = SelfQueryRetriever.from_llm(
    llm=llm,
    vectorstore=vectorstore,
    document_contents="AI 应用开发文档",
    metadata_field_info=metadata_field_info
)
```

---

## 五、生成阶段（Generation）

### 5.1 组装 Prompt
```python
rag_prompt = """
你是一个 AI 助手。基于以下上下文回答用户问题。
如果上下文中没有相关信息，直接说"我不知道"。

上下文：
{context}

问题：{question}
回答："""
```

### 5.2 完整的 RAG 链
```python
from langchain.chains import RetrievalQA

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",  # 全部塞入 context
    retriever=retriever,
    chain_type_kwargs={"prompt": rag_prompt}
)

answer = qa_chain.invoke("什么是 RAG？")
```

---

## 六、RAG 评估与优化

### 6.1 评估指标
| 指标 | 含义 | 测量方式 |
|------|------|---------|
| **检索准确率** | 检索结果是否包含答案 | 人工标注 |
| **生成质量** | 回答是否准确、完整 | LLM 评测 |
| **Faithfulness** | 回答是否忠于检索内容 | 事实一致性检查 |
| **Answer Relevance** | 回答是否针对问题 | 相关性评分 |

### 6.2 常见问题优化

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 检索不相关 | Chunk 太大/太小 | 调整 chunk_size、用语义分割 |
| 回答遗漏信息 | Top-K 太少 | 增加 K 值、优化检索策略 |
| 回答包含无关内容 | 噪音太多 | 加 Reranker、MMR |
| 回答不准确 | Embedding 能力不足 | 换更好的 Embedding 模型 |

### 6.3 Reranking（重排序）
```python
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker

# 使用交叉编码器重排序
compressor = CrossEncoderReranker(
    model_name="BAAI/bge-reranker-v2-m3"
)

compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=retriever
)
```

---

## 七、高级 RAG 架构

### RAG-Fusion
- 用多个搜索词（Query Expansion）
- 综合多个检索结果
- 用 RRF（互惠排名融合）排序

### Agentic RAG
- Agent 决定何时检索、检索什么
- 支持多轮检索
- 能自我纠错

### Graph RAG
- 用知识图谱补充向量检索
- 适合需要关系推理的场景
- 微软提出，处理多跳问题效果更好

---

## 面试常问

1. **RAG 和 Fine-tuning 的区别？** → RAG 动态检索外部知识，微调更新模型参数
2. **Chunk Size 怎么选？** → 取决于文档类型和检索粒度，一般 300-1000 token
3. **什么是"Lost in the Middle"？** → LLM 对中间位置的上下文注意力降低
4. **为什么需要 Reranker？** → 向量检索只能粗排，Reranker 用交叉编码精排
5. **Hybrid Search 是什么？** → 关键词搜索 + 向量搜索结合

---

## 今日练习
1. 用 PDF 加载器读取文档，建立 RAG 系统
2. 对比不同 chunk_size 的检索效果
3. 加入 Reranker 看效果提升
4. 用 HyDE 策略对比普通检索
