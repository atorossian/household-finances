from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone


class Account(BaseModel):
    account_id: UUID = Field(default_factory=uuid4)
    name: str
    household_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False


class AccountOut(BaseModel):
    account_id: str
    household_id: str
    name: str
    created_at: datetime

    class Config:
        orm_mode = True
