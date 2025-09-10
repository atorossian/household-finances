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
    df = load_versions("audit_logs", AuditLog)
    if df.empty:
        return []

    df = df[df["is_current"] & ~df["is_deleted"].fillna(False)]

    if user_id:
        df = df[df["user_id"] == user_id]
    if resource_type:
        df = df[df["resource_type"] == resource_type]
    if action:
        df = df[df["action"] == action]
    if start and end:
        start_dt, end_dt = pd.to_datetime(start), pd.to_datetime(end)
        df = df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= end_dt)]

    return df.to_dict(orient="records")
