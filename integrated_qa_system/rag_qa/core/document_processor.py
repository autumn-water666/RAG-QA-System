# 这个脚本讲义的代码架构图没有体现，需要进行补充
import os
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders.markdown import UnstructuredMarkdownLoader
from langchain.text_splitter import MarkdownTextSplitter
from datetime import datetime
import sys
# 获取当前文件所在目录的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
# print(f'current_dir--》{current_dir}')
# 获取core文件所在的目录的绝对路径
rag_qa_path = os.path.dirname(current_dir)
# print(f'rag_qa_path--》{rag_qa_path}')
sys.path.insert(0, rag_qa_path)
# 获取根目录文件所在的绝对位置
project_root = os.path.dirname(rag_qa_path)
sys.path.insert(0, project_root)
from edu_document_loaders import OCRPDFLoader, OCRDOCLoader, OCRPPTLoader, OCRIMGLoader
from base import logger, Config

conf = Config()
# 定义支持的文件类型及其对应的加载器字典
document_loaders = {
    # 文本文件使用 TextLoader
    ".txt": TextLoader,
    # PDF 文件使用 OCRPDFLoader
    ".pdf": OCRPDFLoader,
    # Word 文件使用 OCRDOCLoader
    ".docx": OCRDOCLoader,
    # PPT 文件使用 OCRPPTLoader
    ".ppt": OCRPPTLoader,
    # PPTX 文件使用 OCRPPTLoader
    ".pptx": OCRPPTLoader,
    # JPG 文件使用 OCRIMGLoader
    ".jpg": OCRIMGLoader,
    # PNG 文件使用 OCRIMGLoader
    ".png": OCRIMGLoader,
    # Markdown 文件使用 UnstructuredMarkdownLoader
    ".md": UnstructuredMarkdownLoader
}
# 定义函数，从指定文件夹加载多种类型文件并添加元数据
def load_documents_from_directory(directory_path):
    # 初始化空列表，用于存储加载的文档
    documents = []
    # 获取支持的文件扩展名集合
    supported_extensions = document_loaders.keys()
    # print(f'supported_extensions--》{supported_extensions}')
    # 从目录名提取学科类别（如 "ai_data" -> "ai"）
    # print(f'1---》{os.path.basename(directory_path)}')
    source = os.path.basename(directory_path).replace("_data", "")
    # print(f'source-->{source}')
    # 遍历指定目录及其子目录
    for root, _, files in os.walk(directory_path):
        # print(f'root---》{root}')
        # print(f'files---》{files}')
        # 遍历当前目录下的所有文件
        for file in files:
            # 构造文件的完整路径
            file_path = os.path.join(root, file)
            # print(f'file_path--》{file_path}')
            # print(os.path.splitext(file_path))
            # 获取文件扩展名并转换为小写
            file_extension = os.path.splitext(file_path)[1].lower()
            # print(f'file_extension--》{file_extension}')
            # 检查文件类型是否在支持的扩展名列表中
            if file_extension in supported_extensions:
                # 使用 try-except 捕获加载过程中的异常
                try:
                    # 根据文件扩展名获取对应的加载器类
                    loader_class = document_loaders[file_extension]
                    # 实例化加载器对象，传入文件路径
                    if file_extension == ".txt":
                        loader = loader_class(file_path, encoding="utf-8")
                    else:
                        loader = loader_class(file_path)
                    # 调用加载器加载文档内容，返回文档列表
                    loaded_docs = loader.load()
                    # print(f'loaded_docs--》{loaded_docs}')
                    # print(f'loaded_docs--》{len(loaded_docs)}')
                    for doc in loaded_docs:
                        # 为文档添加学科类别元数据
                        doc.metadata["source"] = source
                        # 为文档添加文件路径元数据
                        doc.metadata["file_path"] = file_path
                        # 为文档添加当前时间戳元数据
                        doc.metadata["timestamp"] = datetime.now().isoformat()
                    # print(f'loaded_docs111--》{loaded_docs}')
                    documents.extend(loaded_docs)
                    # 记录成功加载文件的日志
                    logger.info(f"成功加载文件: {file_path}")
                except Exception as e:
                    logger.error(f"加载文件 {file_path} 失败: {str(e)}")
            # 如果文件类型不在支持列表中
            else:
                # 记录警告日志，提示不支持的文件类型
                logger.warning(f"不支持的文件类型: {file_path}")
    # 返回加载的所有文档列表
    return documents

if __name__ == '__main__':
    directory_path = '/Users/ligang/Desktop/EduRAG课堂资料/codes/integrated_qa_system/rag_qa/data/ai_data'
    documents = load_documents_from_directory(directory_path)
    print(documents)

