from fastapi import APIRouter, HTTPException, Depends
from uuid import uuid4
from datetime import datetime, timezone
from passlib.hash import bcrypt
import boto3
from app.models.schemas import RegisterRequest, LoginRequest, UserUpdateRequest, User
from app.services.storage import load_versions, save_version, mark_old_version_as_stale
from uuid import UUID, uuid4
from app.services.auth import get_current_user


s3 = boto3.client("s3")
BUCKET_NAME = "household-finances"

router = APIRouter()

@router.post("/register")
def register_user(request: RegisterRequest):
    users_df = load_versions("users")
    if request.email in users_df["email"].values:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        user_id=uuid4(),
        user_name=request.user_name,
        email=request.email,
        hashed_password=bcrypt.hash(request.password),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
        is_active=True
    )

    save_version(new_user, "users", "user_id")
    return {"message": "User registered", "user_id": str(new_user.user_id)}


@router.post("/login")
def login_user(request: LoginRequest):
    users_df = load_versions("users")
    row = users_df[
        (users_df["email"] == request.email)
        & (users_df["is_current"])
        & (~users_df["is_deleted"])
    ]

    if row.empty or not bcrypt.verify(request.password, row.iloc[0]["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {"message": "Login successful", "user_id": row.iloc[0]["user_id"]}


@router.put("/{user_id}")
def update_user(user_id: UUID, update: UserUpdateRequest, user=Depends(get_current_user)):
    users_df = load_versions("users")
    mark_old_version_as_stale("users", user_id, "user_id")

    old = users_df[users_df["user_id"] == str(user_id)].iloc[-1].to_dict()

    updated_user = User(
        user_id=user_id,
        user_name=update.user_name or old["user_name"],
        email=update.email or old["email"],
        hashed_password=bcrypt.hash(update.password) if update.password else old["hashed_password"],
        created_at=old["created_at"],
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
        is_active=True
    )

    save_version(updated_user, "users", "user_id")
    return {"message": "User updated", "user_id": str(user_id)}


@router.post("/{user_id}/delete")
def soft_delete_user(user_id: UUID, user=Depends(get_current_user)):
    users_df = load_versions("users")
    mark_old_version_as_stale("users", user_id, "user_id")

    old = users_df[users_df["user_id"] == str(user_id)].iloc[-1].to_dict()

    deleted_user = User(
        user_id=user_id,
        user_name=old["user_name"],
        email=old["email"],
        hashed_password=old["hashed_password"],
        created_at=old["created_at"],
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=True,
        is_active=False
    )

    save_version(deleted_user, "users", "user_id")
    return {"message": "User soft-deleted", "user_id": str(user_id)}