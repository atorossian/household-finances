from decimal import Decimal
from pydantic import BaseModel, Field
from app.models.enums import EntryType, Category
from uuid import UUID, uuid4
from datetime import datetime, timezone, date


class Entry(BaseModel):
    entry_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    account_id: UUID
    household_id: UUID
    debt_id: UUID | None = None
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


class EntryOut(BaseModel):
    entry_id: str
    user_id: str
    account_id: str
    household_id: str
    debt_id: str | None = None
    type: EntryType
    category: str
    amount: Decimal
    description: str | None = None
    entry_date: date
    value_date: date
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
