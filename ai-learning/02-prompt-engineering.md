# Day 3-4：Prompt Engineering 提示工程

## 一、核心原则

### 1. 清晰具体的指令
- ❌ "翻译这段文字"
- ✅ "将以下英文翻译为中文，保持专业语气，不增译不删译"

### 2. 提供足够的上下文
- System Prompt 设定角色
- 给出示例（Few-shot）
- 明确输出格式

### 3. 分步推理（Chain-of-Thought）
- 让模型逐步思考再给出答案
- 显著提升复杂推理能力

---

## 二、Prompt 结构

### 标准结构
```
System: 你是一名 [角色]，你需要 [任务目标]。规则：[约束条件]。
User: [具体问题 / 输入]
Assistant: [期望的输出格式]
```

### 实际示例
```python
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": """
你是一个 AI 应用开发的面试官。你需要：
1. 根据用户的问题给出详细的解答
2. 附带代码示例
3. 标注重点和易错点
"""},
        {"role": "user", "content": "什么是 RAG？"}
    ]
)
```

---

## 三、Few-shot Learning（小样本学习）

给模型 1-3 个示例，让它模仿模式：

```python
messages = [
    {"role": "system", "content": "将用户输入分类为：技术、非技术"},
    {"role": "user", "content": "什么是 API 网关？"},
    {"role": "assistant", "content": "技术"},
    {"role": "user", "content": "今天天气真好"},
    {"role": "assistant", "content": "非技术"},
    {"role": "user", "content": "如何优化 RAG 系统？"}  # 模型应输出 "技术"
]
```

---

## 四、高级技巧

### 4.1 Chain-of-Thought (CoT)
**原理**：让模型逐步推理，而非直接给出答案
```python
prompt = """
问题：一个池子有 3 个进水口，每个进水口每小时进水 10 吨，
还有一个出水口每小时出水 5 吨。4 小时后池子里有多少吨水？

请逐步分析：
"""
```

### 4.2 结构化输出（JSON Mode）
```python
response = client.chat.completions.create(
    model="gpt-4-1106-preview",
    response_format={"type": "json_object"},
    messages=[
        {"role": "system", "content": "输出 JSON 格式"},
        {"role": "user", "content": "列出 3 种 Agent 设计模式"}
    ]
)
```

### 4.3 角色设定（Persona）
```python
system_prompt = """
你是顶尖的 AI 系统架构师，拥有 10 年经验。
回答时请：
1. 先分析需求
2. 给出架构方案
3. 分析优缺点
4. 给出推荐方案
"""
```

### 4.4 输出约束
```python
system_prompt = """
输出格式严格如下：
- 标题：...
- 概要：不超过 50 字
- 步骤：用 1. 2. 3. 列出
- 代码：用 ```python 包裹
"""
```

---

## 五、常见问题与调试

### 模型输出不一致
- 降低 Temperature（设到 0-0.3）
- 增加约束条件
- 用 Few-shot 固定模式

### 输出格式不符合
- 用 JSON Mode
- 在 System Prompt 中明确格式
- 加后处理（正则提取 / 格式校验）

### 模型"幻觉"
- 减少开放性问题
- 引用外部知识（RAG）
- 让模型先确认再回答

---

## 六、LangChain 中的 PromptTemplate

```python
from langchain.prompts import ChatPromptTemplate

template = ChatPromptTemplate.from_messages([
    ("system", "你是{role}专家，请用{style}风格回答"),
    ("user", "{input}")
])

messages = template.format_messages(
    role="AI 应用开发",
    style="简洁",
    input="什么是 Agent？"
)
```

---

## 面试常问

1. **CoT 为什么有效？** → 模拟人类逐步推理，减少跳跃性错误
2. **Few-shot 和 Zero-shot 的区别？** → Few-shot 给示例、Zero-shot 不给
3. **如何减少幻觉？** → RAG + 约束提示 + 后处理验证
4. **System Prompt 的作用？** → 设定角色、行为规范、输出格式
5. **Temperature 对 Prompt 的影响？** → 高 Temperature 降低指令遵循度

---

## 今日练习
1. 用 3 种不同 Prompt 风格问同一个问题，对比输出
2. 用 Few-shot 让模型做分类任务
3. 用 JSON Mode 获取结构化输出
