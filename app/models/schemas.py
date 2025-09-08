from pydantic import BaseModel, Field, EmailStr
from app.models.enums import EntryType, Category
from uuid import UUID, uuid4
from datetime import datetime, timezone, date


class Entry(BaseModel):
    entry_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    account_id: UUID
    household_id: UUID
    entry_date: date
    value_date: date
    type: EntryType
    category: Category
    amount: float
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False

class EntryCreate(BaseModel):
    user_id: UUID
    account_name: str
    household_name: str
    entry_date: date
    value_date: date
    type: EntryType
    category: Category
    amount: float
    description: str = ""

class EntryUpdate(BaseModel):
    user_id: UUID
    account_name: str
    household_name: str
    entry_date: date
    value_date: date
    type: EntryType
    category: Category
    amount: float
    description: str = ""


class User(BaseModel):
    user_id: UUID = Field(default_factory=uuid4)
    user_name: str
    email: EmailStr
    hashed_password: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    is_deleted: bool = False
    is_current: bool = True

class RefreshToken(BaseModel):
    refresh_token_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False

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

class Household(BaseModel):
    household_id: UUID = Field(default_factory=uuid4)
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False

class Account(BaseModel):
    account_id: UUID = Field(default_factory=uuid4)
    name: str
    user_id: UUID
    household_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False

class UserAccount(BaseModel):
    mapping_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    account_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False

class UserHousehold(BaseModel):
    mapping_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    household_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False

class Debt(BaseModel):
    debt_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    account_id: UUID
    household_id: UUID
    name: str
    principal: float
    interest_rate: float | None = None   # annual %
    installments: int
    start_date: date
    due_day: int   # day of month for payments
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False
