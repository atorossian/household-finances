from fastapi import APIRouter, HTTPException, Depends
from uuid import UUID, uuid4
from datetime import datetime, timezone
from app.models.schemas import Account, Household, User
from app.services.storage import load_versions, save_version, mark_old_version_as_stale
from app.services.auth import get_current_user

router = APIRouter()


@router.post("/")
def create_account(account: Household, user=Depends(get_current_user)):
    new_account = Account(
        account_id=uuid4(),
        name=account.name,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False
    )
    save_version(new_account, "accounts", "account_id")
    return {"message": "Account created", "account_id": str(new_account.account_id)}


@router.put("/{account_id}")
def update_account(account_id: UUID, name: str):
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
    return {"message": "Account updated", "account_id": str(account_id)}


@router.post("/{account_id}/delete")
def soft_delete_account(account_id: UUID):
    mark_old_version_as_stale("accounts", account_id, "account_id")
    accounts = load_versions("accounts", Account)
    current = accounts[accounts["account_id"] == str(account_id)].iloc[-1].to_dict()
    deleted = Account(
        account_id=account_id,
        name=current["name"],
        created_at=current["created_at"],
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=True
    )
    save_version(deleted, "accounts", "account_id")
    return {"message": "Account deleted", "account_id": str(account_id)}


@router.get("/")
def list_accounts():
    accounts = load_versions("accounts", Account)
    current = accounts[(accounts["is_current"] == True) & (accounts["is_deleted"] == False)]
    return current.to_dict(orient="records")


@router.get("   /{account_id}")
def get_account(account_id: UUID):
    accounts = load_versions("accounts", Account)
    record = accounts[(accounts["account_id"] == str(account_id)) & (accounts["is_current"])]
    if record.empty:
        raise HTTPException(status_code=404, detail="Account not found")
    return record.iloc[0].to_dict()


@router.post("/users/{user_id}/assign-account")
def assign_account_to_user(user_id: UUID, account_id: UUID):
    mark_old_version_as_stale("users", user_id, "user_id")
    users = load_versions("users", User)
    current = users[users["user_id"] == str(user_id)].iloc[-1].to_dict()
    updated = User(
        **{k: current[k] for k in User.model_fields if k in current},
        account_id=account_id,
        updated_at=datetime.now(timezone.utc),
        is_current=True
    )
    save_version(updated, "users", "user_id")
    return {"message": "User assigned to account", "user_id": str(user_id), "account_id": str(account_id)}