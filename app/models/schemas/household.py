from pydantic import BaseModel
from datetime import datetime
from pydantic import Field
from uuid import UUID, uuid4
from datetime import timezone


class Household(BaseModel):
    household_id: UUID = Field(default_factory=uuid4)
    name: str
    created_by_user_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False


class HouseholdCreate(BaseModel):
    name: str


class HouseholdOut(BaseModel):
    household_id: str
    name: str
    created_at: datetime
    created_by_user_id: UUID

    class Config:
        orm_mode = True
