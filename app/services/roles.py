from uuid import UUID
from app.services.storage import load_versions
from app.models.schemas.membership import UserHousehold, UserAccount
from fastapi import HTTPException
from app.models.enums import Role

ROLE_WEIGHT = {"reader": 1, "member": 2, "admin": 3}


def get_membership(user_id: UUID, household_id: UUID) -> dict | None:
    df = load_versions("user_households", UserHousehold)
    if df.empty:
        return None

    # Element-wise string comparison, and guard flags correctly
    df = df[
        (df["user_id"].astype(str) == str(user_id))
        & (df["household_id"].astype(str) == str(household_id))
        & (df["is_current"])
        & (~df.get("is_deleted", False).fillna(False))
    ]
    if df.empty:
        return None

    # Normalize role to str before weighting
    df = df.copy()
    df["weight"] = df["role"].astype(str).map(ROLE_WEIGHT)
    row = df.sort_values("weight", ascending=False).iloc[0].to_dict()
    return row


def require_household_role(user: dict, household_id: UUID, required_role: str):
    """
    Check if user has at least the required role in the household.
    Superusers always pass.
    """
    if user.get("is_superuser"):
        return

    if isinstance(user["user_id"], str):
        user["user_id"] = UUID(user["user_id"])

    mem = get_membership(user["user_id"], household_id)
    if not mem:
        raise HTTPException(status_code=403, detail=f"{required_role} role required for this household")

    # Ensure we compare with string keys even if mem['role'] is a Role enum
    if ROLE_WEIGHT[str(mem["role"])] < ROLE_WEIGHT[str(required_role)]:
        raise HTTPException(status_code=403, detail=f"{required_role} role required for this household")


def require_account_access(user: dict, account: dict, min_role: str = "member"):
    # first check household-level access
    require_household_role(user, account["household_id"], required_role=Role(min_role))

    # then tighten: if not admin/superuser, must be assigned to the account
    mem = get_membership(UUID(user["user_id"]), UUID(account["household_id"]))
    if not user.get("is_superuser") and mem and mem["role"] != "admin":
        ua = load_versions("user_accounts", UserAccount)
        ua = ua[(ua["is_current"]) & (~ua.get("is_deleted", False).fillna(False))]
        assigned = not ua[
            (ua["user_id"] == str(user["user_id"])) & (ua["account_id"] == str(account["account_id"]))
        ].empty
        if not assigned:
            raise HTTPException(status_code=403, detail="Not assigned to this account")


def validate_entry_permissions(user_id: UUID, account_id: UUID, household_id: UUID, acting_user: dict):
    """
    Validate that:
    1. Acting user is the same as entry.user_id
    2. User is member of the household
    3. User is assigned to the account
    """

    if str(user_id) != str(acting_user["user_id"]):
        raise HTTPException(status_code=403, detail="Cannot operate on another user's entries")

    # Check household membership
    hh = load_versions("user_households", UserHousehold)
    hh_match = hh[
        (hh["user_id"] == str(user_id))
        & (hh["household_id"] == str(household_id))
        & (hh["is_current"])
        & (~hh.get("is_deleted", False).fillna(False))
    ]
    if hh_match.empty:
        raise HTTPException(status_code=403, detail="User not part of household")

    # Check account membership
    acc = load_versions("user_accounts", UserAccount)
    acc_match = acc[
        (acc["user_id"] == str(user_id))
        & (acc["account_id"] == str(account_id))
        & (acc["is_current"])
        & (~acc.get("is_deleted", False).fillna(False))
    ]
    if acc_match.empty:
        raise HTTPException(status_code=403, detail="User not assigned to account")
