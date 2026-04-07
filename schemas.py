from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
import re


class PriorityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


# ─── Auth ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., max_length=254)
    password: str = Field(..., min_length=6, max_length=128)
    displayName: Optional[str] = Field(None, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., max_length=254)
    password: str = Field(..., min_length=6, max_length=128)


class AuthUserResponse(BaseModel):
    id: str
    email: str
    displayName: Optional[str] = None

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    accessToken: str
    tokenType: str = "Bearer"
    expiresInSeconds: int = 3600
    user: AuthUserResponse


# ─── Todo ─────────────────────────────────────────────────────────────────────

class TodoResponse(BaseModel):
    id: str
    title: str
    details: Optional[str] = None
    priority: str
    dueDate: Optional[str] = None
    isCompleted: bool
    isPublic: bool
    createdAt: str
    updatedAt: str

    class Config:
        from_attributes = True


class CreateTodoRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    details: Optional[str] = Field(None, max_length=1000)
    priority: PriorityEnum = PriorityEnum.medium
    dueDate: Optional[str] = None
    isPublic: bool = False

    @field_validator("dueDate")
    @classmethod
    def validate_due_date(cls, v):
        if v is not None:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                raise ValueError("dueDate must be in YYYY-MM-DD format")
        return v

class UpdateTodoRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    details: Optional[str] = Field(None, max_length=1000)
    priority: PriorityEnum
    dueDate: Optional[str] = None
    isPublic: bool = False
    isCompleted: bool = False

    @field_validator("dueDate")
    @classmethod
    def validate_due_date(cls, v):
        if v is not None:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                raise ValueError("dueDate must be in YYYY-MM-DD format")
        return v

class SetCompletionRequest(BaseModel):
    isCompleted: bool


# ─── Pagination ───────────────────────────────────────────────────────────────

class PaginatedTodoResponse(BaseModel):
    items: List[TodoResponse]
    page: int
    pageSize: int
    totalItems: int
    totalPages: int
