from pydantic import BaseModel, Field, EmailStr
from uuid import UUID, uuid4
from datetime import datetime, timezone


class User(BaseModel):
    user_id: UUID
    user_name: str
    email: EmailStr
    hashed_password: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    password_changed_at: datetime | None = None   # track last password change
    is_superuser: bool = False
    is_suspended: bool = False
    suspended_at: datetime | None = None
    suspension_reason: str | None = None
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

class PasswordHistory(BaseModel):
    history_id: UUID
    user_id: UUID
    hashed_password: str
    changed_at: datetime
    is_current: bool = True
    is_deleted: bool = False

class PasswordResetToken(BaseModel):
    token_id: UUID
    user_id: UUID
    otp_code: str
    expires_at: datetime
    used: bool = False
    created_at: datetime

class UserOut(BaseModel):
    user_id: str
    email: EmailStr
    is_superuser: bool = False
    is_active: bool = True
    is_suspended: bool = False
    created_at: datetime

    class Config:
        orm_mode = True