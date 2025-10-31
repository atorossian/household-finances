from typing import Any, Dict, Optional
from uuid import UUID
from fastapi import HTTPException
from app.models.enums import Role
from app.models.schemas.membership import UserAccount, UserHousehold
from app.services.storage import load_versions

ROLE_WEIGHT: Dict[Role, int] = {Role.reader: 1, Role.member: 2, Role.admin: 3}


def parse_role(v: Role | str) -> Role:
    return v if isinstance(v, Role) else Role(v)


def get_membership(user_id: UUID, household_id: UUID) -> Optional[Dict[str, Any]]:
    df = load_versions("user_households", UserHousehold)
    if df.empty:
        return None
    df = df[
        (df["is_current"])
        & (~df.get("is_deleted", False).fillna(False))
        & (df["user_id"].astype(str) == str(user_id))
        & (df["household_id"].astype(str) == str(household_id))
    ]
    if df.empty:
        return None
    df = df.copy()
    df["role_enum"] = df["role"].apply(parse_role)
    df["weight"] = df["role_enum"].map(ROLE_WEIGHT)
    row = df.sort_values("weight", ascending=False).iloc[0].to_dict()
    row["role"] = row.get("role_enum")
    return row


def require_household_role(user: Dict[str, Any], household_id: UUID, required_role: Role | str) -> None:
    if user.get("is_superuser"):
        return

    u_id = user.get("user_id")
    u_uuid = u_id if isinstance(u_id, UUID) else UUID(str(u_id))

    _mem = get_membership(u_uuid, household_id)
    if _mem is None:
        raise HTTPException(
            status_code=403, detail=f"{parse_role(required_role).value} role required for this household"
        )
    mem: Dict[str, Any] = _mem  # <- non-optional from here on

    mem_role_raw = mem.get("role")
    if mem_role_raw is None:
        raise HTTPException(
            status_code=403, detail=f"{parse_role(required_role).value} role required for this household"
        )

    current = parse_role(mem_role_raw)
    required = parse_role(required_role)
    if ROLE_WEIGHT[current] < ROLE_WEIGHT[required]:
        raise HTTPException(status_code=403, detail=f"{required.value} role required for this household")


def require_account_access(user: Dict[str, Any], account: Dict[str, Any], min_role: Role | str = Role.member) -> None:
    hh_id_val = account["household_id"]
    hh_uuid = hh_id_val if isinstance(hh_id_val, UUID) else UUID(str(hh_id_val))

    # Enforce household-level permission
    require_household_role(user, hh_uuid, required_role=min_role)

    if user.get("is_superuser"):
        return

    u_id = user.get("user_id")
    u_uuid = u_id if isinstance(u_id, UUID) else UUID(str(u_id))

    _mem = get_membership(u_uuid, hh_uuid)
    mem_role_obj: Optional[Role] = None
    if _mem is not None:
        mem: Dict[str, Any] = _mem  # <- promote to non-optional
        role_raw = mem.get("role")
        if role_raw is not None:
            mem_role_obj = parse_role(role_raw)

    # Admins bypass account assignment
    if mem_role_obj == Role.admin:
        return

    acc_id_val = account["account_id"]
    acc_uuid_str = str(acc_id_val)

    ua = load_versions("user_accounts", UserAccount)
    assigned = False
    if not ua.empty:
        ua = ua[(ua["is_current"]) & (~ua.get("is_deleted", False).fillna(False))]
        assigned = not ua[
            (ua["user_id"].astype(str) == str(u_uuid)) & (ua["account_id"].astype(str) == acc_uuid_str)
        ].empty

    if not assigned:
        raise HTTPException(status_code=403, detail="Not assigned to this account")


def validate_entry_permissions(
    user_id: UUID, account_id: UUID, household_id: UUID, acting_user: Dict[str, Any]
) -> None:
    """
    Validate that:
    1) Acting user is the same as entry.user_id
    2) User is member of the household
    3) User is assigned to the account
    """
    if str(user_id) != str(acting_user.get("user_id")):
        raise HTTPException(status_code=403, detail="Cannot operate on another user's entries")

    # Check household membership
    hh = load_versions("user_households", UserHousehold)
    hh_match = hh[
        (hh["is_current"])
        & (~hh.get("is_deleted", False).fillna(False))
        & (hh["user_id"].astype(str) == str(user_id))
        & (hh["household_id"].astype(str) == str(household_id))
    ]
    if hh_match.empty:
        raise HTTPException(status_code=403, detail="User not part of household")

    # Check account membership
    acc = load_versions("user_accounts", UserAccount)
    acc_match = acc[
        (acc["is_current"])
        & (~acc.get("is_deleted", False).fillna(False))
        & (acc["user_id"].astype(str) == str(user_id))
        & (acc["account_id"].astype(str) == str(account_id))
    ]
    if acc_match.empty:
        raise HTTPException(status_code=403, detail="User not assigned to account")
