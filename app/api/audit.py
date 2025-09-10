from fastapi import APIRouter, Depends, Query
import pandas as pd
from app.services.storage import load_versions
from app.models.schemas import AuditLog
from app.services.auth import get_current_user

router = APIRouter()

@router.get("/logs")
def list_audit_logs(
    user_id: str | None = Query(None),
    resource_type: str | None = Query(None),
    action: str | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    user=Depends(get_current_user)
):
    start_dt, end_dt = None, None
    if start and end:
        start_dt, end_dt = pd.to_datetime(start), pd.to_datetime(end)

    df = load_versions("audit_logs", AuditLog, start=start_dt, end=end_dt)
    if df.empty:
        return []

    df = df[df["is_current"] & ~df["is_deleted"].fillna(False)]

    if user_id:
        df = df[df["user_id"] == user_id]
    if resource_type:
        df = df[df["resource_type"] == resource_type]
    if action:
        df = df[df["action"] == action]

    return df.to_dict(orient="records")
