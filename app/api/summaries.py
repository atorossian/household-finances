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
    df = df[(df["is_current"]) & (~df["is_deleted"])]

    # Filter by month
    try:
        month_start = pd.to_datetime(month + "-01")
        month_end = (month_start + pd.offsets.MonthEnd(1))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid month format, expected YYYY-MM")

    df = df[(pd.to_datetime(df["entry_date"]) >= month_start) & (pd.to_datetime(df["entry_date"]) <= month_end)]

    # Optional filter by type (income/expense)
    if type:
        df = df[df["type"] == type]

    if df.empty:
        return {"message": "No entries found", "summary": {}}

    # Resolve account/household names for grouping
    df["account_name"] = df["account_id"].apply(lambda x: resolve_name_by_id("accounts", x, Account, "account_id", "name"))
    df["household_name"] = df["household_id"].apply(lambda x: resolve_name_by_id("households", x, Household, "household_id", "name"))

    # Aggregate summaries
    summary = {
        "by_category": df.groupby("category")["amount"].sum().to_dict(),
        "by_account": df.groupby("account_name")["amount"].sum().to_dict(),
        "by_household": df.groupby("household_name")["amount"].sum().to_dict(),
        "total": df["amount"].sum()
    }

    return {"month": month, "type": type, "summary": summary}
