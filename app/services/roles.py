from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException

from app.models.enums import Role
from app.models.schemas.membership import UserHousehold, UserAccount
from app.services.storage import load_versions

# Weight map keyed by Role (not str)
ROLE_WEIGHT: Dict[Role, int] = {Role.reader: 1, Role.member: 2, Role.admin: 3}


def to_role(v: Role | str) -> Role:
    """Normalize incoming value to a Role enum."""
    return v if isinstance(v, Role) else Role(v)


def get_membership(user_id: UUID, household_id: UUID) -> Optional[Dict[str, Any]]:
    """
    Return the highest-weight membership row for the given user/household
    as a plain dict, or None if no active membership.
    """
    df = load_versions("user_households", UserHousehold)
    if df.empty:
        return None

    df = df[
        (df["user_id"].astype(str) == str(user_id))
        & (df["household_id"].astype(str) == str(household_id))
        & (df["is_current"])
        & (~df.get("is_deleted", False).fillna(False))
    ]
    if df.empty:
        return None

    # Ensure we compute weight using Role keys
    df = df.copy()
    df["weight"] = df["role"].map(lambda v: ROLE_WEIGHT[to_role(v)])
    row = df.sort_values("weight", ascending=False).iloc[0].to_dict()
    return row


def require_household_role(user: Dict[str, Any], household_id: UUID, required_role: Role) -> None:
    """
    Ensure the user has at least the required household role.
    Superusers always pass.
    """
    if user.get("is_superuser"):
        return

    # Normalize user_id in case it's a str
    uid = user["user_id"]
    uid_uuid = uid if isinstance(uid, UUID) else UUID(str(uid))

    mem = get_membership(uid_uuid, household_id)
    if not mem:
        raise HTTPException(status_code=403, detail=f"{required_role} role required for this household")

    user_role = to_role(mem["role"])
    if ROLE_WEIGHT[user_role] < ROLE_WEIGHT[required_role]:
        raise HTTPException(status_code=403, detail=f"{required_role} role required for this household")


def require_account_access(user: Dict[str, Any], account: Dict[str, Any], min_role: Role = Role.member) -> None:
    """
    Household-level gate by min_role, then (if not admin/superuser) require
    explicit assignment to the account.
    """
    # 1) Household-level role check
    hh_id = account["household_id"]
    hh_uuid = hh_id if isinstance(hh_id, UUID) else UUID(str(hh_id))
    require_household_role(user, hh_uuid, required_role=min_role)

    # 2) If not superuser/admin, must be assigned to the account
    if user.get("is_superuser"):
        return

    uid = user["user_id"]
    uid_str = str(uid)
    mem = get_membership(hh_uuid, hh_uuid)  # not used; keep logic simple below
    # Prefer using the role from membership we already satisfied:
    # If we want to avoid second read, we can re-fetch or simply trust min_role gate.
    # We'll fetch to know if user is admin:
    mem = get_membership(UUID(uid_str), hh_uuid)
    if mem is not None and to_role(mem["role"]) == Role.admin:
        return

    ua = load_versions("user_accounts", UserAccount)
    ua = ua[(ua["is_current"]) & (~ua.get("is_deleted", False).fillna(False))]
    assigned = not ua[
        (ua["user_id"].astype(str) == uid_str) & (ua["account_id"].astype(str) == str(account["account_id"]))
    ].empty
    if not assigned:
        raise HTTPException(status_code=403, detail="Not assigned to this account")


def validate_entry_permissions(
    user_id: UUID, account_id: UUID, household_id: UUID, acting_user: Dict[str, Any]
) -> None:
    """
    Validate that:
      1) acting_user is the same as entry.user_id
      2) User is member of the household
      3) User is assigned to the account
    """
    if str(user_id) != str(acting_user["user_id"]):
        raise HTTPException(status_code=403, detail="Cannot operate on another user's entries")

    # Check household membership
    hh = load_versions("user_households", UserHousehold)
    hh_match = hh[
        (hh["user_id"].astype(str) == str(user_id))
        & (hh["household_id"].astype(str) == str(household_id))
        & (hh["is_current"])
        & (~hh.get("is_deleted", False).fillna(False))
    ]
    if hh_match.empty:
        raise HTTPException(status_code=403, detail="User not part of household")

    # Check account membership
    acc = load_versions("user_accounts", UserAccount)
    acc_match = acc[
        (acc["user_id"].astype(str) == str(user_id))
        & (acc["account_id"].astype(str) == str(account_id))
        & (acc["is_current"])
        & (~acc.get("is_deleted", False).fillna(False))
    ]
    if acc_match.empty:
        raise HTTPException(status_code=403, detail="User not assigned to account")
