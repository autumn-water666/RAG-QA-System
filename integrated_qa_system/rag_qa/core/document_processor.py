"""
文档处理器 —— 负责文档的加载和分层切分。

整体流程：
    目录遍历 → 按文件扩展名分发到对应 Loader → 加载为 Document 对象
    → 分层切分（父块 + 子块）→ 返回带元数据的子块列表

支持的文件格式：
    - 纯文本：.txt, .md（使用 LangChain TextLoader）
    - 文档类：.pdf, .doc, .docx, .ppt, .pptx, .rtf, .epub 等 20+ 种
      （统一使用 AnyDocLoader，基于 anydoc 库转换为 Markdown）

切分策略：
    采用父子分层切分，父块（1500字）保留完整上下文，子块（500字）用于精确检索。
    检索时用子块匹配问题，命中后可拿到 parent_content 作为更完整的上下文。
"""
import os
import hashlib
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import MarkdownTextSplitter
from datetime import datetime
import sys
from langchain_core.documents import Document

# 路径设置：将 rag_qa 和项目根目录加入 sys.path，确保模块导入正常
current_dir = os.path.dirname(os.path.abspath(__file__))  # core/ 目录
rag_qa_path = os.path.dirname(current_dir)                # rag_qa/ 目录
sys.path.insert(0, rag_qa_path)
project_root = os.path.dirname(rag_qa_path)               # integrated_qa_system/ 目录
sys.path.insert(0, project_root)
from edu_document_loaders import AnyDocLoader
from edu_text_spliter import ChineseRecursiveTextSplitter
from base import logger, Config

conf = Config()

# ============================================================
# 文件类型 → Loader 映射表
# ============================================================
# .txt 和 .md 是纯文本，直接用 TextLoader 读取即可。
# 其余 20+ 种格式全部交给 AnyDocLoader，由 anydoc 库
# 根据文件内容自动检测格式并转换为 Markdown。
document_loaders = {
    ".txt": TextLoader,
    ".md": TextLoader,
    # ---- 文档类（anydoc 统一转换为 Markdown）----
    ".pdf": AnyDocLoader,
    ".doc": AnyDocLoader,
    ".docx": AnyDocLoader,
    ".docm": AnyDocLoader,   # Word 宏文档
    ".ppt": AnyDocLoader,
    ".pptx": AnyDocLoader,
    ".pptm": AnyDocLoader,   # PPT 宏文档
    ".pps": AnyDocLoader,    # PPS 放映格式
    ".ppsx": AnyDocLoader,
    ".ppsm": AnyDocLoader,   # PPS 宏文档
    ".odt": AnyDocLoader,    # OpenDocument 文本
    ".ods": AnyDocLoader,    # OpenDocument 表格
    ".odp": AnyDocLoader,    # OpenDocument 演示
    ".rtf": AnyDocLoader,    # 富文本格式
    ".epub": AnyDocLoader,   # 电子书格式
    ".csv": AnyDocLoader,    # 逗号分隔值
    ".xls": AnyDocLoader,
    ".xlsx": AnyDocLoader,
    ".xlsm": AnyDocLoader,   # Excel 宏文档
    ".xlsb": AnyDocLoader,   # Excel 二进制格式
}


def load_documents_from_directory(directory_path) -> list[Document]:
    """从指定目录递归加载所有支持格式的文档，并为每个文档添加元数据。

    流程：
        1. 递归遍历 directory_path 下所有子目录
        2. 对每个文件，检查扩展名是否在 document_loaders 映射表中
        3. 如果支持，实例化对应的 Loader 并加载文档内容
        4. 为每个加载的 Document 添加 source（学科类别）、file_path、timestamp 元数据
        5. 如果加载失败，记录错误日志并跳过该文件

    Args:
        directory_path: 数据目录路径，目录名用于提取学科类别（如 "ai_data" → "ai"）。

    Returns:
        加载后的 LangChain Document 对象列表。
    """
    documents = []
    supported_extensions = document_loaders.keys()
    # 从目录名提取学科类别，例如 "ai_data" → "ai"，"math_data" → "math"
    source = os.path.basename(directory_path).replace("_data", "")

    # 递归遍历目录下所有文件
    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_extension = os.path.splitext(file_path)[1].lower()

            # 只处理支持的文件类型
            if file_extension in supported_extensions:
                try:
                    loader_class = document_loaders[file_extension]
                    # .txt 和 .md 是纯文本，须显式指定 UTF-8 编码。
                    # 否则 TextLoader 自动检测会落到系统默认编码（Windows 下是 GBK），
                    # 遇到 UTF-8 编码的中文文件会抛 UnicodeDecodeError。
                    if file_extension in (".txt", ".md"):
                        loader = loader_class(file_path, encoding="utf-8")
                    else:
                        loader = loader_class(file_path)

                    loaded_docs = loader.load()

                    # 为每个文档添加元数据
                    for doc in loaded_docs:
                        doc.metadata["source"] = source          # 学科类别
                        doc.metadata["file_path"] = file_path    # 文件完整路径
                        doc.metadata["timestamp"] = datetime.now().isoformat()  # 加载时间
                        # 稳定文档 ID：基于文件绝对路径哈希，跨批次一致，
                        # 供知识库按文档删除 / 去重 / 详情定位（父块 id 里的序号不可靠）。
                        doc.metadata["doc_id"] = hashlib.md5(
                            os.path.abspath(file_path).encode('utf-8')).hexdigest()
                        # 文档标题：取文件名（去扩展名），块继承后前端列表直接用
                        doc.metadata["title"] = os.path.splitext(
                            os.path.basename(file_path))[0]

                    documents.extend(loaded_docs)
                    logger.info(f"成功加载文件: {file_path}")
                except Exception as e:
                    logger.error(f"加载文件 {file_path} 失败: {str(e)}")
            else:
                logger.warning(f"不支持的文件类型: {file_path}")
    return documents


def _split_single_document(doc, doc_index, parent_chunk_size=conf.PARENT_CHUNK_SIZE,
                           child_chunk_size=conf.CHILD_CHUNK_SIZE,
                           chunk_overlap=conf.CHUNK_OVERLAP):
    """把单个已加载 Document 切成父子子块，返回子块列表。

    抽取自 process_documents 的内层循环，供「批量加载」与「单文件上传」复用，
    保证两条路径的切分行为完全一致。

    Args:
        doc: 单个已元数据的 Document。
        doc_index: 该文档在批次的序号，用于生成 doc_0_parent_x_child_y 前缀。

    Returns:
        该文档的所有子块（带 parent_id/parent_content/id 元数据）。
    """
    file_extension = os.path.splitext(doc.metadata.get("file_path", ""))[1].lower()
    is_markdown = (file_extension == ".md")
    parent_splitter = ChineseRecursiveTextSplitter(
        chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap
    )
    child_splitter = ChineseRecursiveTextSplitter(
        chunk_size=child_chunk_size, chunk_overlap=chunk_overlap
    )
    # Markdown 专用切分器：能识别标题层级，按结构切分
    markdown_parent_splitter = MarkdownTextSplitter(
        chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap
    )
    markdown_child_splitter = MarkdownTextSplitter(
        chunk_size=child_chunk_size, chunk_overlap=chunk_overlap
    )
    parent_splitter_to_use = markdown_parent_splitter if is_markdown else parent_splitter
    child_splitter_to_use = markdown_child_splitter if is_markdown else child_splitter

    child_chunks = []
    parent_docs = parent_splitter_to_use.split_documents([doc])
    for j, parent_doc in enumerate(parent_docs):
        parent_id = f"doc_{doc_index}_parent_{j}"
        sub_chunks = child_splitter_to_use.split_documents([parent_doc])
        for k, sub_chunk in enumerate(sub_chunks):
            sub_chunk.metadata["parent_id"] = parent_id
            sub_chunk.metadata["parent_content"] = parent_doc.page_content
            sub_chunk.metadata["id"] = f"{parent_id}_child_{k}"
            child_chunks.append(sub_chunk)
    return child_chunks


def _attach_doc_metadata(doc, file_path, source):
    """为单个加载的 Document 补齐学科/路径/时间戳/稳定 ID 元数据。"""
    doc.metadata["source"] = source
    doc.metadata["file_path"] = file_path
    doc.metadata["timestamp"] = datetime.now().isoformat()
    # 稳定文档 ID：基于文件绝对路径哈希，跨批次一致
    doc.metadata["doc_id"] = hashlib.md5(os.path.abspath(file_path).encode('utf-8')).hexdigest()
    doc.metadata["title"] = os.path.splitext(os.path.basename(file_path))[0]


def process_file(file_path: str, source: str,
                 parent_chunk_size=conf.PARENT_CHUNK_SIZE,
                 child_chunk_size=conf.CHILD_CHUNK_SIZE,
                 chunk_overlap=conf.CHUNK_OVERLAP) -> list[Document]:
    """处理单个文件（上传场景），返回子块列表。

    Args:
        file_path: 单个文件的绝对路径（已保存到本地）。
        source: 学科类别（如 "ai"），写入每个子块的 source 字段。

    Returns:
        该文件切分后的子块列表；文件类型不支持时抛 ValueError。
    """
    file_extension = os.path.splitext(file_path)[1].lower()
    if file_extension not in document_loaders:
        raise ValueError(f"不支持的文件类型: {file_extension}")
    # 与 load_documents_from_directory 保持一致：.txt/.md 显式 UTF-8，
    # 其余交给 AnyDocLoader 自动识别
    if file_extension in (".txt", ".md"):
        loader = document_loaders[file_extension](file_path, encoding="utf-8")
    else:
        loader = document_loaders[file_extension](file_path)

    docs = loader.load()
    for doc in docs:
        _attach_doc_metadata(doc, file_path, source)

    child_chunks = []
    for i, doc in enumerate(docs):
        child_chunks.extend(_split_single_document(
            doc, i, parent_chunk_size, child_chunk_size, chunk_overlap))
    logger.info(f"单文件处理完成: {file_path}，共 {len(child_chunks)} 个子块")
    return child_chunks


def process_documents(directory_path, parent_chunk_size=conf.PARENT_CHUNK_SIZE,
                     child_chunk_size=conf.CHILD_CHUNK_SIZE,
                     chunk_overlap=conf.CHUNK_OVERLAP)  -> list[Document]:
    """处理文档并进行分层切分，返回子块结果。

    采用父子分层切分策略：
        原始文档 → 父块切分（大粒度，保留上下文）→ 子块切分（小粒度，精确匹配）

    父块的作用：在检索时提供更完整的上下文，避免子块切分后丢失语义。
    子块的作用：用于向量检索匹配用户问题，粒度更小，匹配更精确。

    切分器选择规则：
        - .md 文件使用 MarkdownTextSplitter（按标题/段落结构切分）
        - 其他格式使用 ChineseRecursiveTextSplitter（按中文标点递归切分）

    输出的每个子块携带以下元数据：
        - id: 唯一标识，格式为 "doc_{文档索引}_parent_{父块索引}_child_{子块索引}"
        - parent_id: 所属父块的 ID
        - parent_content: 父块的完整文本（用于检索后补充上下文）
        - source: 学科类别
        - file_path: 来源文件路径
        - timestamp: 加载时间

    Args:
        directory_path: 数据目录路径。
        parent_chunk_size: 父块大小（字符数），默认 1500。
        child_chunk_size: 子块大小（字符数），默认 500。
        chunk_overlap: 切分重叠区域大小（字符数），默认 200。

    Returns:
        所有子块组成的列表，每个元素是带元数据的 LangChain Document 对象。
    """
    # 第一步：加载目录下所有文档
    documents = load_documents_from_directory(directory_path)
    logger.info(f"加载的文档数量: {len(documents)}")

    # 第二步：逐文档进行分层切分（统一走 _split_single_document）
    child_chunks = []
    for i, doc in enumerate(documents):
        logger.info(
            f"处理文档: {doc.metadata['file_path']}, "
            f"使用切分器: {'Markdown' if os.path.splitext(doc.metadata.get('file_path', ''))[1].lower() == '.md' else 'ChineseRecursive'}"
        )
        child_chunks.extend(_split_single_document(
            doc, i, parent_chunk_size, child_chunk_size, chunk_overlap))

    logger.info(f"子块数量: {len(child_chunks)}")
    return child_chunks


if __name__ == '__main__':
    chunks = process_documents(
        '/Users/ligang/PycharmProjects/LLM/ITCAST_EduRAG/data/ai_data',
        conf.PARENT_CHUNK_SIZE,
        conf.CHILD_CHUNK_SIZE,
        conf.CHUNK_OVERLAP,
    )
    print(chunks)
