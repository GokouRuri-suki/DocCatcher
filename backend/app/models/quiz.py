from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, Float, JSON
from sqlalchemy.sql import func
from ..database import Base


class Quiz(Base):
    """测验模型"""
    __tablename__ = "quizzes"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    title = Column(String(500), nullable=False, comment="标题")
    description = Column(Text, nullable=True, comment="描述")
    question_count = Column(Integer, default=0, comment="题目数量")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class QuizQuestion(Base):
    """测验题目模型"""
    __tablename__ = "quiz_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=True)
    question_type = Column(String(50), nullable=False, 
                          comment="题型: single_choice/multiple_choice/true_false/fill_blank")
    question_text = Column(Text, nullable=False, comment="题目内容")
    options = Column(JSON, nullable=True, comment="选项（选择题）")
    correct_answer = Column(JSON, nullable=False, comment="正确答案")
    explanation = Column(Text, nullable=True, comment="解析")
    difficulty = Column(Integer, default=3, comment="难度 1-5")
    order = Column(Integer, default=0, comment="排序")


class QuizAttempt(Base):
    """测验尝试模型"""
    __tablename__ = "quiz_attempts"
    
    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    score = Column(Float, nullable=True, comment="得分")
    total_questions = Column(Integer, default=0, comment="总题数")
    correct_count = Column(Integer, default=0, comment="正确数")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class QuizAnswer(Base):
    """测验答案模型"""
    __tablename__ = "quiz_answers"
    
    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("quiz_attempts.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("quiz_questions.id"), nullable=False)
    user_answer = Column(JSON, nullable=True, comment="用户答案")
    is_correct = Column(Boolean, nullable=True, comment="是否正确")
