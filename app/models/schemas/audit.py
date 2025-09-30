from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone


class AuditLog(BaseModel):
    log_id: UUID = Field(default_factory=uuid4)
    user_id: str | None = None  # who performed action (optional for system tasks)
    action: str  # "create", "update", "delete", "login", etc.
    resource_type: str  # "users", "accounts", "entries", etc.
    resource_id: str | None = None  # affected record
    details: str | None = None  # request payload, old vs. new values, etc.
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True
    is_deleted: bool = False
