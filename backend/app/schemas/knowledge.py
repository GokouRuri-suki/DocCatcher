from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class KnowledgePointBase(BaseModel):
    title: str
    description: Optional[str] = None
    content: Optional[str] = None
    level: int = 1
    order: int = 0
    page_numbers: Optional[str] = None


class KnowledgePointCreate(KnowledgePointBase):
    document_id: int
    parent_id: Optional[int] = None


class KnowledgePointResponse(KnowledgePointBase):
    id: int
    document_id: int
    parent_id: Optional[int] = None
    created_at: datetime
    children: List["KnowledgePointResponse"] = []
    
    class Config:
        from_attributes = True


class KnowledgePointSimple(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    level: int
    parent_id: Optional[int] = None
    page_numbers: Optional[str] = None
    
    class Config:
        from_attributes = True


class KnowledgeRelationResponse(BaseModel):
    id: int
    source_id: int
    target_id: int
    relation_type: str
    description: Optional[str] = None
    
    class Config:
        from_attributes = True


class KnowledgeGraphResponse(BaseModel):
    nodes: List[KnowledgePointSimple]
    edges: List[KnowledgeRelationResponse]


# 解决循环引用
KnowledgePointResponse.model_rebuild()
