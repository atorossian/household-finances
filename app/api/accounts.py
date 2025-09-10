from fastapi import APIRouter, HTTPException, Depends
from uuid import UUID, uuid4
from datetime import datetime, timezone
from app.models.schemas import Account, Household, User, UserAccount
from app.services.storage import load_versions, save_version, mark_old_version_as_stale, soft_delete_record, log_action
from app.services.auth import get_current_user

router = APIRouter()


@router.post("/")
def create_account(payload: Account, user=Depends(get_current_user)):
    account = Account(
        account_id=uuid4(),
        name=payload.name,
        household_id=payload.household_id,
        user_id=payload.user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
    )
    save_version(account, "accounts", "account_id")
    log_action(user["user_id"], "create", "accounts", str(account.account_id), payload.model_dump())
    # Automatically assign the creator as a member
    mapping = UserAccount(user_id=user["user_id"], account_id=account.account_id)
    save_version(mapping, "user_accounts", "mapping_id")
    log_action(user["user_id"], "assign_user", "accounts", str(account.account_id), {"user_id": str(payload.user_id)})

    return {"message": "Account created", "account_id": str(account.account_id)}

@router.post("/assign-user-to-account")
def assign_user_to_account(user_id: UUID, account_id: UUID, user=Depends(get_current_user)):
    mapping = UserAccount(user_id=user_id, account_id=account_id)
    save_version(mapping, "user_accounts", "mapping_id")
    log_action(user["user_id"], "assign_user", "accounts", str(account_id), {"user_id": str(user_id)})
    return {"message": "User assigned to account"}

@router.put("/{account_id}")
def update_account(account_id: UUID, name: str, user=Depends(get_current_user)):
    mark_old_version_as_stale("accounts", account_id, "account_id")
    accounts = load_versions("accounts", Account)
    current = accounts[accounts["account_id"] == str(account_id)].iloc[-1].to_dict()
    updated = Account(
        account_id=account_id,
        name=name,
        created_at=current["created_at"],
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False
    )
    save_version(updated, "accounts", "account_id")
    log_action(user["user_id"], "update", "accounts", str(account_id), {"name": name})

    return {"message": "Account updated", "account_id": str(account_id)}


@router.delete("/{account_id}")
def delete_account(account_id: UUID, user=Depends(get_current_user)):

    return soft_delete_record(
        "accounts", str(account_id), "account_id", Account,
        user=user, owner_field="user_id", require_owner=True
    )


@router.get("/")
def list_accounts(user=Depends(get_current_user)):
    accounts = load_versions("accounts", Account)
    current = accounts[(accounts["is_current"] == True) & (accounts["is_deleted"] == False)]
    log_action(user["user_id"], "list", "accounts", None, {"count": len(current)})
    return current.to_dict(orient="records")

@router.get("/memberships")
def list_account_memberships(user=Depends(get_current_user)):
    df = load_versions("user_accounts", UserAccount)

    if df.empty:
        return []

    # Filter current + not deleted memberships
    df = df[
        (df["is_current"]) &
        (~df.get("is_deleted", False).fillna(False))
    ]
    log_action(user["user_id"], "list", "account_membership", None, {"count": len(df)})
    return df.to_dict(orient="records")

@router.get("/{account_id}")
def get_account(account_id: UUID, user=Depends(get_current_user)):
    accounts = load_versions("accounts", Account)
    record = accounts[(accounts["account_id"] == str(account_id)) & (accounts["is_current"])]
    if record.empty:
        raise HTTPException(status_code=404, detail="Account not found")
    
    log_action(user["user_id"], "get", "accounts", str(account_id))
    return record.iloc[0].to_dict()
