from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, Date, JSON
from sqlalchemy.sql import func
from ..database import Base


class StudyPlan(Base):
    """学习规划模型"""
    __tablename__ = "study_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    title = Column(String(500), nullable=False, comment="标题")
    description = Column(Text, nullable=True, comment="描述")
    total_days = Column(Integer, default=0, comment="总天数")
    start_date = Column(Date, nullable=True, comment="开始日期")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class StudyPlanItem(Base):
    """学习项目模型"""
    __tablename__ = "study_plan_items"
    
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("study_plans.id"), nullable=False)
    day_number = Column(Integer, nullable=False, comment="第几天")
    title = Column(String(500), nullable=False, comment="标题")
    tasks = Column(Text, nullable=True, comment="任务描述")
    knowledge_point_ids = Column(JSON, nullable=True, comment="关联知识点ID列表")
    completed = Column(Boolean, default=False, comment="是否完成")
    order = Column(Integer, default=0, comment="排序")
