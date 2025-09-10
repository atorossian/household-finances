from app.services.storage import save_version, load_versions, mark_old_version_as_stale, resolve_id_by_name, soft_delete_record
from datetime import datetime, timezone
from app.models.schemas import EntryCreate, Entry, Account, Household, UserAccount, UserHousehold, EntryUpdate
from uuid import UUID, uuid4
import boto3
import pandas as pd
from fastapi import APIRouter, HTTPException, Depends, Query
from app.services.auth import get_current_user

router = APIRouter()

@router.post("/")
def create_entry(payload: EntryCreate, user=Depends(get_current_user)):
    account_id = resolve_id_by_name("accounts", payload.account_name, Account, "name",  "account_id")
    household_id = resolve_id_by_name("households", payload.household_name, Household, "name", "household_id")

    if str(payload.user_id) != str(user["user_id"]):
        raise HTTPException(status_code=403, detail="Cannot create entries for another user")

    # Load memberships
    account_memberships = load_versions("user_accounts", UserAccount)
    household_memberships = load_versions("user_households", UserHousehold)

    account_match = account_memberships[
        (account_memberships["user_id"] == str(payload.user_id)) &
        (account_memberships["account_id"] == str(account_id)) &
        (account_memberships["is_current"]) &
        (~account_memberships["is_deleted"].fillna(False))
    ]

    if account_match.empty:
        raise HTTPException(status_code=403, detail="Account mismatch or not assigned to user")


    household_match = household_memberships[
        (household_memberships["user_id"] == str(payload.user_id)) &
        (household_memberships["household_id"] == str(household_id)) &
        (household_memberships["is_current"]) &
        (~household_memberships["is_deleted"].fillna(False))
    ]

    if household_match.empty:
        raise HTTPException(status_code=403, detail="Household mismatch or not assigned to user")

    entry = Entry(
        entry_id=uuid4(),
        user_id=payload.user_id,
        account_id=account_id,
        household_id=household_id,
        entry_date=payload.entry_date,
        value_date=payload.value_date,
        type=payload.type,
        category=payload.category,
        amount=payload.amount,
        description=payload.description,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_current=True,
    )

    save_version(entry, "entries", "entry_id")
    return {"message": "Entry created", "entry_id": str(entry.entry_id)}


@router.put("/{entry_id}")
def update_entry(entry_id: UUID, payload: EntryUpdate, user=Depends(get_current_user)):
    account_id = resolve_id_by_name("accounts", payload.account_name, Account, "name", "account_id")
    household_id = resolve_id_by_name("households", payload.household_name, Household, "name", "household_id")

    if str(payload.user_id) != str(user["user_id"]):
        raise HTTPException(status_code=403, detail="Cannot update entries for another user")

    # Stale old version
    mark_old_version_as_stale("entries", entry_id, "entry_id")

    updated = Entry(
        entry_id=entry_id,
        user_id=payload.user_id,
        account_id=account_id,
        household_id=household_id,
        entry_date=payload.entry_date,
        value_date=payload.value_date,
        type=payload.type,
        category=payload.category,
        amount=payload.amount,
        description=payload.description,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_current=True,
    )

    save_version(updated, "entries", "entry_id")
    return {"message": "Entry updated", "entry_id": str(entry_id)}


@router.delete("/{entry_id}")
def delete_entry(entry_id: UUID, user=Depends(get_current_user)):
    return soft_delete_record(
        "entries", str(entry_id), "entry_id", Entry,
        user=user, owner_field="user_id", require_owner=True
    )


@router.get("/")
def list_current_entries(user=Depends(get_current_user)):
    df = load_versions("entries", Entry)
    current = df[
        (df["is_current"]) &
        (~df.get("is_deleted", False).fillna(False)) &
        (df["user_id"] == str(user["user_id"]))
    ]
    
    return current.sort_values(by="updated_at", ascending=False).to_dict(orient="records")


@router.get("/{entry_id}")
def get_entry_history(entry_id: UUID, user=Depends(get_current_user)):
    df = load_versions("entries", Entry)
    versions = df[df["entry_id"] == str(entry_id)].sort_values(by="updated_at", ascending=False)
    if versions.empty:
        raise HTTPException(status_code=404, detail="Entry not found")
    return versions.to_dict(orient="records")
