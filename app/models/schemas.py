from pydantic import BaseModel, Field, EmailStr
from app.models.enums import EntryType, Category
from uuid import UUID, uuid4
from datetime import datetime, timezone, date


class Entry(BaseModel):
    entry_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    entry_date: date
    value_date: date
    type: EntryType
    category: Category
    amount: float
    description: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True


class User(BaseModel):
    user_id: UUID = Field(default_factory=uuid4)
    user_name: str
    email: EmailStr
    hashed_password: str
    token: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    is_deleted: bool = False
    is_current: bool = True


class RegisterRequest(BaseModel):
    user_name: str
    email: EmailStr
    password: str  # Raw password; will be hashed on creation


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserUpdateRequest(BaseModel):
    user_name: str | None = None
    email: EmailStr | None = None
    password: str | None = None
