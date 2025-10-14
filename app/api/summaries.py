from fastapi import APIRouter, Depends, Query
import pandas as pd
from uuid import UUID
from app.services.storage import load_versions, resolve_name_by_id
from app.services.auth import get_current_user
from app.services.roles import require_household_role
from app.models.schemas.entry import Entry
from app.models.schemas.account import Account
from app.models.schemas.household import Household
from app.models.enums import Role

router = APIRouter()


@router.get("/summary")
def get_entry_summary(
    month: str | None = Query(None, description="Month in YYYY-MM format"),
    start: str | None = Query(None, description="Start month YYYY-MM"),
    end: str | None = Query(None, description="End month YYYY-MM"),
    last_n_months: int | None = Query(None, description="Last N months to include"),
    type: str | None = Query(None, description="Optional filter: income or expense"),
    household_id: UUID | None = Query(None, description="Restrict to a specific household"),
    user=Depends(get_current_user),
):
    df = load_versions("entries", Entry)

    # --- Base filter ---
    df = df[(df["is_current"]) & (~df["is_deleted"].fillna(False)) & (df["user_id"] == str(user["user_id"]))]
    if df.empty:
        return {"message": "No entries available"}

    # Normalize dates and types
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["type"] = df["type"].astype(str)

    # --- Household filter ---
    if household_id:
        require_household_role(user, household_id, required_role=Role.member)
        df = df[df["household_id"] == str(household_id)]

    # --- Date filtering ---
    # If last_n_months is given without explicit start/end/month, anchor to the latest entry month
    if last_n_months and not any([start, end, month]):
        anchor = df["entry_date"].max()  # last date in the dataset
        anchor_month_start = anchor.to_period("M").to_timestamp()  # YYYY-MM-01
        cutoff = anchor_month_start - pd.DateOffset(months=last_n_months - 1)
        window_end = anchor_month_start + pd.offsets.MonthEnd(1)  # exclusive end of anchor month
        df = df[(df["entry_date"] >= cutoff) & (df["entry_date"] < window_end)]
    elif last_n_months:
        # (kept for completeness if you also pass month/start/end)
        today = pd.to_datetime("today").normalize()
        cutoff = (today - pd.DateOffset(months=last_n_months - 1)).replace(day=1)
        df = df[df["entry_date"] >= cutoff]
    elif start and end:
        start_date = pd.to_datetime(start + "-01")
        end_date = pd.to_datetime(end + "-01") + pd.offsets.MonthEnd(1)
        df = df[(df["entry_date"] >= start_date) & (df["entry_date"] <= end_date)]
    elif month:
        # Compare on YYYY-MM strings for stability
        df = df[df["entry_date"].dt.strftime("%Y-%m") == month]

    if type:
        df = df[df["type"] == type]

    if df.empty:
        return {"message": "No entries for given filters"}

    # Precompute month label for grouping
    df["month"] = df["entry_date"].dt.strftime("%Y-%m")

    # --- Resolve account & household names ---
    df["account_name"] = df["account_id"].apply(
        lambda x: resolve_name_by_id("accounts", x, Account, "account_id", "name")
    )
    df["household_name"] = df["household_id"].apply(
        lambda x: resolve_name_by_id("households", x, Household, "household_id", "name")
    )

    # --- Aggregate summaries ---
    total = float(df["amount"].sum())
    by_category = df.groupby("category")["amount"].sum().to_dict()
    by_account = df.groupby("account_name")["amount"].sum().to_dict()
    by_household = df.groupby("household_name")["amount"].sum().to_dict()

    # --- Trends (only when a multi-month window is requested) ---
    type_trends = category_trends = None
    if last_n_months or (start and end):
        type_trends = (
            df.groupby(["month", "type"], as_index=False)["amount"]
            .sum()
            .rename(columns={"amount": "amount"})
            .to_dict("records")
        )
        category_trends = (
            df.groupby(["month", "category"], as_index=False)["amount"]
            .sum()
            .rename(columns={"amount": "amount"})
            .to_dict("records")
        )

    return {
        "total": round(total, 2),
        "by_category": {k: round(float(v), 2) for k, v in by_category.items()},
        "by_account": {k: round(float(v), 2) for k, v in by_account.items()},
        "by_household": {k: round(float(v), 2) for k, v in by_household.items()},
        "type_trends": type_trends,
        "category_trends": category_trends,
    }
