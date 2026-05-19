from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from app.models.transaction import TransactionType, TransactionStatus


class TransactionBase(BaseModel):
    type: TransactionType
    points: int


class TransactionCreate(TransactionBase):
    user_id: int
    amount: Optional[float] = None
    stripe_payment_id: Optional[str] = None
    image_task_id: Optional[int] = None


class TransactionUpdate(BaseModel):
    status: TransactionStatus
    stripe_payment_id: Optional[str] = None


class TransactionInDBBase(TransactionBase):
    id: int
    user_id: int
    status: TransactionStatus
    amount: Optional[float] = None
    stripe_payment_id: Optional[str] = None
    image_task_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True 


class Transaction(TransactionInDBBase):
    pass


class TransactionInDB(TransactionInDBBase):
    pass