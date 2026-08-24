"""
中文递归文本切分器。

继承自 LangChain 的 RecursiveCharacterTextSplitter，针对中文文本特点
优化了切分策略。核心思路是按中文标点符号的优先级递归切分：

    段落分隔 > 换行 > 句号/感叹号/问号 > 英文句末标点 > 分号 > 逗号

这样可以在保证语义完整性的前提下，将长文本切分为合适大小的块。
"""
import re
from typing import List, Optional, Any
from langchain.text_splitter import RecursiveCharacterTextSplitter
import logging

logger = logging.getLogger(__name__)


def _split_text_with_regex_from_end(
        text: str, separator: str, keep_separator: bool
) -> List[str]:
    """使用正则表达式从末尾开始切分文本。

    当 keep_separator=True 时，将分隔符保留在切分结果中（作为前一段的结尾），
    这样可以避免丢失标点符号。

    Args:
        text: 待切分的文本。
        separator: 正则表达式形式的分隔符。
        keep_separator: 是否保留分隔符在结果中。

    Returns:
        切分后的文本片段列表（已过滤空字符串）。
    """
    if separator:
        if keep_separator:
            # 用括号包裹分隔符模式，re.split 会将分隔符也保留在结果中
            # 例如 re.split("([。！？])", "你好。再见！") -> ["你好", "。", "再见", "！"]
            _splits = re.split(f"({separator})", text)
            # 将分隔符与前一个片段合并：["你好", "。", "再见", "！"] -> ["你好。", "再见！"]
            splits = ["".join(i) for i in zip(_splits[0::2], _splits[1::2])]
            # 如果分隔符数量为奇数，最后一段没有对应的分隔符，直接追加
            if len(_splits) % 2 == 1:
                splits += _splits[-1:]
        else:
            splits = re.split(separator, text)
    else:
        # 没有分隔符时，按单个字符切分
        splits = list(text)
    return [s for s in splits if s != ""]


class ChineseRecursiveTextSplitter(RecursiveCharacterTextSplitter):
    """中文递归文本切分器。

    相比原版 RecursiveCharacterTextSplitter，做了以下适配：
    1. 默认分隔符按中文标点优先级排列
    2. 分隔符支持正则表达式（如 "。|！|？" 同时匹配多种句末标点）
    3. 切分后自动合并过短的片段，并清理多余空行
    """

    def __init__(
            self,
            separators: Optional[List[str]] = None,
            keep_separator: bool = True,
            is_separator_regex: bool = True,
            **kwargs: Any,
    ) -> None:
        """初始化中文递归文本切分器。

        Args:
            separators: 自定义分隔符列表，按优先级从高到低排列。
                默认为段落分隔、换行、中文句末标点、英文句末标点、分号、逗号。
            keep_separator: 是否将分隔符保留在切分结果中，默认 True。
            is_separator_regex: 分隔符是否为正则表达式，默认 True。
            **kwargs: 传递给父类的参数，如 chunk_size、chunk_overlap 等。
        """
        super().__init__(keep_separator=keep_separator, **kwargs)
        # 默认分隔符优先级：段落 > 换行 > 中文句末标点 > 英文句末标点 > 分号 > 逗号
        self._separators = separators or [
            "\n\n",                # 段落分隔（最高优先级）
            "\n",                  # 换行
            "。|！|？",             # 中文句末标点
            r"\.\s|\!\s|\?\s",     # 英文句末标点（后跟空格）
            r"；|;\s",             # 分号
            r"，|,\s"              # 逗号（最低优先级）
        ]
        self._is_separator_regex = is_separator_regex

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        """递归切分文本的核心方法。

        算法流程：
        1. 从分隔符列表中找到当前文本中实际存在的最高优先级分隔符
        2. 用该分隔符切分文本
        3. 对于每个切分片段：
           - 如果长度 < chunk_size，加入"待合并"队列
           - 如果长度 >= chunk_size，先合并队列中的短片段，再对该片段用下一级分隔符递归切分
        4. 最后将所有切分结果中的连续空行替换为单个换行

        Args:
            text: 待切分的文本。
            separators: 按优先级排列的分隔符列表。

        Returns:
            切分后的文本块列表。
        """
        final_chunks = []

        # 第一步：找到当前文本中实际存在的最高优先级分隔符
        separator = separators[-1]  # 默认使用最低优先级的分隔符
        new_separators = []  # 当匹配到某个分隔符后，剩余的更低优先级分隔符
        for i, _s in enumerate(separators):
            _separator = _s if self._is_separator_regex else re.escape(_s)
            if _s == "":
                separator = _s
                break
            # 在文本中搜索该分隔符，如果找到就使用它
            if re.search(_separator, text):
                separator = _s
                new_separators = separators[i + 1:]  # 记录后续更细粒度的分隔符
                break

        # 第二步：用找到的分隔符切分文本
        _separator = separator if self._is_separator_regex else re.escape(separator)
        splits = _split_text_with_regex_from_end(text, _separator, self._keep_separator)

        # 第三步：合并短片段 or 递归切分长片段
        _good_splits = []
        _separator = "" if self._keep_separator else separator
        for s in splits:
            if self._length_function(s) < self._chunk_size:
                # 片段足够短，加入待合并队列
                _good_splits.append(s)
            else:
                # 片段太长，先处理队列中已有的短片段
                if _good_splits:
                    merged_text = self._merge_splits(_good_splits, _separator)
                    final_chunks.extend(merged_text)
                    _good_splits = []
                # 对该长片段进行递归切分
                if not new_separators:
                    # 已经没有更细的分隔符了，直接作为一块
                    final_chunks.append(s)
                else:
                    # 用下一级分隔符递归切分
                    other_info = self._split_text(s, new_separators)
                    final_chunks.extend(other_info)

        # 处理队列中剩余的短片段
        if _good_splits:
            merged_text = self._merge_splits(_good_splits, _separator)
            final_chunks.extend(merged_text)

        # 第四步：清理结果——去掉连续空行、首尾空白、空块
        return [re.sub(r"\n{2,}", "\n", chunk.strip()) for chunk in final_chunks if chunk.strip() != ""]


if __name__ == "__main__":
    # 测试示例：一段中文贸易报告文本
    text_splitter = ChineseRecursiveTextSplitter(
        keep_separator=True,
        is_separator_regex=True,
        chunk_size=150,
        chunk_overlap=10
    )
    ls = [
        """中国对外贸易形势报告（75页）。前 10 个月，一般贸易进出口 19.5 万亿元，增长 25.1%， 比整体进出口增速高出 2.9 个百分点，占进出口总额的 61.7%，较去年同期提升 1.6 个百分点。其中，一般贸易出口 10.6 万亿元，增长 25.3%，占出口总额的 60.9%，提升 1.5 个百分点；进口8.9万亿元，增长24.9%，占进口总额的62.7%， 提升 1.8 个百分点。加工贸易进出口 6.8 万亿元，增长 11.8%， 占进出口总额的 21.5%，减少 2.0 个百分点。其中，出口增 长 10.4%，占出口总额的 24.3%，减少 2.6 个百分点；进口增 长 14.2%，占进口总额的 18.0%，减少 1.2 个百分点。此外， 以保税物流方式进出口 3.96 万亿元，增长 27.9%。其中，出 口 1.47 万亿元，增长 38.9%；进口 2.49 万亿元，增长 22.2%。前三季度，中国服务贸易继续保持快速增长态势。服务 进出口总额 37834.3 亿元，增长 11.6%；其中服务出口 17820.9 亿元，增长 27.3%；进口 20013.4 亿元，增长 0.5%，进口增 速实现了疫情以来的首次转正。服务出口增幅大于进口 26.8 个百分点，带动服务贸易逆差下降 62.9%至 2192.5 亿元。服 务贸易结构持续优化，知识密集型服务进出口 16917.7 亿元， 增长 13.3%，占服务进出口总额的比重达到 44.7%，提升 0.7 个百分点。 二、中国对外贸易发展环境分析和展望 全球疫情起伏反复，经济复苏分化加剧，大宗商品价格 上涨、能源紧缺、运力紧张及发达经济体政策调整外溢等风 险交织叠加。同时也要看到，我国经济长期向好的趋势没有 改变，外贸企业韧性和活力不断增强，新业态新模式加快发 展，创新转型步伐提速。产业链供应链面临挑战。美欧等加快出台制造业回迁计 划，加速产业链供应链本土布局，跨国公司调整产业链供应 链，全球双链面临新一轮重构，区域化、近岸化、本土化、 短链化趋势凸显。疫苗供应不足，制造业"缺芯"、物流受限、 运价高企，全球产业链供应链面临压力。 全球通胀持续高位运行。能源价格上涨加大主要经济体 的通胀压力，增加全球经济复苏的不确定性。世界银行今年 10 月发布《大宗商品市场展望》指出，能源价格在 2021 年 大涨逾 80%，并且仍将在 2022 年小幅上涨。IMF 指出，全 球通胀上行风险加剧，通胀前景存在巨大不确定性。""",
    ]
    for inum, text in enumerate(ls):
        print(inum)
        chunks = text_splitter.split_text(text)
        for chunk in chunks:
            print("="*50)
            print(chunk)
