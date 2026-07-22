# Day 1-2：LLM 基础 + Embedding

## 一、LLM 调用原理

### 核心概念
- **LLM（大语言模型）**：基于 Transformer 架构的文本生成模型，核心是 "下一个 token 预测"
- **Token**：LLM 的最小文本单位（≈0.75 个中文词 / ≈0.25 个英文词）
- **Temperature**：控制输出的随机性，0 为确定性，1 为随机
- **Top_p**（Nucleus Sampling）：累积概率截止，控制输出多样性
- **System Prompt**：给模型的系统级指令，设定行为规范
- **Chat Completion API**：最主流的 LLM 调用方式

### API 调用流程（示例）
```python
from openai import OpenAI

client = OpenAI(api_key="your-key")

response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "你是 AI 助手"},
        {"role": "user", "content": "解释什么是 token"}
    ],
    temperature=0.7,
    max_tokens=500
)

print(response.choices[0].message.content)
```

### 常用模型
- **OpenAI**：GPT-4o, GPT-4o-mini
- **Claude**：Claude-3.5-Sonnet, Claude-3-Haiku
- **国产**：DeepSeek-V3, Qwen2.5, GLM-4
- **开源**：Llama-3, Mistral, Qwen2

---

## 二、Embedding（嵌入向量）

### 什么是 Embedding
- 将文本/图像转为 **固定长度的浮点向量**（如 1536 维）
- 语义相近的文本在向量空间中距离更近
- 核心度量：**余弦相似度**（Cosine Similarity）

### 常见 Embedding 模型
| 模型 | 维度 | 特点 |
|------|------|------|
| OpenAI text-embedding-3-small | 512/1536 | 性价比高 |
| OpenAI text-embedding-3-large | 256/1024/3072 | 质量最高 |
| BGE (BAAI) | 768/1024 | 国产优秀 |
| text2vec-large-chinese | 1024 | 中文优化 |
| m3e | 768 | 中文嵌入模型 |

### 代码示例
```python
from openai import OpenAI

client = OpenAI()
response = client.embeddings.create(
    model="text-embedding-3-small",
    input="我喜欢学习 AI 应用开发"
)

vector = response.data[0].embedding  # 1536 维向量
print(f"向量维度: {len(vector)}")
print(f"前 5 个值: {vector[:5]}")
```

### 计算相似度
```python
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

vec1 = np.array([0.1, 0.2, 0.3, ...])  # 文本1 的 embedding
vec2 = np.array([0.4, 0.5, 0.6, ...])  # 文本2 的 embedding

similarity = cosine_similarity([vec1], [vec2])[0][0]
print(f"相似度: {similarity}")
```

---

## 三、Token 管理

### 计费概念
- 输入 Token + 输出 Token 均计费
- 一般按 **每 1K Token** 计费
- 不同模型价格差异巨大（GPT-4 约是 GPT-3.5 的 20 倍）

### Token 计数
```python
import tiktoken

# GPT-4 使用的 tokenizer
enc = tiktoken.encoding_for_model("gpt-4")
text = "你好，今天我们来学习 AI 应用开发"
tokens = enc.encode(text)
print(f"Token 数量: {len(tokens)}")  # 中文约 0.75 词/token
```

---

## 四、上下文窗口（Context Window）

- **上下文窗口**：模型一次能处理的最大 Token 数
- 主流模型窗口：8K / 32K / 128K / 200K
- **关键问题**：长上下文 ≠ 长文本理解能力（"lost in the middle" 问题）
- 解决方案：RAG（后续学习）+ 结构化提示

---

## 面试常问问题

1. **LLM 的生成原理是什么？** → 自回归生成，逐个预测下一个 token
2. **Temperature 和 Top_p 的区别？** → Temperature 缩放概率分布，Top_p 截断低概率 token
3. **为什么需要 Embedding？** → 文本无法直接计算相似度，向量空间可以
4. **余弦相似度和欧氏距离的区别？** → 余弦关注方向（语义），欧氏关注绝对距离
5. **上下文窗口越大越好吗？** → 不，存在"lost in the middle"问题，成本也更高

---

## 今日练习

1. 调用任意 LLM API 完成一次对话
2. 用 Embedding 模型计算两个句子的相似度
3. 对比不同 Temperature 的输出差异
