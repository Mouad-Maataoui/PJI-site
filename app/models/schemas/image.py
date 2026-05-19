from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from app.models.image_task import ProcessingStatus


class ImageTaskBase(BaseModel):
    original_filename: str


class ImageTaskCreate(ImageTaskBase):
    pass


class ImageTaskUpdate(BaseModel):
    status: Optional[ProcessingStatus] = None
    processed_file_path: Optional[str] = None
    error_message: Optional[str] = None


class ImageTaskInDBBase(ImageTaskBase):
    id: int
    user_id: int
    original_file_path: str
    processed_file_path: Optional[str] = None
    status: ProcessingStatus
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    expire_at: datetime

    class Config:
        from_attributes = True 


class ImageTask(ImageTaskInDBBase):
    pass


class ImageTaskInDB(ImageTaskInDBBase):
    pass