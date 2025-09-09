from fastapi import APIRouter, HTTPException, Depends
from uuid import uuid4
from datetime import datetime, timezone
import bcrypt
import boto3
import re
from uuid import UUID, uuid4
import jwt
from app.models.schemas import RegisterRequest, LoginRequest, UserUpdateRequest, User, RefreshToken, UserAccount, UserHousehold
from app.services.storage import load_versions, save_version, mark_old_version_as_stale, cascade_stale
from app.services.auth import get_current_user, create_access_token, create_refresh_token, SECRET_KEY, ALGORITHM

router = APIRouter()

@router.post("/register")
def register_user(request: RegisterRequest):
    users_df = load_versions("users", User)

    if request.email in users_df["email"].values:
        raise HTTPException(status_code=400, detail="Email already registered")
    salt = bcrypt.gensalt()
    new_user = User(
        user_id=uuid4(),
        user_name=request.user_name,
        email=request.email,
        hashed_password=bcrypt.hashpw(request.password.encode('utf-8'), salt),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
        is_active=True
    )

    save_version(new_user, "users", "user_id")
    return {
        "message": "User registered successfully",
        "user_id": str(new_user.user_id)
    }


@router.post("/login")
def login_user(request: LoginRequest):
    users_df = load_versions("users", User)
    row = users_df[
        (users_df["email"] == request.email)
        & (users_df["is_current"])
        & (~users_df["is_deleted"])
    ]

    user = row.iloc[0]

    if row.empty or not bcrypt.checkpw(request.password.encode('utf-8'), user["hashed_password"].encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token({"sub": user.user_id})
    refresh_token = create_refresh_token(user.user_id)

    return {
        "message": "Login successful",
        "user_id": user["user_id"],
        "access_token": access_token, 
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.put("/{user_id}")
def update_user(user_id: UUID, update: UserUpdateRequest, user=Depends(get_current_user)):
    users_df = load_versions("users", User)
    mark_old_version_as_stale("users", user_id, "user_id")

    old = users_df[users_df["user_id"] == str(user_id)].iloc[-1].to_dict()
    salt = bcrypt.gensalt()
    updated_user = User(
        user_id=user_id,
        user_name=update.user_name or old["user_name"],
        email=update.email or old["email"],
        hashed_password=bcrypt.hashpw(update.password.encode('utf-8'), salt) if update.password else old["hashed_password"],
        created_at=old["created_at"],
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
        is_active=True
    )

    save_version(updated_user, "users", "user_id")
    return {"message": "User updated successfully", "user_id": str(user_id)}


@router.post("/{user_id}/delete")
def soft_delete_user(user_id: UUID, user=Depends(get_current_user)):
    mark_old_version_as_stale("users", user_id, "user_id")

    now = datetime.now(timezone.utc)
    deleted = User(
        user_id=user_id,
        email="deleted",
        user_name="deleted",
        hashed_password="",
        created_at=now,
        updated_at=now,
        is_current=True,
        is_deleted=True,
        is_active=False,
    )
    save_version(deleted, "users", "user_id")

    # Cascade delete memberships
    cascade_stale("users", str(user_id), "user_accounts", "user_id")
    cascade_stale("users", str(user_id), "user_households", "user_id")

    return {"message": "User soft-deleted successfully", "user_id": str(user_id)}


@router.post("/refresh")
def refresh_tokens(refresh_token: str):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        token_id = payload.get("jti")

        if not user_id or not token_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Verify token in S3
        df = load_versions("refresh_tokens", schema=RefreshToken)
        token_row = df[(df["refresh_token_id"] == token_id) & (df["is_current"])]

        if token_row.empty:
            raise HTTPException(status_code=401, detail="Token expired or already used")

        # Mark old refresh token as stale (rotation)
        mark_old_version_as_stale("refresh_tokens", token_id, "refresh_token_id")

        # Issue new tokens
        access_token = create_access_token({"sub": user_id})
        new_refresh_token = create_refresh_token(user_id)

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/change-password")
def change_password(current_password: str, new_password: str, user=Depends(get_current_user)):

    users_df = load_versions("users", User)
    row = users_df[(users_df["user_id"] == str(user["user_id"])) & (users_df["is_current"])]
    
    user = row.iloc[0]

    if row.empty or not bcrypt.checkpw(current_password.encode('utf-8'), user["hashed_password"].encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", new_password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", new_password):
        raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter")
    if not re.search(r"\d", new_password):
        raise HTTPException(status_code=400, detail="Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", new_password):
        raise HTTPException(status_code=400, detail="Password must contain at least one special character")

    mark_old_version_as_stale("users", user["user_id"], "user_id")
    salt = bcrypt.gensalt()
    # Create new version with new password
    updated_user = User(
        user_id=user["user_id"],
        user_name=user["user_name"],
        email=user["email"],
        hashed_password=bcrypt.hashpw(new_password.encode('utf-8'), salt),
        created_at=user["created_at"],
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
    )
    save_version(updated_user, "users", "user_id")

    # Invalidate refresh tokens for this user
    tokens_df = load_versions("refresh_tokens", schema=RefreshToken)
    user_tokens = tokens_df[(tokens_df["user_id"] == str(user["user_id"])) & (tokens_df["is_current"])]

    for _, token in user_tokens.iterrows():
        mark_old_version_as_stale("refresh_tokens", token["refresh_token_id"], "refresh_token_id")

    return {"message": "Password changed successfully. Please log in again."}