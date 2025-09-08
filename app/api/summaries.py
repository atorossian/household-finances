from fastapi import APIRouter, Depends, Query, HTTPException
import pandas as pd
from app.services.storage import load_versions, resolve_name_by_id
from app.services.auth import get_current_user
from app.models.schemas import Entry, Account, Household

router = APIRouter()

@router.get("/summary")
def get_entry_summary(
    month: str = Query(..., description="Month in YYYY-MM format"),
    type: str = Query(None, description="Optional filter: income or expense"),
    user=Depends(get_current_user)
):
    df = load_versions("entries", Entry)

    # Filter only current, non-deleted entries
    df = df[
        (df["is_current"]) &
        (~df["is_deleted"].fillna(False)) &
        (df["user_id"] == str(user["user_id"]))
    ]

    # Filter by month
    try:
        month_start = pd.to_datetime(month + "-01")
        month_end = (month_start + pd.offsets.MonthEnd(1))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid month format, expected YYYY-MM")

    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df = df[df["entry_date"].dt.strftime("%Y-%m") == month]

    if type:
        df = df[df["type"] == type]

    if df.empty:
        return {"month": month, "total": 0.0, "by_category": {}, "by_account": {}, "by_household": {}}
    # Resolve account/household names for grouping
    df["account_name"] = df["account_id"].apply(lambda x: resolve_name_by_id("accounts", x, Account, "account_id", "name"))
    df["household_name"] = df["household_id"].apply(lambda x: resolve_name_by_id("households", x, Household, "household_id", "name"))

    total = df["amount"].sum()
    by_category = df.groupby("category")["amount"].sum().to_dict()
    by_account = df.groupby("account_name")["amount"].sum().to_dict()
    by_household = df.groupby("household_name")["amount"].sum().to_dict()

    return {
        "month": month,
        "type": type,
        "total": round(total, 2),
        "by_category": {k: round(v, 2) for k, v in by_category.items()},
        "by_account": {k: round(v, 2) for k, v in by_account.items()},
        "by_household": {k: round(v, 2) for k, v in by_household.items()}
    }
