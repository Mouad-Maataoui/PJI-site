from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    ip_address: Optional[str] = None

    
class UserCreate(UserBase):
    email: EmailStr
    username: str
    password: str


class UserUpdate(UserBase):
    password: Optional[str] = None


class UserInDBBase(UserBase):
    id: Optional[int] = None
    points_balance: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True 


# Returned to the API
class User(UserInDBBase):
    pass


# Additional properties stored in DB
class UserInDB(UserInDBBase):
    hashed_password: str