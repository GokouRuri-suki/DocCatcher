from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base


class KnowledgePoint(Base):
    """知识点模型"""
    __tablename__ = "knowledge_points"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    title = Column(String(500), nullable=False, comment="标题")
    description = Column(Text, nullable=True, comment="描述")
    content = Column(Text, nullable=True, comment="详细内容")
    parent_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=True, comment="父知识点ID")
    level = Column(Integer, default=1, comment="层级: 1=章, 2=节, 3=知识点")
    order = Column(Integer, default=0, comment="排序")
    page_numbers = Column(String(200), nullable=True, comment="相关页码，如 '1-5, 8'")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    parent = relationship("KnowledgePoint", remote_side=[id], backref="children")
    relations_as_source = relationship("KnowledgeRelation", foreign_keys="KnowledgeRelation.source_id", back_populates="source")
    relations_as_target = relationship("KnowledgeRelation", foreign_keys="KnowledgeRelation.target_id", back_populates="target")


class KnowledgeRelation(Base):
    """知识点关系模型"""
    __tablename__ = "knowledge_relations"
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=False)
    relation_type = Column(String(50), nullable=False, comment="关系类型: prerequisite/related/contains")
    description = Column(String(500), nullable=True, comment="关系描述")
    
    # 关系
    source = relationship("KnowledgePoint", foreign_keys=[source_id], back_populates="relations_as_source")
    target = relationship("KnowledgePoint", foreign_keys=[target_id], back_populates="relations_as_target")
