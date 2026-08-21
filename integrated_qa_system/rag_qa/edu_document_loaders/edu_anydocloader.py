"""
通用文档加载器 —— 基于 anydoc 库。

anydoc 是一个 Rust 实现的文档转换库，支持将 PDF、Word、PPT、Excel、
OpenDocument、RTF、EPUB、CSV 等 20+ 种格式统一转换为 GitHub-Flavored Markdown。
底层根据文件内容自动检测格式，无需 OCR，纯本地运行。

本模块将 anydoc 封装为 LangChain 的 BaseLoader，使其可以接入
document_processor 的统一加载流程。
"""
from typing import Iterator
from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader
import anydoc


class AnyDocLoader(BaseLoader):
    """使用 anydoc 将任意文档格式转换为 Markdown 的通用 Loader。

    支持的格式包括：PDF, DOC, DOCX, DOCM, PPT, PPTX, PPTM, PPS, PPSX,
    PPSM, ODT, ODS, ODP, RTF, EPUB, CSV, XLS, XLSX, XLSM, XLSB。

    与之前的 OCR Loader 相比：
    - 无需安装 OCR 模型（rapidocr_paddle / rapidocr_onnxruntime）
    - 无需安装 OpenCV、PyMuPDF 等重依赖
    - 转换速度极快（毫秒级），由 Rust 实现
    - 图片内容直接忽略，只提取文字部分转为 Markdown
    """

    def __init__(self, file_path: str) -> None:
        """初始化加载器。

        Args:
            file_path: 待加载文档的文件路径。
        """
        self.file_path = file_path

    def lazy_load(self) -> Iterator[Document]:
        """惰性加载文档内容。

        调用 anydoc.to_markdown() 将文档转为 Markdown 文本，
        包装为 LangChain Document 对象后逐个 yield。
        """
        md = anydoc.to_markdown(self.file_path)
        yield Document(page_content=md, metadata={"source": self.file_path})
