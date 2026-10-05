from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List


class StudyPlanBase(BaseModel):
    title: str
    description: Optional[str] = None
    total_days: int = 0


class StudyPlanCreate(StudyPlanBase):
    document_id: int
    start_date: Optional[date] = None


class StudyPlanItemResponse(BaseModel):
    id: int
    plan_id: int
    day_number: int
    title: str
    tasks: Optional[str] = None
    knowledge_point_ids: Optional[List[int]] = None
    completed: bool = False
    order: int = 0
    
    class Config:
        from_attributes = True


class StudyPlanResponse(StudyPlanBase):
    id: int
    document_id: int
    start_date: Optional[date] = None
    created_at: datetime
    items: List[StudyPlanItemResponse] = []
    
    class Config:
        from_attributes = True


class StudyPlanItemUpdate(BaseModel):
    completed: bool


class StudyPlanSimpleResponse(BaseModel):
    id: int
    document_id: int
    title: str
    description: Optional[str] = None
    total_days: int
    start_date: Optional[date] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
