# core/strategy_selector.py 源码
import os 
import sys
# 路径设置：先把 rag_qa 和项目根目录加入 sys.path，再导入项目内模块（base.logger）。
# 否则从其他目录启动时 `from base import logger` 会 ImportError（与 core/vector_store.py 同样的问题）。
current_dir = os.path.dirname(os.path.abspath(__file__))  # core/
rag_qa_path = os.path.dirname(current_dir)                # rag_qa/
project_root = os.path.dirname(rag_qa_path)               # integrated_qa_system/
sys.path.insert(0, rag_qa_path)
sys.path.insert(0, project_root)
# 导入 LangChain 提示模板
from langchain.prompts import PromptTemplate
# 导入日志和配置
from base import logger, Config
# 导入 OpenAI
from openai import OpenAI


class StrategySelector:
    def __init__(self):
        # 初始化 OpenAI 客户端
        self.client = OpenAI(
            api_key=Config().LLM_API_KEY,
            base_url=Config().LLM_BASE_URL
                             )
        # 获取策略选择提示模板
        self.strategy_prompt_template = self._get_strategy_prompt()

    def call_llm(self, prompt):
        # 调用 LLM API
        try:
            # 创建聊天完成请求
            completion = self.client.chat.completions.create(
                model=Config().LLM_MODEL_NAME,
                messages=[
                    {"role": "system", "content": "你是一个有用的助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1
            )
            # 返回完成结果
            return completion.choices[0].message.content if completion.choices else "直接检索"
        except Exception as e:
            # 记录 API 调用失败
            logger.error(f"LLM API 调用失败: {e}")
            # 默认返回直接检索
            return "直接检索"


    def _get_strategy_prompt(self):
        #   定义私有方法，获取策略选择 Prompt 模板
        return PromptTemplate(
            template="""
            你是一个智能助手，负责分析用户查询 {query}，并从以下四种检索增强策略中选择一个最适合的策略，直接返回策略名称，不需要解释过程。

            以下是几种检索增强策略及其适用场景：

            1.  **直接检索：**
                * 描述：对用户查询直接进行检索，不进行任何增强处理。
                * 适用场景：适用于查询意图明确，需要从知识库中检索**特定信息**的问题，例如：
                    * 示例：
                        * 查询：公司新产品的功能清单有哪些？
                        * 策略：直接检索
                    * 查询：数据库的优化方案是什么？
                        * 策略：直接检索
            2.  **假设问题检索（HyDE）：**
                * 描述：使用 LLM 生成一个假设的答案，然后基于假设答案进行检索。
                * 适用场景：适用于查询较为抽象，直接检索效果不佳的问题，例如：
                    * 示例：
                        * 查询：人工智能在智能制造领域的应用有哪些？
                        * 策略：假设问题检索
            3.  **子查询检索：**
                * 描述：将复杂的用户查询拆分为多个简单的子查询，分别检索并合并结果。
                * 适用场景：适用于查询涉及多个实体或方面，需要分别检索不同信息的问题，例如：
                    * 示例：
                        * 查询：比较 Milvus 和 Zilliz Cloud 的优缺点。
                        * 策略：子查询检索
            4.  **回溯问题检索：**
                * 描述：将复杂的用户查询转化为更基础、更易于检索的问题，然后进行检索。
                * 适用场景：适用于查询较为复杂，需要简化后才能有效检索的问题，例如：
                    * 示例：
                        * 查询：我有一个包含 100 亿条记录的数据集，想把它存储到 Milvus 中进行查询。可以吗？
                        * 策略：回溯问题检索

            根据用户查询 {query}，直接返回最适合的策略名称，例如 "直接检索"。不要输出任何分析过程或其他内容。
            """
            ,
            input_variables=["query"],
        )

    #   定义方法，选择检索策略
    def select_strategy(self, query):
        #   调用 LLM 获取检索策略
        strategy = self.call_llm(self.strategy_prompt_template.format(query=query)).strip()
        logger.info(f"为查询 '{query}' 选择的检索策略：{strategy}")
        return strategy

    def _get_analyze_prompt(self):
        #   定义私有方法，获取"问题解析" Prompt 模板
        #   一次调用同时产出：规范查询（去口语化、纠错、补全，供 BM25/检索使用）+
        #   向量检索策略（从四种策略中选一个），提升 BM25 对口语化问题的命中率。
        return PromptTemplate(
            template="""
            你是一个专业的问题解析与检索规划助手。给定用户的原始查询，你需要做两件事：

            任务一：把"规范查询"规范化。
            - 把口语化、含口头禅/错别字/指代不清的查询，改写成规范、完整、适合检索的标准查询。
            - 保留所有技术术语、领域关键词和实体，不要改变查询的本意。
            - 若查询本身已经规范，原样返回即可。
            任务二：从以下四种检索增强策略中选择一个最适合向量检索的策略。
            1. 直接检索：查询意图明确，直接检索特定信息。
            2. 假设问题检索（HyDE）：查询抽象，直接检索效果不佳。
            3. 子查询检索：查询涉及多个实体/方面，需要拆分检索再合并。
            4. 回溯问题检索：查询复杂/口语化，需要简化成更基础的问题再检索。

            用户原始查询: {query}

            请严格按以下两行输出，不要输出其他任何内容：
            规范查询: <改写后的标准查询>
            检索策略: <四种策略之一，如 直接检索>
            """
            ,
            input_variables=["query"],
        )

    #   定义方法：一次 LLM 调用完成"问题解析"——规范化查询 + 选择向量检索策略。
    #   规范化后的查询用于 BM25 快速命中与向量检索，解决口语化问题匹配不到的问题；
    #   返回 (search_query, strategy)，失败时回退 (原始查询, "直接检索")。
    def analyze(self, query):
        try:
            text = self.call_llm(self._get_analyze_prompt().format(query=query))
            search_query, strategy = query, "直接检索"
            for line in (text or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                if "规范查询" in line:
                    seg = line.split(":", 1)[-1].strip()
                    if seg:
                        search_query = seg
                elif "检索策略" in line:
                    seg = line.split(":", 1)[-1].strip().lower()
                    # 归一化策略名到四种之一，无法识别一律按"直接检索"
                    if "回溯" in seg:
                        strategy = "回溯问题检索"
                    elif "子查询" in seg:
                        strategy = "子查询检索"
                    elif "假设" in seg or "hyde" in seg:
                        strategy = "假设问题检索"
                    else:
                        strategy = "直接检索"
            search_query = search_query.strip() or query
            logger.info(f"问题解析：'{query}' -> 规范查询 '{search_query}'，策略 '{strategy}'")
            return search_query, strategy
        except Exception as e:
            logger.error(f"问题解析失败，回退原始查询: {e}")
            return query, "直接检索"

if __name__ == '__main__':
    ss = StrategySelector()
    ss.select_strategy('你好吗')
