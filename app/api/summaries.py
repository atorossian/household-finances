from fastapi import APIRouter, Depends, Query, HTTPException
import pandas as pd
from app.services.storage import load_versions, resolve_name_by_id
from app.services.auth import get_current_user
from app.models.schemas import Entry, Account, Household

router = APIRouter()

@router.get("/summary")
def get_entry_summary(
    month: str | None = Query(None, description="Month in YYYY-MM format"),
    start: str | None = Query(None, description="Start month YYYY-MM"),
    end: str | None = Query(None, description="End month YYYY-MM"),
    last_n_months: int | None = Query(None, description="Last N months to include"),
    type: str | None = Query(None, description="Optional filter: income or expense"),
    user=Depends(get_current_user),
):
    df = load_versions("entries", Entry)

    # --- Base filter ---
    df = df[
        (df["is_current"]) &
        (~df["is_deleted"].fillna(False)) &
        (df["user_id"] == str(user["user_id"]))
    ]
    if df.empty:
        return {"message": "No entries available"}

    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["month"] = df["entry_date"].dt.to_period("M")

    # --- Date filtering ---
    if last_n_months:
        today = pd.to_datetime("today").normalize()
        cutoff = (today - pd.DateOffset(months=last_n_months - 1)).replace(day=1)
        df = df[df["entry_date"] >= cutoff]
    elif start and end:
        start_date = pd.to_datetime(start + "-01")
        end_date = pd.to_datetime(end + "-01") + pd.offsets.MonthEnd(1)
        df = df[(df["entry_date"] >= start_date) & (df["entry_date"] <= end_date)]
    elif month:
        df = df[df["month"] == month]

    if type:
        df = df[df["type"] == type]

    if df.empty:
        return {"message": "No entries for given filters"}

    # --- Resolve account & household names ---
    df["account_name"] = df["account_id"].apply(lambda x: resolve_name_by_id("accounts", x, Account, "account_id", "name"))
    df["household_name"] = df["household_id"].apply(lambda x: resolve_name_by_id("households", x, Household, "household_id", "name"))

    # --- Aggregate summaries ---
    total = df["amount"].sum()
    by_category = df.groupby("category")["amount"].sum().to_dict()
    by_account = df.groupby("account_name")["amount"].sum().to_dict()
    by_household = df.groupby("household_name")["amount"].sum().to_dict()

    # --- Trends ---
    type_trends, category_trends = None, None
    if last_n_months or (start and end):
        # Type-level trends (income vs expense vs net)
        type_trends = df.groupby(["month", "type"])["amount"].sum().unstack(fill_value=0)
        type_trends["net"] = type_trends.get("income", 0) - type_trends.get("expense", 0)
        type_trends = type_trends.reset_index().to_dict(orient="records")

        # Category-level trends
        category_trends = df.groupby(["month", "category"])["amount"].sum().unstack(fill_value=0)
        category_trends = category_trends.reset_index().to_dict(orient="records")

    return {
        "total": round(total, 2),
        "by_category": {k: round(v, 2) for k, v in by_category.items()},
        "by_account": {k: round(v, 2) for k, v in by_account.items()},
        "by_household": {k: round(v, 2) for k, v in by_household.items()},
        "type_trends": type_trends,
        "category_trends": category_trends,
    }
