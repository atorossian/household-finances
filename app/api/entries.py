from app.services.storage import save_version, load_versions, mark_old_version_as_stale
from datetime import datetime, timezone
from app.models.schemas import Entry
from uuid import UUID, uuid4
import boto3
from fastapi import APIRouter, HTTPException, Depends
from app.services.auth import get_current_user

s3 = boto3.client("s3")
BUCKET_NAME = "household-finances"

router = APIRouter()

@router.post("/")
def create_entry(entry: Entry, user=Depends(get_current_user)):
    entry.entry_id = uuid4()
    entry.created_at = datetime.now(timezone.utc)
    entry.updated_at = datetime.now(timezone.utc)
    entry.is_current = True

    save_version(entry, "entries", "entry_id")
    return {"message": "Entry created", "entry_id": str(entry.entry_id)}


@router.put("/{entry_id}")
def update_entry(entry_id: UUID, updated: Entry, user=Depends(get_current_user)):
    mark_old_version_as_stale("entries", entry_id, "entry_id")

    updated.entry_id = entry_id
    updated.updated_at = datetime.now(timezone.utc)
    updated.is_current = True

    save_version(updated, "entries", "entry_id")
    return {"message": "Entry updated", "entry_id": str(entry_id)}


@router.post("/{entry_id}/delete")
def soft_delete_entry(entry_id: UUID, user=Depends(get_current_user)):
    mark_old_version_as_stale("entries", entry_id, "entry_id")

    now = datetime.now(timezone.utc)
    deleted = Entry(
        entry_id=entry_id,
        entry_date=datetime.today(),
        value_date=datetime.today(),
        type="expense",
        category="other",
        amount=0.0,
        description="deleted",
        created_at=now,
        updated_at=now,
        is_current=True
    )

    save_version(deleted, "entries", "entry_id")
    return {"message": "Entry soft-deleted", "entry_id": str(entry_id)}


@router.get("/")
def list_current_entries(user=Depends(get_current_user)):
    df = load_versions("entries")
    current = df[(df["is_current"]) & (df["description"] != "deleted")]
    return current.sort_values(by="updated_at", ascending=False).to_dict(orient="records")


@router.get("/{entry_id}")
def get_entry_history(entry_id: UUID, user=Depends(get_current_user)):
    df = load_versions("entries")
    versions = df[df["entry_id"] == str(entry_id)].sort_values(by="updated_at", ascending=False)
    if versions.empty:
        raise HTTPException(status_code=404, detail="Entry not found")
    return versions.to_dict(orient="records")