# Day 8-10：Agent 架构

## 一、什么是 Agent

**Agent = LLM + 规划 + 工具 + 记忆**

核心区别：
- **普通 LLM**：一问一答，纯文本输出
- **Agent**：能自主决策、调用工具、规划步骤、完成任务

### Agent 核心能力
1. **感知**：理解用户意图和当前环境
2. **规划**：拆解任务、制定步骤
3. **行动**：调用工具、执行操作
4. **记忆**：记住历史状态
5. **反思**：根据结果调整策略

---

## 二、ReAct 模式（Reasoning + Acting）

### 核心思想
**交替进行推理（Reasoning）和行动（Acting）**，每一步先思考再行动。

### 工作流程
```
用户问题
    │
    ▼
Thought: 我需要先理解用户的需求
Action: search_knowledge_base("RAG 定义")
    │
    ▼
Observation: RAG 是检索增强生成...
    │
    ▼
Thought: 有了定义，我需要用它来回答问题
Action: 生成回答
    │
    ▼
Final Answer: RAG 是一种...
```

### 代码实现
```python
import json
from openai import OpenAI

client = OpenAI()

def agent_react(query):
    messages = [
        {"role": "system", "content": """你是一个 AI Agent。请按以下格式回应：
        
Thought: 思考当前需要做什么
Action: 工具名称(参数)
Observation: 工具返回结果
...（可重复多轮）
Thought: 我有足够的信息了
Final Answer: 最终回答

可用工具：
- search_knowledge_base(query): 搜索知识库
- calculate(expression): 计算数学表达式
"""},
        {"role": "user", "content": query}
    ]
    
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0
    )
    
    return response.choices[0].message.content
```

---

## 三、Tool Calling（函数调用）

### 3.1 Function Calling 定义
```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "北京今天天气怎么样？"}
    ],
    tools=tools,
    tool_choice="auto"  # auto / required / none
)

# 模型会返回 tool_calls
tool_call = response.choices[0].message.tool_calls[0]
print(f"调用的函数: {tool_call.function.name}")
print(f"参数: {tool_call.function.arguments}")
```

### 3.2 执行工具函数
```python
def execute_tool_call(tool_call):
    """执行工具调用"""
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    
    if name == "get_weather":
        return get_weather(**args)
    elif name == "search_knowledge":
        return search_knowledge(**args)
    # ... 更多工具

def get_weather(city: str) -> str:
    # 实际调用天气 API
    return f"{city} 天气：晴，温度 25°C"
```

### 3.3 多轮工具调用
```python
def agent_with_tools(user_query):
    messages = [{"role": "user", "content": user_query}]
    
    while True:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            tools=tools
        )
        
        message = response.choices[0].message
        messages.append(message)
        
        # 检查是否有工具调用
        if message.tool_calls:
            for tool_call in message.tool_calls:
                result = execute_tool_call(tool_call)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
        else:
            # 没有工具调用，返回最终结果
            return message.content
```

---

## 四、Planning（任务规划）

### 4.1 任务分解
```python
planning_prompt = """
任务：{task}

请将上述任务分解为可执行的子步骤，每个步骤：
1. 做什么
2. 用什么工具
3. 期望得到什么结果

按顺序列出步骤：
"""

# 示例输出
"""
步骤1: 搜索"RAG"的定义 → 工具: search_knowledge
步骤2: 查找 RAG 的实现方案 → 工具: search_knowledge  
步骤3: 综合信息编写回答 → 工具: write_response
"""
```

### 4.2 动态规划（Plan-and-Execute）
```python
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.chains.plan_and_execute import PlanAndExecute

# 规划器：制定步骤
# 执行器：按步骤执行
# 支持动态调整计划
```

### 4.3 ReAct vs Plan-and-Execute
| 模式 | 特点 | 适用场景 |
|------|------|---------|
| ReAct | 边想边做、灵活调整 | 简单到中等复杂任务 |
| Plan-and-Execute | 先计划后执行 | 复杂多步骤任务 |
| Tree-of-Thought | 多路径探索 | 需要权衡的决策 |

---

## 五、Agent 设计模式

### 5.1 Single Agent
- 一个 LLM 完成所有任务
- 简单，但能力有限

### 5.2 Multi-Agent
- 多个 Agent 协作
- 每个 Agent 有专门角色

```python
# 多 Agent 示例
class ResearchAgent:
    """负责检索信息"""
    def search(self, query): ...

class WriterAgent:
    """负责撰写内容"""
    def write(self, context, style): ...

class ReviewerAgent:
    """负责审核质量"""
    def review(self, content): ...

# 编排流程
research_agent = ResearchAgent()
writer_agent = WriterAgent()
reviewer_agent = ReviewerAgent()

# 工作流
info = research_agent.search("RAG 优化方案")
draft = writer_agent.write(info, "技术文档")
feedback = reviewer_agent.review(draft)
```

### 5.3 Supervisor Agent
```python
class SupervisorAgent:
    """管理多个子 Agent"""
    
    def delegate_task(self, task):
        # 分析任务类型
        task_type = self.analyze(task)
        
        # 分派给合适的 Agent
        if task_type == "research":
            return research_agent.handle(task)
        elif task_type == "code":
            return coding_agent.handle(task)
        elif task_type == "writing":
            return writer_agent.handle(task)
```

---

## 六、Agent 评估

### 关键指标
- **任务完成率**：是否达成目标
- **工具调用准确率**：选对工具 + 参数正确
- **步数效率**：用最少步骤完成任务
- **错误恢复率**：出错了能否自愈

### 常见失败原因
1. **工具幻觉**：调用不存在的工具
2. **循环卡死**：反复调用同一工具无进展
3. **信息过载**：上下文太长导致混乱
4. **忘记目标**：多轮后偏离原始任务

---

## 面试常问

1. **Agent 和传统 Chatbot 的区别？** → Agent 能自主规划、调用工具、记忆上下文
2. **ReAct 模式的核心是什么？** → 推理与行动交替，每一步先思考再行动
3. **Function Calling 的原理？** → 模型输出结构化 JSON，系统解析后执行对应函数
4. **Multi-Agent 有什么挑战？** → 通信开销、任务冲突、协调复杂
5. **Agent 如何做错误恢复？** → 重试机制 + 反思回退 + 人工接管

---

## 今日练习
1. 用 Function Calling 实现天气查询 Agent
2. 实现一个 ReAct 模式的检索 Agent
3. 设计一个多 Agent 协作的写作系统
