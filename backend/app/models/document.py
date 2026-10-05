from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from ..database import Base


class Document(Base):
    """PDF 文档模型"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, comment="存储文件名")
    original_name = Column(String(255), nullable=False, comment="原始文件名")
    file_path = Column(String(500), nullable=False, comment="文件路径")
    status = Column(String(50), nullable=False, default="uploading", 
                    comment="状态: uploading/parsing/processed/error")
    total_pages = Column(Integer, default=0, comment="总页数")
    file_size = Column(Integer, default=0, comment="文件大小(字节)")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
