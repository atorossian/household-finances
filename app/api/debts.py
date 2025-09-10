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
    save_version, resolve_id_by_name, load_versions, soft_delete_record
)
from app.services.auth import get_current_user
from scripts.safe_due_dates import safe_due_date

router = APIRouter()

@router.post("/")
def create_debt(payload: DebtCreate, user=Depends(get_current_user)):
    account_id = resolve_id_by_name("accounts", payload.account_name, Account, "name", "account_id")
    household_id = resolve_id_by_name("households", payload.household_name, Household, "name", "household_id")

    # User check
    if str(payload.user_id) != str(user["user_id"]):
        raise HTTPException(status_code=403, detail="Cannot create debts for another user")

    # --- Membership checks ---
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
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
    )
    save_version(debt, "debts", "debt_id")

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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_current=True,
            is_deleted=False,
        )
        save_version(entry, "entries", "entry_id")
        entries.append(entry)

    return {
        "message": "Debt created",
        "debt_id": str(debt.debt_id),
        "installments": payload.installments,
        "entries": [str(e.entry_id) for e in entries]
    }

@router.delete("/{debt_id}")
def delete_debt(debt_id: UUID, user=Depends(get_current_user)):
    # Cascade to child entries handled inside storage
    return soft_delete_record(
        "debts", str(debt_id), "debt_id", Debt,
        user=user, owner_field="user_id", require_owner=True
    )


@router.get("/")
def list_debts(user=Depends(get_current_user)):
    df = load_versions("debts", Debt)
    df = df[
        (df["is_current"]) &
        (~df["is_deleted"].fillna(False)) &
        (df["user_id"] == str(user["user_id"]))
    ]
    return df.to_dict(orient="records")

