from decimal import Decimal
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone, date


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

class DebtCreate(BaseModel):
    user_id: UUID
    account_name: str
    household_name: str
    name: str
    principal: float
    interest_rate: float | None = None   # annual %
    installments: int
    start_date: date
    due_day: int   # day of month for payments

class DebtOut(BaseModel):
    debt_id: UUID
    user_id: UUID
    account_id: UUID
    household_id: UUID
    name: str
    principal: float
    interest_rate: float
    installments: int
    start_date: date
    due_day: int
    created_at: datetime

    class Config:
        orm_mode = True