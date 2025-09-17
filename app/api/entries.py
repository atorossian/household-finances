from app.services.storage import save_version, load_versions, mark_old_version_as_stale, resolve_id_by_name, soft_delete_record, log_action
from datetime import datetime, timezone
from app.models.schemas.entry import EntryCreate, Entry, EntryUpdate, EntryOut
from app.models.schemas.account import Account
from app.models.schemas.household import Household
from app.models.schemas.membership import UserAccount, UserHousehold
from uuid import UUID, uuid4
import boto3
import pandas as pd
from fastapi import APIRouter, HTTPException, Depends, Query
from app.services.auth import get_current_user
from app.services.roles import validate_entry_permissions
from app.services.utils import page_params

router = APIRouter()

@router.post("/")
def create_entry(payload: EntryCreate, user=Depends(get_current_user)):
    account_id = resolve_id_by_name("accounts", payload.account_name, Account, "name",  "account_id")
    household_id = resolve_id_by_name("households", payload.household_name, Household, "name", "household_id")
    
    validate_entry_permissions(str(payload.user_id), account_id, household_id, acting_user=user)

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
    log_action(user["user_id"], "create", "entries", str(entry.entry_id), payload.model_dump())

    return {"message": "Entry created", "entry_id": str(entry.entry_id)}


@router.put("/{entry_id}")
def update_entry(entry_id: UUID, payload: EntryUpdate, user=Depends(get_current_user)):
    account_id = resolve_id_by_name("accounts", payload.account_name, Account, "name", "account_id")
    household_id = resolve_id_by_name("households", payload.household_name, Household, "name", "household_id")

    df = load_versions("entries", Entry, record_id=entry_id)
    current = df[(df["is_current"]) & (~df["is_deleted"].fillna(False))]
    if current.empty:
        raise HTTPException(status_code=404, detail="Entry not found")

    validate_entry_permissions(str(payload.user_id), account_id, household_id, user)

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
    log_action(user["user_id"], "update", "entries", str(entry_id), payload.model_dump())

    return {"message": "Entry updated", "entry_id": str(entry_id)}


@router.delete("/{entry_id}")
def delete_entry(entry_id: UUID, user=Depends(get_current_user)):
    df = load_versions("entries", Entry, record_id=entry_id)
    current = df[(df["is_current"]) & (~df["is_deleted"].fillna(False))]
    if current.empty:
        raise HTTPException(status_code=404, detail="Entry not found")

    row = current.iloc[0].to_dict()
    validate_entry_permissions(row["user_id"], row["account_id"], row["household_id"], user)

    return soft_delete_record(
        "entries", str(entry_id), "entry_id", Entry,
        user=user, require_owner=False
    )

@router.get("/", response_model=list[EntryOut])
def list_current_entries(user=Depends(get_current_user), page=Depends(page_params)):
    df = load_versions("entries", Entry)
    if df.empty:
        return []

    # Filter current and active
    df = df[(df["is_current"]) & (~df.get("is_deleted", False).fillna(False))]

    # Validate each debt against entry permissions
    allowed = []
    for _, row in df.iterrows():
        try:
            validate_entry_permissions(
                user_id=row["user_id"],
                account_id=row["account_id"],
                household_id=row["household_id"],
                acting_user=user,
            )
            allowed.append(row)
        except HTTPException:
            continue

    # Build new dataframe from allowed rows
    if not allowed:
        return []
    df = pd.DataFrame(allowed)
    df = df.iloc[page["offset"] : page["offset"] + page["limit"]]

    log_action(user["user_id"], "list", "entries", None, {"count": len(df)})

    return df.to_dict(orient="records")


@router.get("/{entry_id}", response_model=list[EntryOut])
def get_entry_history(entry_id: UUID, user=Depends(get_current_user), page=Depends(page_params)):
    df = load_versions("entries", Entry, record_id=entry_id)
    versions = df.sort_values(by="updated_at", ascending=False)
    if versions.empty:
        raise HTTPException(status_code=404, detail="Entry not found")
    row = versions.iloc[0].to_dict()

    validate_entry_permissions(row["user_id"], row["account_id"], row["household_id"], user)
    df = versions.iloc[page["offset"] : page["offset"] + page["limit"]]
    log_action(user["user_id"], "get", "entries", str(entry_id))
    return df.to_dict(orient="records")
