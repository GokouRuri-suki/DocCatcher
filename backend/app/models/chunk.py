from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from ..database import Base


class TextChunk(Base):
    """文本分块模型 - 用于存储 PDF 解析后的文本块"""
    __tablename__ = "text_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False, comment="分块序号")
    content = Column(Text, nullable=False, comment="文本内容")
    page_start = Column(Integer, nullable=False, comment="起始页码")
    page_end = Column(Integer, nullable=False, comment="结束页码")
    section_title = Column(String(500), nullable=True, comment="所属章节标题")
    char_count = Column(Integer, default=0, comment="字符数")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
