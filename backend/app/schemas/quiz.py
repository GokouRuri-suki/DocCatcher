from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Any


class QuizBase(BaseModel):
    title: str
    description: Optional[str] = None


class QuizCreate(QuizBase):
    document_id: int


class QuizQuestionResponse(BaseModel):
    id: int
    quiz_id: int
    knowledge_point_id: Optional[int] = None
    question_type: str
    question_text: str
    options: Optional[Any] = None
    difficulty: int = 3
    order: int = 0
    
    class Config:
        from_attributes = True


class QuizResponse(QuizBase):
    id: int
    document_id: int
    question_count: int = 0
    created_at: datetime
    
    class Config:
        from_attributes = True


class QuizDetailResponse(QuizResponse):
    questions: List[QuizQuestionResponse] = []


class QuizAnswerRequest(BaseModel):
    question_id: int
    answer: Any


class QuizSubmitRequest(BaseModel):
    answers: List[QuizAnswerRequest]


class QuizAnswerResponse(BaseModel):
    id: int
    question_id: int
    user_answer: Optional[Any] = None
    is_correct: Optional[bool] = None
    
    class Config:
        from_attributes = True


class QuizAttemptResponse(BaseModel):
    id: int
    quiz_id: int
    score: Optional[float] = None
    total_questions: int = 0
    correct_count: int = 0
    started_at: datetime
    completed_at: Optional[datetime] = None
    answers: List[QuizAnswerResponse] = []
    
    class Config:
        from_attributes = True


class QuizQuestionWithAnswer(QuizQuestionResponse):
    correct_answer: Optional[Any] = None
    explanation: Optional[str] = None
    user_answer: Optional[Any] = None
    is_correct: Optional[bool] = None


class QuizResultResponse(BaseModel):
    attempt: QuizAttemptResponse
    questions: List[QuizQuestionWithAnswer]
