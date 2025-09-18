from fastapi import APIRouter, HTTPException, Depends
from uuid import UUID, uuid4
from datetime import datetime, timezone
from app.models.schemas.account import Account, AccountOut
from app.models.schemas.household import Household
from app.models.schemas.user import User
from app.models.schemas.membership import UserAccount, UserAccountOut
from app.services.storage import load_versions, save_version, mark_old_version_as_stale, soft_delete_record, log_action
from app.services.auth import get_current_user
from app.services.roles import require_household_role, get_membership, require_account_access
from app.services.utils import page_params
from app.services.fetchers import fetch_record

router = APIRouter()


@router.post("/")
def create_account(payload: Account, user=Depends(get_current_user)):
    require_household_role(user, payload.household_id, "admin")
    now = datetime.now(timezone.utc)
    account = Account(
        account_id=uuid4(),
        name=payload.name,
        household_id=payload.household_id,
        created_at=now,
        updated_at=now,
        is_current=True,
        is_deleted=False,
    )
    save_version(account, "accounts", "account_id")
    log_action(user["user_id"], "create", "accounts", str(account.account_id), payload.model_dump())

    return {"message": "Account created", "account_id": str(account.account_id)}

@router.post("/{account_id}/assign-user")
def assign_user_to_account(account_id: UUID, target_user_id: UUID, user=Depends(get_current_user)):
    acc_df = load_versions("accounts", Account, record_id=account_id)
    cur = acc_df[(acc_df["is_current"]) & (~acc_df["is_deleted"].fillna(False))]
    if cur.empty:
        raise HTTPException(status_code=404, detail="Account not found")
    acc = cur.iloc[0].to_dict()

    require_household_role(user, acc['household_id'], "admin")

    mem = get_membership(str(target_user_id), acc["household_id"])
    if not mem:
        raise HTTPException(status_code=400, detail="Assignee must be a member of the household")

    # Mark previous mapping as stale (enforce 1 user per account)
    ua = load_versions("user_accounts", UserAccount)
    existing = ua[(ua["account_id"] == str(account_id)) & (ua["is_current"]) & (~ua["is_deleted"].fillna(False))]
    for _, row in existing.iterrows():
        mark_old_version_as_stale("user_accounts", row["mapping_id"], "mapping_id")
        row_dict = row.to_dict()
        row_dict.update({"updated_at": datetime.now(timezone.utc), "is_current": True, "is_deleted": True})
        save_version(UserAccount(**row_dict), "user_accounts", "mapping_id")

    # Add new mapping
    mapping = UserAccount(user_id=target_user_id, account_id=account_id, role="member")
    save_version(mapping, "user_accounts", "mapping_id")

    log_action(user["user_id"], "assign_user", "accounts", str(account_id), {"user_id": str(target_user_id)})
    return {"message": "Account assigned", "account_id": str(account_id), "user_id": str(target_user_id)}


@router.put("/{account_id}")
def update_account(account_id: UUID, name: str, user=Depends(get_current_user)):
    acc_df = load_versions("accounts", Account, record_id=account_id)
    cur = acc_df[(acc_df["is_current"]) & (~acc_df["is_deleted"].fillna(False))]
    if cur.empty:
        raise HTTPException(status_code=404, detail="Account not found")
    acc = cur.iloc[0].to_dict()

    require_household_role(user, acc['household_id'], "admin")

    mark_old_version_as_stale("accounts", account_id, "account_id")
    
    updated = Account(
        account_id=account_id,
        name=name,
        household_id=cur["household_id"],
        created_at=cur["created_at"],
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False
    )
    save_version(updated, "accounts", "account_id")
    log_action(user["user_id"], "update", "accounts", str(account_id), {"name": name})

    return {"message": "Account updated", "account_id": str(account_id)}


@router.delete("/{account_id}")
def delete_account(account_id: UUID, user=Depends(get_current_user)):
    # Only admin of the household (or superuser)
    acc_df = load_versions("accounts", Account, record_id=account_id)
    cur = acc_df[(acc_df["is_current"]) & (~acc_df["is_deleted"].fillna(False))]
    if cur.empty:
        raise HTTPException(status_code=404, detail="Account not found")
    acc = cur.iloc[0].to_dict()
    require_household_role(user, acc['household_id'], "admin")

    resp = soft_delete_record(
        "accounts", str(account_id), "account_id", Account,
        user=user, require_owner=False  # ownership enforced by role above
    )

    log_action(user["user_id"], "delete", "accounts", str(account_id))
    return resp

@router.get("/", response_model=list[AccountOut])
def list_accounts(user=Depends(get_current_user), page=Depends(page_params)):
    accounts = load_versions("accounts", Account)
    current = accounts[(accounts["is_current"]) & (~accounts["is_deleted"].fillna(False))]

    # only return accounts where user has membership
    user_accounts = load_versions("user_accounts", UserAccount)
    memberships = user_accounts[(user_accounts["user_id"] == str(user["user_id"])) & (user_accounts["is_current"]) & (~user_accounts["is_deleted"].fillna(False))]
    allowed_ids = set(memberships["account_id"])

    current = current[current["account_id"].isin(allowed_ids)]
    current = current.iloc[page["offset"]: page["offset"] + page["limit"]]

    log_action(user["user_id"], "list", "accounts", None, {"count": len(current)})
    return current.to_dict(orient="records")

@router.get("/memberships", response_model=list[UserAccountOut])
def list_account_memberships(user=Depends(get_current_user), page=Depends(page_params)):
    df = load_versions("user_accounts", UserAccount)

    if df.empty:
        return []

    # Filter current + not deleted memberships
    df = df[
        (df["is_current"]) &
        (~df.get("is_deleted", False).fillna(False))
    ]
    df = df.iloc[page["offset"] : page["offset"] + page["limit"]]
    log_action(user["user_id"], "list", "account_membership", None, {"count": len(df)})
    return df.to_dict(orient="records")

@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: UUID, user=Depends(get_current_user)):
    row = fetch_record(
        "accounts", Account, str(account_id),
        permission_check=lambda r: require_account_access(user, r, min_role="member"),
        history=False,
    )
    log_action(user["user_id"], "get", "accounts", str(account_id))
    return row

@router.get("/{account_id}/history", response_model=list[AccountOut])
def get_account_history(account_id: UUID, user=Depends(get_current_user), page=Depends(page_params)):
    versions = fetch_record(
        "accounts", Account, str(account_id),
        permission_check=lambda r: require_account_access(user, r, min_role="member"),
        history=True, page=page, sort_by="updated_at",
    )
    log_action(user["user_id"], "get_history", "accounts", str(account_id), {"offset": page["offset"], "limit": page["limit"]})
    return versions
