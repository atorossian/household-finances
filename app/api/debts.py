
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pandas as pd
from app.models.schemas import Debt, Entry, EntryType, Category
from app.services.storage import save_version, mark_old_version_as_stale
from app.services.auth import get_current_user

router = APIRouter()

@router.post("/")
def create_debt(payload: Debt, user=Depends(get_current_user)):
    # Ensure user creating is the same as payload user
    if str(payload.user_id) != str(user["user_id"]):
        raise HTTPException(status_code=403, detail="Cannot create debts for another user")

    debt = Debt(**payload.dict())
    save_version(debt, "debts", "debt_id")

    # --- Generate installments ---
    installment_value = round(payload.principal / payload.installments, 2)
    entries = []

    for i in range(payload.installments):
        due_date = (payload.start_date + pd.DateOffset(months=i)).replace(day=payload.due_day)

        entry = Entry(
            entry_id=uuid4(),
            user_id=payload.user_id,
            account_id=payload.account_id,
            household_id=payload.household_id,
            entry_date=due_date.date(),
            value_date=due_date.date(),
            type=EntryType.expense,
            category=Category.financing,
            amount=installment_value,
            description=f"{payload.name} installment {i+1}/{payload.installments}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_current=True,
        )
        save_version(entry, "entries", "entry_id")
        entries.append(entry)

    return {
        "message": "Debt created",
        "debt_id": str(debt.debt_id),
        "installments": payload.installments
    }
