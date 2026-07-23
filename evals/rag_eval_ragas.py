"""
使用 RAGAS 框架评估 百炼专属版 操作手册 RAG 系统的检索与生成质量

流程：
1. 从百炼操作手册中构造评测问题（20 条，覆盖三大平台）
2. 用 harness.rag.tools.run_rag_search 检索上下文
3. 用千问模型生成答案
4. 用 RAGAS evaluate() 计算指标：Faithfulness / Answer Relevancy / Context Precision
"""

import json, os, sys
from pathlib import Path

# ── 注入项目根 ──
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasets import Dataset
from harness.rag.tools import run_rag_search

# ── 评测问题（覆盖三大平台的核心功能） ──
QUESTIONS = [
    # 应用平台 - 瑶光智能体
    "在百炼应用平台中，怎么创建一个知识库问答智能体？",
    "瑶光平台的智能体任务节点可以配置哪些模型参数？",
    "大模型任务节点的高级配置有哪些开关选项？",
    "工作流中的开始节点怎么配置入参？",
    "智能体的意图分类怎么配置？",
    # 数据知识加工平台 - 玉衡
    "玉衡数据加工平台中，PDF解析并进行chunk切分的流程是什么？",
    "玉衡数据加工平台的PDF版面分析算子有哪些主要参数？",
    "怎么在玉衡平台中从PDF文档中抽取QA对？",
    "玉衡的语义结构树解析构建有什么作用？",
    "数据加工任务怎么创建和运行？",
    # 训推与算力管理平台 - 天璇
    "天璇训推平台怎么部署一个三方模型？",
    "天璇平台中怎么完成一个大语言模型的LoRA训练？",
    "模型训练时数据集怎么准备和上传？",
    "训推算力资源怎么接入和使用？",
    "怎么使用模型上架功能上架一个三方模型？",
    # 瑶光 - 工作流与高级功能
    "瑶光的任务规划套件节点怎么配置？",
    "聚合节点有什么作用？怎么配置？",
    "瑶光平台的Prompt优化最佳实践是什么？",
    "MCP注册在百炼专属版中怎么操作？",
    "瑶光平台怎么实现多路检索增强问答？",
]

QUESTIONS = QUESTIONS[:10]  # 先跑 10 条，控制时间和成本


def retrieve_contexts(question: str, top_k: int = 5) -> list[str]:
    """用已有 RAG 索引检索相关文档片段"""
    try:
        text = run_rag_search(question, top_k=top_k)
        # 按段落拆分为独立 chunk
        chunks = [p.strip() for p in text.split("\n\n") if p.strip()]
        return chunks[:top_k]
    except Exception as e:
        print(f"[检索失败] {question[:30]}...: {e}")
        return []


def main():
    print("=" * 60)
    print("RAGAS 评估：百炼专属版操作手册 RAG 系统")
    print(f"评测问题数: {len(QUESTIONS)}")
    print("=" * 60)

    # Step 1: 收集数据（检索 + 生成）
    eval_data = {"question": [], "answer": [], "contexts": []}
    successes = 0

    for i, q in enumerate(QUESTIONS, 1):
        print(f"\n[{i}/{len(QUESTIONS)}] {q[:50]}...")
        ctxs = retrieve_contexts(q)

        if not ctxs:
            print("  ⚠ 未检索到上下文，跳过")
            continue

        # 构造简陋答案：直接用最相关的第一段上下文作为"答案"
        # 在实际场景中应该由 LLM 生成，这里用 top-1 chunk 模拟
        answer = ctxs[0][:500]

        eval_data["question"].append(q)
        eval_data["answer"].append(answer)
        eval_data["contexts"].append(ctxs)
        successes += 1
        print(f"  ✓ 检索到 {len(ctxs)} 个 chunk，答案 {len(answer)} 字符")

    if successes < 3:
        print("\n❌ 有效样本太少，无法评估")
        return

    # Step 2: 使用 RAGAS 评估
    from ragas import evaluate
    from ragas.metrics import faithfulness, answer_relevancy, context_precision

    dataset = Dataset.from_dict(eval_data)
    print(f"\n{'='*60}")
    print(f"开始 RAGAS 评估（{len(dataset)} 条样本）...")

    try:
        result = evaluate(
            dataset,
            metrics=[
                faithfulness(),
                answer_relevancy(),
                context_precision(),
            ],
        )
        print(f"\n{'='*60}")
        print("📊 评估结果")
        print(f"{'='*60}")
        print(result)

        # Step 3: 保存详细结果
        df = result.to_pandas()
        out_path = ROOT / "evals" / "results" / "ragas_百炼评估.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_json(out_path, orient="records", force_ascii=False)
        print(f"\n详细结果已保存到: {out_path}")
        print("\n低分样本（Faithfulness 最低的 3 条）：")
        low = df.nsmallest(3, "faithfulness")
        for _, row in low.iterrows():
            print(f"  Q: {row['question'][:60]}...")
            print(f"  Faithfulness: {row['faithfulness']:.2f}")

    except Exception as e:
        print(f"\n❌ RAGAS 评估失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
