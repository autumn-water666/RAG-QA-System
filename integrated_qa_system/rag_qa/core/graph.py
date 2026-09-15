# -*- coding:utf-8 -*-
# core/graph.py
"""基于 LangGraph 的问答编排层。

把原来散落在 rag_system.generate_answer / new_main.query 里的手写 if/else 路由，
显式化为一个 StateGraph 状态机：

    START → classify ──通用知识──→ generate ──→ END
                     └─专业咨询──→ analyze ──→ bm25 ──有答案──→ generate(LLM仲裁标准答案) ──→ END
                                                │
                                              needs_rag（未命中）
                                                │
                                                ├──需要→ retrieve ──→ generate ──→ END
                                                └──不需要→ set_not_found ──→ END

节点只复用现有的完成模块（QueryClassifier / BM25Search / StrategySelector /
VectorStore 混合检索 / RAGPrompts），不重写任何检索与生成逻辑：
- classify       → rag_system.query_classifier
- analyze        → strategy_selector.analyze（问题解析前置：一次 LLM 产出规范查询 + 检索策略，
                    BM25 与向量检索都用规范查询，口语化问题也能命中）
- bm25           → bm25_search.search(规范查询)（命中时标准答案作为上下文交 LLM 仲裁，不再直答）
- retrieve       → rag_system.retrieve_and_merge（用 analyze 预设的策略，不重复调 LLM）
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
    search_query: Optional[str]            # 问题解析后的规范查询（供 BM25/检索）
    bm25_answer: Optional[str]             # BM25 快速命中的答案
    need_rag: bool                         # BM25 判定是否需要 RAG
    strategy: Optional[str]                # 检索策略名（analyze 阶段选出）
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

    # 定义节点函数，对问题进行意图识别
    def classify(state):
        logger.info(f"[graph] 查询分类: '{state['query']}'")
        state["category"] = query_classifier.predict_category(state["query"])
        logger.info(f"[graph] 分类结果: {state['category']}")
        return state

    def analyze(state):
        # 问题解析前置：一次 LLM 调用产出"规范查询 + 检索策略"，放在 BM25/检索之前，
        # 让 BM25 用规范化后的好问题匹配，口语化/指代不清的查询也能命中。
        query = state["query"]
        if strategy_selector is not None:
            search_query, strategy = strategy_selector.analyze(query)
        else:
            search_query, strategy = query, None
        state["search_query"] = search_query or query
        state["strategy"] = strategy
        logger.info(f"[graph] 问题解析: '{query}' -> 规范查询 '{state['search_query']}'，策略 '{strategy}'")
        return state

    def bm25(state):
        # 意图识别关闭时 classify/analyze 节点被移除，直接进到这里，category 未初始化。
        # 兜底按"专业咨询"处理（会继续走检索），保证 generate 分支逻辑稳定。
        state.setdefault("category", "专业咨询")
        # 优先用 analyze 阶段产出的规范查询；无（意图识别关闭或解析失败）则回退原始查询。
        query = state.get("search_query") or state["query"]
        if bm25_search is None:
            state["need_rag"] = True
            return state
        answer, need_rag = bm25_search.search(query, threshold=conf.BM25_THRESHOLD)
        state["bm25_answer"] = answer
        state["need_rag"] = need_rag
        logger.info(f"[graph] BM25 用规范查询检索: '{query}'")
        return state

    def retrieve(state):
        # BM25 未命中才走到此处；用 analyze 解析出的规范查询 + 预设策略检索，
        # 不再重复调用 LLM 选策略（retrieve_and_merge 收到 strategy 就不会再选）。
        query = state.get("search_query") or state["query"]
        src_filter = state["source_filter"]
        strategy = state.get("strategy") or "直接检索"
        docs = rag_system.retrieve_and_merge(query, source_filter=src_filter, strategy=strategy)
        state["context_docs"] = docs
        logger.info(f"[graph] 策略 '{strategy}' 检索到 {len(docs)} 个文档")
        return state

    def generate(state):
        hc = _history_context(state["history"])
        if state["category"] == "通用知识":
            # 通用知识：不检索，直接用历史（若有）当上下文
            context = hc
            logger.info("[graph] 通用知识，直接调用 LLM")
        elif state.get("bm25_answer"):
            # BM25 命中：标准答案降级为"证据上下文"交给 LLM 仲裁，
            # 不再硬返回，由 LLM 判断采纳还是纠偏/拒答（提升准确率）
            context = (f"数据库标准答案（可能已过时或不相关，请核对其能正确回答用户问题后再采用，"
                       f"不符则依据你的知识纠正或回复无法回答）:\n{state['bm25_answer']}")
            if hc:
                context = f"对话历史:\n{hc}\n\n{context}"
            logger.info("[graph] BM25 命中，交由 LLM 仲裁")
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

    def set_not_found(state):
        state["answer"] = NOT_FOUND_ANSWER
        return state

    # ---- 条件路由 ----

    def route_after_classify(state):
        return "generate" if state["category"] == "通用知识" else "analyze"

    def route_after_bm25(state):
        if state.get("bm25_answer"):
            # BM25 命中不再硬返回，改走 generate：标准答案降级为上下文，
            # 由 LLM 做最终仲裁（采纳 / 纠偏 / 拒答），提升准确率。
            return "generate"
        return "retrieve" if state.get("need_rag", True) else "set_not_found"

    # ---- 组图 ----
    # 意图识别开关：conf.USE_INTENT_CLASSIFY=True 走"通用知识/专业咨询" classify 路由；
    # 为 False 则不注册 classify 节点，但仍保留 analyze 问题解析（规范化口语化查询 +
    # 选策略，让 BM25/检索不因口语化而漏接），所有问题一律走检索(RAG)。
    graph = StateGraph(QState)
    graph.add_node("analyze", analyze)       # 问题解析：规范查询 + 选策略，独立于意图识别
    if conf.USE_INTENT_CLASSIFY:
        graph.add_node("classify", classify)
        graph.add_edge(START, "classify")
    else:
        # 关闭意图识别：跳过 BERT 分类，直接从问题解析开始，再进 BM25
        graph.add_edge(START, "analyze")
    graph.add_node("bm25", bm25)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_node("set_not_found", set_not_found)
    graph.add_edge("analyze", "bm25")

    if conf.USE_INTENT_CLASSIFY:
        graph.add_conditional_edges(
            "classify", route_after_classify,
            {"generate": "generate", "analyze": "analyze"}
        )
    graph.add_conditional_edges(
        "bm25", route_after_bm25,
        {"generate": "generate",
         "retrieve": "retrieve",
         "set_not_found": "set_not_found"}
    )
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
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


def _build_sources(docs) -> list:
    """把检索到的父文档映射为引用溯源 Source[]（契约见 docs/API.md §4）。

    title 优先 metadata 里的 title / file_path 文件名，缺省回退「文档片段N」。
    url 指向前端文档详情路由 #/kb/{doc_id}，doc_id 优先，回退 parent_id。
    snippet 取正文前 80 字符，正文为空时回退父块内容。
    """
    sources = []
    for idx, doc in enumerate(docs, start=1):
        md = doc.metadata or {}
        subject = md.get("source") or "未知"
        raw_title = md.get("title") or md.get("file_path") or ""
        title = raw_title.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or f"文档片段{idx}"
        doc_id = md.get("doc_id") or md.get("parent_id") or f"doc_{idx}"
        snippet = (doc.page_content or "").strip()[:80]
        if not snippet:
            snippet = (md.get("parent_content") or "")[:80]
        # 检索落点是父块：带 parent_id 作精确锚点，DocPage 按此定位并高亮对应切块
        parent_id = md.get("parent_id")
        sources.append({
            "index": idx,
            "title": title,
            "subject": subject,
            "snippet": snippet,
            "parent_id": parent_id,
            "url": f"#/kb/{doc_id}?c={parent_id}" if parent_id else f"#/kb/{doc_id}",
        })
    return sources


def _stream_from_compiled(compiled, query, source_filter=None, history=None):
    """从已编译的图以 (token, is_complete, sources) 形式流式产出。

    - generate 节点每个 token 经 LangGraph custom 流产出 (token, False, [])
    - 非 LLM 直答终端（BM25 命中 / 未找到）一次性产出整串 (answer, False, [])
    - RAG 路径 retrieve 后持有 context_docs，结束时首个 is_complete=True 的
      产出携带 sources（引用溯源），前端据此渲染「参考来源」
    - 全部结束产出 ("", True, sources) 作为结束标记
    """
    inp = _to_state_input(query, source_filter, history)
    terminal_nodes = {"set_not_found"}
    context_docs = []
    saw_token = False
    for mode, chunk in compiled.stream(inp, stream_mode=["updates", "custom"]):
        if mode == "custom":
            yield chunk, False, []
            saw_token = True
        elif mode == "updates":
            for node, update in (chunk or {}).items():
                if isinstance(update, dict) and update.get("context_docs"):
                    context_docs = update["context_docs"]
                if node in terminal_nodes:
                    yield update.get("answer", ""), False, []
                    yield "", True, _build_sources(context_docs)
                    return
    if saw_token:
        yield "", True, _build_sources(context_docs)


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
    for token, complete, sources in stream_qa_graph(FakeRAG(), "什么是人工智能？", bm25_search=None):
        parts.append(token)
    print("stream joined:", "".join(parts))