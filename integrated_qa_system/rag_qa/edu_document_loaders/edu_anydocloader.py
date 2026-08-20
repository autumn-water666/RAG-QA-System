from typing import Iterator
from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader
import anydoc


class AnyDocLoader(BaseLoader):
    """使用 anydoc 将文档转换为 Markdown 的通用 Loader。"""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def lazy_load(self) -> Iterator[Document]:
        md = anydoc.to_markdown(self.file_path)
        yield Document(page_content=md, metadata={"source": self.file_path})
