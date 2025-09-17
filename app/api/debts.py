# debts.py
from calendar import monthrange
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from uuid import uuid4, UUID
import pandas as pd
from app.models.schemas import (
    Debt, DebtCreate, Entry,
    Account, Household, UserAccount, UserHousehold
)
from app.services.storage import (
    save_version, resolve_id_by_name, load_versions, soft_delete_record, log_action, mark_old_version_as_stale, generate_debt_entries
)
from app.services.auth import get_current_user
from app.services.roles import validate_entry_permissions
from scripts.safe_due_dates import safe_due_date

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
    if payload.interest_rate and payload.interest_rate > 0.0:
        # Convert annual % to monthly decimal
        r = payload.interest_rate / 100 / 12
        n = payload.installments
        P = payload.principal
        installment_value = round(P * (r * (1 + r) ** n) / ((1 + r) ** n - 1), 2)
    else:
        installment_value = round(payload.principal / payload.installments, 2)

    entries = []

    for i in range(payload.installments):
        due_date = safe_due_date(payload.start_date, i, payload.due_day)

        entry = Entry(
            entry_id=uuid4(),
            user_id=payload.user_id,
            account_id=account_id,
            household_id=household_id,
            debt_id=debt_id,
            entry_date=due_date.date(),
            value_date=due_date.date(),
            type="expense",
            category="financing",
            amount=installment_value,
            description=f"{payload.name} installment {i+1}/{payload.installments}",
            created_at=now,
            updated_at=now,
            is_current=True,
            is_deleted=False,
        )
        save_version(entry, "entries", "entry_id")
        
        entries.append(entry)
        log_action(user["user_id"], "create", "entries", str(entry.entry_id), entry.model_dump())
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

    # Load existing debt entries
    entries = load_versions("entries", Entry)
    debt_entries = entries[(entries["description"].str.contains(row["name"])) & (entries["is_current"]) & (~entries["is_deleted"].fillna(False))]

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

    # Regenerate future installments
    regenerate_future_debt_entries(updated, from_date=today)

    log_action(user["user_id"], "update", "debts", str(debt_id), payload)
    return {"message": "Debt updated", "debt_id": str(debt_id)}


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

@router.get("/")
def list_debts(user=Depends(get_current_user)):
    df = load_versions("debts", Debt)
    if df.empty:
        return []

    df = df[(df["is_current"]) & (~df.get("is_deleted", False).fillna(False))]

    # Keep only debts from households the user belongs to
    households = set(df["household_id"].unique())
    allowed = []
    for hh_id in households:
        try:
            require_household_role(user, str(hh_id), required_role="member")
            allowed.append(hh_id)
        except HTTPException:
            continue

    df = df[df["household_id"].isin(allowed)]
    log_action(user["user_id"], "list", "debts", None, {"count": len(df)})
    return df.to_dict(orient="records")

@router.get("/{debt_id}")
def get_debt(debt_id: UUID, user=Depends(get_current_user)):
    df = load_versions("debts", Debt)
    records = df[(df["debt_id"] == str(debt_id)) & (df["is_current"])]
    if records.empty:
        raise HTTPException(status_code=404, detail="Debt not found")

    row = records.iloc[0].to_dict()
    validate_entry_permissions(row["user_id"], row["account_id"], row["household_id"], user)

    log_action(user["user_id"], "get", "debts", str(debt_id))
    return records.to_dict(orient="records")
