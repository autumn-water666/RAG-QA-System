import os
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import MarkdownTextSplitter
from datetime import datetime
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
rag_qa_path = os.path.dirname(current_dir)
sys.path.insert(0, rag_qa_path)
project_root = os.path.dirname(rag_qa_path)
sys.path.insert(0, project_root)
from edu_document_loaders import AnyDocLoader
from edu_text_spliter import ChineseRecursiveTextSplitter
from base import logger, Config

conf = Config()

# 定义支持的文件类型及其对应的加载器字典
document_loaders = {
    # 文本文件使用 TextLoader
    ".txt": TextLoader,
    # Markdown 文件使用 TextLoader
    ".md": TextLoader,
    # 以下格式全部使用 AnyDocLoader（anydoc 库统一转换为 Markdown）
    ".pdf": AnyDocLoader,
    ".doc": AnyDocLoader,
    ".docx": AnyDocLoader,
    ".docm": AnyDocLoader,
    ".ppt": AnyDocLoader,
    ".pptx": AnyDocLoader,
    ".pptm": AnyDocLoader,
    ".pps": AnyDocLoader,
    ".ppsx": AnyDocLoader,
    ".ppsm": AnyDocLoader,
    ".odt": AnyDocLoader,
    ".ods": AnyDocLoader,
    ".odp": AnyDocLoader,
    ".rtf": AnyDocLoader,
    ".epub": AnyDocLoader,
    ".csv": AnyDocLoader,
    ".xls": AnyDocLoader,
    ".xlsx": AnyDocLoader,
    ".xlsm": AnyDocLoader,
    ".xlsb": AnyDocLoader,
}


def load_documents_from_directory(directory_path):
    """从指定文件夹加载多种类型文件并添加元数据。"""
    documents = []
    supported_extensions = document_loaders.keys()
    # 从目录名提取学科类别（如 "ai_data" -> "ai"）
    source = os.path.basename(directory_path).replace("_data", "")

    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_extension = os.path.splitext(file_path)[1].lower()
            if file_extension in supported_extensions:
                try:
                    loader_class = document_loaders[file_extension]
                    if file_extension == ".txt":
                        loader = loader_class(file_path, encoding="utf-8")
                    else:
                        loader = loader_class(file_path)
                    loaded_docs = loader.load()
                    for doc in loaded_docs:
                        doc.metadata["source"] = source
                        doc.metadata["file_path"] = file_path
                        doc.metadata["timestamp"] = datetime.now().isoformat()
                    documents.extend(loaded_docs)
                    logger.info(f"成功加载文件: {file_path}")
                except Exception as e:
                    logger.error(f"加载文件 {file_path} 失败: {str(e)}")
            else:
                logger.warning(f"不支持的文件类型: {file_path}")
    return documents


def process_documents(directory_path, parent_chunk_size=conf.PARENT_CHUNK_SIZE,
                     child_chunk_size=conf.CHILD_CHUNK_SIZE,
                     chunk_overlap=conf.CHUNK_OVERLAP):
    """处理文档并进行分层切分，返回子块结果。"""
    documents = load_documents_from_directory(directory_path)
    logger.info(f"加载的文档数量: {len(documents)}")

    # 初始化父块和子块分词器（通用）
    parent_splitter = ChineseRecursiveTextSplitter(chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap)
    child_splitter = ChineseRecursiveTextSplitter(chunk_size=child_chunk_size, chunk_overlap=chunk_overlap)
    # 初始化 Markdown 专用分词器
    markdown_parent_splitter = MarkdownTextSplitter(chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap)
    markdown_child_splitter = MarkdownTextSplitter(chunk_size=child_chunk_size, chunk_overlap=chunk_overlap)

    child_chunks = []
    for i, doc in enumerate(documents):
        file_extension = os.path.splitext(doc.metadata.get("file_path", ""))[1].lower()

        # 选择切分器：Markdown 文件用 MarkdownTextSplitter，其他用 ChineseRecursiveTextSplitter
        is_markdown = (file_extension == ".md")
        parent_splitter_to_use = markdown_parent_splitter if is_markdown else parent_splitter
        child_splitter_to_use = markdown_child_splitter if is_markdown else child_splitter
        logger.info(f"处理文档: {doc.metadata['file_path']}, 使用切分器: {'Markdown' if is_markdown else 'ChineseRecursive'}")

        # 使用父块分词器将文档切分为父块
        parent_docs = parent_splitter_to_use.split_documents([doc])
        for j, parent_doc in enumerate(parent_docs):
            parent_id = f"doc_{i}_parent_{j}"
            parent_doc.metadata["parent_id"] = parent_id
            parent_doc.metadata["parent_content"] = parent_doc.page_content

            # 使用子块分词器将父块切分为子块
            sub_chunks = child_splitter_to_use.split_documents([parent_doc])
            for k, sub_chunk in enumerate(sub_chunks):
                sub_chunk.metadata["parent_id"] = parent_id
                sub_chunk.metadata["parent_content"] = parent_doc.page_content
                sub_chunk.metadata["id"] = f"{parent_id}_child_{k}"
                child_chunks.append(sub_chunk)

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
