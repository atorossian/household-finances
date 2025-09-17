from pydantic import BaseModel, Field
from app.models.enums import Role
from uuid import UUID, uuid4
from datetime import datetime, timezone


class UserAccount(BaseModel):
    mapping_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    account_id: UUID
    role: Role = "member" 
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False

class UserHousehold(BaseModel):
    mapping_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    household_id: UUID
    role: Role = "member" 
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False

class UserAccountOut(BaseModel):
    mapping_id: UUID
    user_id: UUID
    account_id: UUID
    role: Role
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class UserHouseholdOut(BaseModel):
    mapping_id: UUID
    user_id: UUID
    household_id: UUID
    role: Role
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
