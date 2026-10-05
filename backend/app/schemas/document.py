from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class DocumentBase(BaseModel):
    original_name: str


class DocumentCreate(DocumentBase):
    pass


class DocumentResponse(DocumentBase):
    id: int
    filename: str
    file_path: str
    status: str
    total_pages: int
    file_size: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    id: int
    original_name: str
    status: str
    total_pages: int
    file_size: int
    created_at: datetime
    
    class Config:
        from_attributes = True
