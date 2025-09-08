from app.services.storage import save_version, load_versions, mark_old_version_as_stale, resolve_id_by_name
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

    # # Load memberships
    # account_memberships = load_versions("user_accounts", UserAccount)
    # household_memberships = load_versions("user_households", UserHousehold)
    # print(str(account_memberships["user_id"]))
    # print(str(account_memberships["account_id"]))
    # print(str(household_memberships["user_id"]))
    # print(str(household_memberships["household_id"]))
    # print(payload.user_id)
    # print(account_id)
    # print(household_id)
    # # Check account membership
    # if not ((str(account_memberships["user_id"]) == str(payload.user_id)) &
    #         (str(account_memberships["account_id"]) == str(account_id))):
    #     raise HTTPException(status_code=403, detail="Account mismatch or not assigned to user")

    # # Check household membership
    # if not ((str(household_memberships["user_id"]) == str(payload.user_id)) &
    #         (str(household_memberships["household_id"]) == str(household_id))):
    #     raise HTTPException(status_code=403, detail="Household mismatch or not assigned to user")

    
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


@router.post("/{entry_id}/delete")
def soft_delete_entry(entry_id: UUID, user=Depends(get_current_user)):
    df = load_versions("entries", Entry)

    current = df[(df["entry_id"] == str(entry_id)) & (df["is_current"])]
    if current.empty:
        raise HTTPException(status_code=404, detail="Entry not found")

    current_entry = current.iloc[0]

    # Mark old version as stale
    mark_old_version_as_stale("entries", entry_id, "entry_id")

    now = datetime.now(timezone.utc)
    deleted = Entry(
        entry_id=entry_id,
        user_id=current_entry["user_id"],
        account_id=current_entry["account_id"],
        household_id=current_entry["household_id"],
        entry_date=pd.to_datetime(current_entry["entry_date"]).date(),
        value_date=pd.to_datetime(current_entry["value_date"]).date(),
        type=current_entry["type"],
        category=current_entry["category"],
        amount=0.0,
        description="deleted",
        created_at=current_entry["created_at"],
        updated_at=now,
        is_current=True,
    )

    save_version(deleted, "entries", "entry_id")
    return {"message": "Entry soft-deleted", "entry_id": str(entry_id)}



@router.get("/")
def list_current_entries(user=Depends(get_current_user)):
    df = load_versions("entries", Entry)
    current = df[(df["is_current"]) & (df["description"] != "deleted")]
    return current.sort_values(by="updated_at", ascending=False).to_dict(orient="records")


@router.get("/{entry_id}")
def get_entry_history(entry_id: UUID, user=Depends(get_current_user)):
    df = load_versions("entries", Entry)
    versions = df[df["entry_id"] == str(entry_id)].sort_values(by="updated_at", ascending=False)
    if versions.empty:
        raise HTTPException(status_code=404, detail="Entry not found")
    return versions.to_dict(orient="records")
