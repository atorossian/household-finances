from calendar import monthrange
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from uuid import uuid4, UUID
import pandas as pd
from app.models.schemas.debt import Debt, DebtCreate, DebtOut
from app.models.schemas.entry import Entry
from app.models.schemas.account import Account
from app.models.schemas.household import Household
from app.models.schemas.membership import UserAccount, UserHousehold
from app.services.storage import (
    save_version, resolve_id_by_name, 
    load_versions, soft_delete_record, 
    log_action, mark_old_version_as_stale, 
    generate_debt_entries
)
from app.services.auth import get_current_user
from app.services.roles import validate_entry_permissions
from scripts.safe_due_dates import safe_due_date
from app.services.utils import page_params

router = APIRouter()

@router.post("/")
def create_debt(payload: DebtCreate, user=Depends(get_current_user)):
    account_id = resolve_id_by_name("accounts", payload.account_name, Account, "name", "account_id")
    household_id = resolve_id_by_name("households", payload.household_name, Household, "name", "household_id")
    
    now = datetime.now(timezone.utc)
    validate_entry_permissions(str(user["user_id"]), account_id, household_id, user)


    # --- Build and save debt ---
    debt_id = uuid4()
    debt = Debt(
        debt_id=debt_id,
        user_id=payload.user_id,
        account_id=account_id,
        household_id=household_id,
        name=payload.name,
        principal=payload.principal,
        interest_rate=payload.interest_rate,
        installments=payload.installments,
        start_date=payload.start_date,
        due_day=payload.due_day,
        created_at=now,
        updated_at=now,
        is_current=True,
        is_deleted=False,
    )
    save_version(debt, "debts", "debt_id")
    log_action(user["user_id"], "create", "debts", str(debt.debt_id), payload.model_dump())

    # --- Generate installments ---
    entries = generate_debt_entries(debt)
    for e in entries:
        save_version(e, "entries", "entry_id")
        log_action(user['user_id'], "create", "entries", str(e.entry_id), e.model_dump())

    return {
        "message": "Debt created",
        "debt_id": str(debt.debt_id),
        "installments": payload.installments,
        "entries": [str(e.entry_id) for e in entries]
    }

@router.put("/{debt_id}")
def update_debt(debt_id: UUID, payload: dict, user=Depends(get_current_user)):
    debts = load_versions("debts", Debt)
    match = debts[(debts["debt_id"] == str(debt_id)) & (debts["is_current"]) & (~debts["is_deleted"].fillna(False))]

    if match.empty:
        raise HTTPException(status_code=404, detail="Debt not found")

    row = match.iloc[0].to_dict()
    mark_old_version_as_stale("debts", str(debt_id), "debt_id")

    updated = Debt(
        **{**row, **payload},
        debt_id=debt_id,
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
    )
    save_version(updated, "debts", "debt_id")
    log_action(user["user_id"], "update", "debts", str(debt_id), payload)

    # Load existing debt entries
    entries = load_versions("entries", Entry)
    debt_entries = entries[(entries["debt_id"] == str(debt_id)) & (entries["is_current"]) & (~entries["is_deleted"].fillna(False))]

    today = datetime.now(timezone.utc).date()

    for _, e in debt_entries.iterrows():
        entry_date = pd.to_datetime(e["entry_date"]).date()

        if entry_date < today:
            # Past entries: only update description if debt name changed
            if "name" in payload and payload["name"] != row["name"]:
                mark_old_version_as_stale("entries", e["entry_id"], "entry_id")
                e_dict = e.to_dict()
                e_dict["description"] = e_dict["description"].replace(row["name"], payload["name"])
                e_dict.update({"is_current": True, "is_deleted": False, "updated_at": datetime.now(timezone.utc)})
                save_version(Entry(**e_dict), "entries", "entry_id")
        else:
            # Future entries: recalc with new debt terms
            mark_old_version_as_stale("entries", e["entry_id"], "entry_id")

    # --- Generate installments ---
    entries = generate_debt_entries(updated, start_date=today)
    for e in entries:
        save_version(e, "entries", "entry_id")
        log_action(user['user_id'], "update", "entries", str(e.entry_id), e.model_dump())

    return {
        "message": "Debt update",
        "debt_id": str(updated.debt_id),
        "installments": payload.installments,
        "entries": [str(e.entry_id) for e in entries]
    }


@router.delete("/{debt_id}")
def delete_debt(debt_id: UUID, user=Depends(get_current_user)):
    # Cascade to child entries handled inside storage
    df = load_versions("debts", Debt)
    current = df[(df["debt_id"] == str(debt_id)) & (df["is_current"]) & (~df["is_deleted"].fillna(False))]
    if current.empty:
        raise HTTPException(status_code=404, detail="Debt not found")

    row = current.iloc[0].to_dict()
    validate_entry_permissions(row["user_id"], row["account_id"], row["household_id"], user)

    return soft_delete_record(
        "debts", str(debt_id), "debt_id", Debt,
        user=user, owner_field="user_id", require_owner=True
    )

@router.get("/", response_model=list[DebtOut])
def list_debts(user=Depends(get_current_user), page=Depends(page_params)):
    df = load_versions("debts", Debt)
    if df.empty:
        return []

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

    log_action(user["user_id"], "list", "debts", None, {"count": len(df)})
    return df.to_dict(orient="records")

@router.get("/{debt_id}", response_model=list[DebtOut])
def get_debt(debt_id: UUID, user=Depends(get_current_user), page=Depends(page_params)):
    df = load_versions("debts", Debt)
    records = df[(df["debt_id"] == str(debt_id)) & (df["is_current"])]
    if records.empty:
        raise HTTPException(status_code=404, detail="Debt not found")

    row = records.iloc[0].to_dict()
    validate_entry_permissions(row["user_id"], row["account_id"], row["household_id"], user)
    df = records.iloc[page["offset"] : page["offset"] + page["limit"]]

    log_action(user["user_id"], "get", "debts", str(debt_id))
    return records.to_dict(orient="records")
