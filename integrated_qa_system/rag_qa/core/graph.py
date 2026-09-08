# -*- coding:utf-8 -*-
# core/graph.py
"""基于 LangGraph 的问答编排层。

把原来散落在 rag_system.generate_answer / new_main.query 里的手写 if/else 路由，
显式化为一个 StateGraph 状态机：

    START → classify ──通用知识──→ generate ──→ END
                     └─专业咨询──→ bm25 ──有答案──→ set_bm25_answer ──→ END
                                    │
                                  needs_rag
                                    │
                                    ├──需要→ retrieve ──→ generate ──→ END
                                    └──不需要→ set_not_found ──→ END

节点只复用现有的完成模块（QueryClassifier / BM25Search / StrategySelector /
VectorStore 混合检索 / RAGPrompts），不重写任何检索与生成逻辑：
- classify       → rag_system.query_classifier
- bm25           → bm25_search.search（快速命中直答）
- retrieve       → rag_system.strategy_selector + retrieve_and_merge
- generate       → rag_system.rag_prompt + rag_system.llm
"""
import os
import sys
from typing import TypedDict, Optional, List

# 路径引导：先把 core、rag_qa、项目根目录加入 sys.path，再导入项目内模块
current_dir = os.path.dirname(os.path.abspath(__file__))  # core/
rag_qa_path = os.path.dirname(current_dir)                # rag_qa/
project_root = os.path.dirname(rag_qa_path)               # integrated_qa_system/
sys.path.insert(0, current_dir)
sys.path.insert(0, rag_qa_path)
sys.path.insert(0, project_root)

from langgraph.graph import StateGraph, START, END
from langgraph.config import get_stream_writer
from base import Config, logger

conf = Config()

# 与 RAG 默认提示词中"无法回答"分支保持一致：无上下文兜底回复
NOT_FOUND_ANSWER = "未找到答案"


class QState(TypedDict):
    """图的状态。所有节点都读写它，作为节点间传参的统一通道。"""
    query: str
    source_filter: Optional[str]
    history: Optional[List[dict]]          # [{"question":..., "answer":...}, ...]
    category: str                          # 通用知识 | 专业咨询
    bm25_answer: Optional[str]             # BM25 快速命中的答案
    need_rag: bool                         # BM25 判定是否需要 RAG
    strategy: Optional[str]                # 检索策略名
    context_docs: List                     # 检索到的父文档
    answer: str                            # 最终答案


def _history_context(history):
    """把多轮历史拼成文本，无则返回空串。"""
    if not history:
        return ""
    return "\n".join(
        f"用户: {item['question']}\n助手: {item['answer']}" for item in history
    )


def build_qa_graph(rag_system, bm25_search=None):
    """把已有的 RAG 部件组装成一个 LangGraph 编排图。

    Args:
        rag_system: RAGSystem 实例（必含 query_classifier / strategy_selector /
                    retrieve_and_merge / rag_prompt / llm）
        bm25_search: BM25Search 实例或 None。为 None 时跳过 BM25 快速命中，直接走 RAG。

    Returns:
        编译好的 CompiledStateGraph
    """
    rag_prompt = rag_system.rag_prompt
    query_classifier = rag_system.query_classifier
    strategy_selector = rag_system.strategy_selector
    llm = rag_system.llm

    # ---- 节点 ----

    def classify(state):
        logger.info(f"[graph] 查询分类: '{state['query']}'")
        state["category"] = query_classifier.predict_category(state["query"])
        logger.info(f"[graph] 分类结果: {state['category']}")
        return state

    def bm25(state):
        if bm25_search is None:
            state["need_rag"] = True
            return state
        answer, need_rag = bm25_search.search(state["query"], threshold=0.85)
        state["bm25_answer"] = answer
        state["need_rag"] = need_rag
        return state

    def retrieve(state):
        query = state["query"]
        src_filter = state["source_filter"]
        strategy = (strategy_selector.select_strategy(query)
                    if strategy_selector else "直接检索")
        docs = rag_system.retrieve_and_merge(query, source_filter=src_filter, strategy=strategy)
        state["strategy"] = strategy
        state["context_docs"] = docs
        logger.info(f"[graph] 策略 '{strategy}' 检索到 {len(docs)} 个文档")
        return state

    def generate(state):
        hc = _history_context(state["history"])
        if state["category"] == "通用知识":
            # 通用知识：不检索，直接用历史（若有）当上下文
            context = hc
            logger.info("[graph] 通用知识，直接调用 LLM")
        else:
            # 专业咨询：到这里说明已经 retrieve 过，拼检索上下文
            docs = state["context_docs"]
            context = "\n\n".join(doc.page_content for doc in docs) if docs else ""
            if hc:
                context = f"对话历史:\n{hc}\n\n当前检索到的上下文:\n{context}"
            logger.info(f"[graph] 构建上下文完成，含 {len(docs)} 个文档块")
        prompt = rag_prompt.format(
            context=context, question=state["query"], phone=conf.CUSTOMER_SERVICE_PHONE
        )
        # 逐 token 写入 LangGraph custom 流（stream_mode="custom" 时被消费）；
        # 非流式模式下 get_stream_writer 是空操作，此时仅通过 state["answer"] 返回完整答案。
        writer = get_stream_writer()
        result = llm(prompt)
        if isinstance(result, str):
            full = result
            writer(result)
        elif hasattr(result, "__iter__"):
            parts = []
            for token in result:
                if not token:
                    continue
                parts.append(str(token))
                writer(str(token))
            full = "".join(parts)
        else:
            full = str(result)
            writer(full)
        state["answer"] = full
        return state

    def set_bm25_answer(state):
        state["answer"] = state["bm25_answer"]
        return state

    def set_not_found(state):
        state["answer"] = NOT_FOUND_ANSWER
        return state

    # ---- 条件路由 ----

    def route_after_classify(state):
        return "generate" if state["category"] == "通用知识" else "bm25"

    def route_after_bm25(state):
        if state.get("bm25_answer"):
            return "set_bm25_answer"
        return "retrieve" if state.get("need_rag", True) else "set_not_found"

    # ---- 组图 ----
    graph = StateGraph(QState)
    graph.add_node("classify", classify)
    graph.add_node("bm25", bm25)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_node("set_bm25_answer", set_bm25_answer)
    graph.add_node("set_not_found", set_not_found)

    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify", route_after_classify,
        {"generate": "generate", "bm25": "bm25"}
    )
    graph.add_conditional_edges(
        "bm25", route_after_bm25,
        {"set_bm25_answer": "set_bm25_answer",
         "retrieve": "retrieve",
         "set_not_found": "set_not_found"}
    )
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    graph.add_edge("set_bm25_answer", END)
    graph.add_edge("set_not_found", END)

    return graph.compile()


def run_qa_graph(rag_system, query, source_filter=None, history=None,
                 bm25_search=None) -> dict:
    """便捷入口：构建图并执行一次查询，返回最终状态（含 answer）。"""
    compiled = build_qa_graph(rag_system, bm25_search=bm25_search)
    return compiled.invoke(_to_state_input(query, source_filter, history))


def _to_state_input(query, source_filter=None, history=None) -> dict:
    """把 query 参数规整成图的状态输入。"""
    return {
        "query": query,
        "source_filter": source_filter,
        "history": history,
    }


def _stream_from_compiled(compiled, query, source_filter=None, history=None):
    """从已编译的图以 (token, is_complete) 形式流式产出，契约与 new_main.query() 一致。

    - generate 节点每个 token 经 LangGraph custom 流产出 (token, False)
    - 非 LLM 直答终端（BM25 命中 / 未找到）一次性产出整串 (answer, False)
    - 全部结束产出 ("", True) 作为结束标记
    """
    inp = _to_state_input(query, source_filter, history)
    terminal_nodes = {"set_bm25_answer", "set_not_found"}
    saw_token = False
    for mode, chunk in compiled.stream(inp, stream_mode=["updates", "custom"]):
        if mode == "custom":
            yield chunk, False
            saw_token = True
        elif mode == "updates":
            for node, update in (chunk or {}).items():
                if node in terminal_nodes:
                    yield update.get("answer", ""), False
                    yield "", True
                    return
    if saw_token:
        yield "", True


def stream_qa_graph(rag_system, query, source_filter=None, history=None,
                    bm25_search=None):
    """便捷入口：构建图并流式产出 (token, is_complete)。"""
    compiled = build_qa_graph(rag_system, bm25_search=bm25_search)
    yield from _stream_from_compiled(compiled, query, source_filter, history)


if __name__ == "__main__":
    # 离线冒烟测试：模拟一个通用知识查询，只走 classify → generate，无需 Milvus/MySQL
    class FakeRAG:
        def __init__(self):
            from query_classifier import QueryClassifier
            from strategy_selector import StrategySelector
            from prompts import RAGPrompts
            self.query_classifier = QueryClassifier()
            self.strategy_selector = StrategySelector()
            self.rag_prompt = RAGPrompts.rag_prompt()

        def llm(self, prompt):
            for ch in "你好，这是 LangGraph 编排层的流式测试":
                yield ch

        def retrieve_and_merge(self, query, source_filter=None, strategy=None):
            return []

    state = run_qa_graph(FakeRAG(), "什么是人工智能？", bm25_search=None)
    print("invoke answer:", state["answer"])

    # 流式路径
    parts = []
    for token, complete in stream_qa_graph(FakeRAG(), "什么是人工智能？", bm25_search=None):
        parts.append(token)
    print("stream joined:", "".join(parts))