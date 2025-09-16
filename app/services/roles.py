from app.services.storage import load_versions
from app.models.schemas import UserHousehold
import pandas as pd
from fastapi import HTTPException

ROLE_WEIGHT = {"reader": 1, "member": 2, "admin": 3}

def get_membership(user_id: str, household_id: str) -> dict | None:
    df = load_versions("user_households", UserHousehold)
    if df.empty:
        return None
    df = df[(df["user_id"] == user_id) &
            (df["household_id"] == household_id) &
            (df["is_current"]) &
            (~df.get("is_deleted", False).fillna(False))]
    if df.empty:
        return None
    # If multiple, take the highest role
    df["weight"] = df["role"].map(ROLE_WEIGHT)
    row = df.sort_values("weight", ascending=False).iloc[0].to_dict()
    return row

def require_household_role(user: dict, household_id: str, min_role: str):
    """
    Check if user has at least the required role in the household.
    Superusers always pass.
    """
    if user.get("is_superuser"):
        return
    
    mem = get_membership(str(user["user_id"]), str(household_id))
    if not mem:
        raise HTTPException(status_code=403, detail=f"{min_role} role required for this household")

    if ROLE_WEIGHT[mem["role"]] < ROLE_WEIGHT[min_role]:
        raise HTTPException(status_code=403, detail=f"{min_role} role required for this household")

