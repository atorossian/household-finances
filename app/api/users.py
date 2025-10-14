from fastapi import APIRouter, HTTPException, Depends
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta
import bcrypt
import os
import secrets
import pandas as pd
import jwt
from app.services.utils import validate_password_strength, is_password_expired, normalize_email
from app.models.schemas.user import (
    RegisterRequest,
    LoginRequest,
    UserUpdateRequest,
    User,
    RefreshToken,
    PasswordHistory,
    PasswordResetToken,
)
from app.services.storage import load_versions, save_version, mark_old_version_as_stale, soft_delete_record, log_action
from app.services.auth import get_current_user, create_access_token, create_refresh_token, SECRET_KEY, ALGORITHM
from app.services.triggers import on_user_suspended, on_user_unsuspended, on_password_change

MIN_NUMBER_OF_PREVIOUS_PASSWORDS = 5
RESET_TOKEN_EXPIRY_HOURS = 1
MIN_NUMBER_OF_PREVIOUS_PASSWORDS = 3

router = APIRouter()


@router.post("/register")
def register_user(request: RegisterRequest):
    normalized_email = normalize_email(request.email)
    users_df = load_versions("users", User)

    if normalized_email in users_df["email"].values:
        raise HTTPException(status_code=400, detail="Email already registered")

    validate_password_strength(request.password)

    # Check if email matches bootstrap superuser email
    bootstrap_email = os.getenv("BOOTSTRAP_SUPERUSER_EMAIL", "").lower()
    is_superuser = request.email.lower() == bootstrap_email

    salt = bcrypt.gensalt()
    new_user = User(
        user_id=uuid4(),
        user_name=request.user_name,
        email=normalized_email,
        hashed_password=bcrypt.hashpw(request.password.encode("utf-8"), salt),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
        is_active=True,
        is_superuser=is_superuser,
    )

    save_version(new_user, "users", "user_id")
    log_action(str(new_user.user_id), "register", "users", str(new_user.user_id), request.model_dump())

    return {"message": "User registered successfully", "user_id": str(new_user.user_id)}


@router.post("/login")
def login_user(request: LoginRequest):
    users_df = load_versions("users", User)
    normalized_email = normalize_email(request.email)
    row = users_df[(users_df["email"] == normalized_email) & (users_df["is_current"]) & (~users_df["is_deleted"])]

    if row.empty:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = row.iloc[0]

    if not bcrypt.checkpw(request.password.encode("utf-8"), user["hashed_password"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if is_password_expired(user):
        raise HTTPException(status_code=403, detail="Password expired, please reset your password")

    if user["is_suspended"]:
        raise HTTPException(status_code=403, detail="Account is suspended")

    access_token = create_access_token({"sub": str(user.user_id)})
    refresh_token = create_refresh_token(str(user.user_id))

    log_action(user["user_id"], "login", "users", str(user["user_id"]))
    return {
        "message": "Login successful",
        "user_id": user["user_id"],
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.get("/me")
def get_current_user_info(user=Depends(get_current_user)):
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "user_name": user["user_name"],
        "is_active": user.get("is_active", True),
    }


@router.put("/{user_id}")
def update_user(user_id: UUID, update: UserUpdateRequest, user=Depends(get_current_user)):
    if str(user["user_id"]) != str(user_id) and not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="You can only update your own profile")

    users_df = load_versions("users", User, record_id=user_id)

    normalized_email = normalize_email(update.email) if update.email else None
    if normalized_email and normalized_email in users_df["email"].values:
        raise HTTPException(status_code=400, detail="Email already registered")

    old = users_df.iloc[-1].to_dict()
    salt = bcrypt.gensalt()

    mark_old_version_as_stale("users", user_id, "user_id")

    updated_user = User(
        user_id=user_id,
        user_name=update.user_name or old["user_name"],
        email=normalized_email or old["email"],
        hashed_password=bcrypt.hashpw(update.password.encode("utf-8"), salt)
        if update.password
        else old["hashed_password"],
        created_at=old["created_at"],
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
        is_active=True,
    )

    save_version(updated_user, "users", "user_id")
    log_action(user["user_id"], "update", "users", str(user_id), update.model_dump())
    return {"message": "User updated successfully", "user_id": str(user_id)}


@router.delete("/{user_id}")
def soft_delete_user(user_id: UUID, user=Depends(get_current_user)):
    # Only allow deleting your own account (or admins if you add auth)
    if str(user["user_id"]) != str(user_id) and not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="You can only update your own profile")

    return soft_delete_record("users", user_id, "user_id", User, user=user, owner_field="user_id", require_owner=True)


@router.post("/refresh")
def refresh_tokens(refresh_token: str):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        token_id = payload.get("jti")

        if not user_id or not token_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Verify token in S3
        df = load_versions("refresh_tokens", schema=RefreshToken, record_id=token_id)
        token_row = df[(df["is_current"])]

        if token_row.empty:
            raise HTTPException(status_code=401, detail="Token expired or already used")

        # Mark old refresh token as stale (rotation)
        mark_old_version_as_stale("refresh_tokens", token_id, "refresh_token_id")

        # Issue new tokens
        access_token = create_access_token({"sub": user_id})
        new_refresh_token = create_refresh_token(user_id)

        return {"access_token": access_token, "refresh_token": new_refresh_token, "token_type": "bearer"}

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/request-password-reset")
def request_password_reset(email: str):
    users_df = load_versions("users", User)

    normalized_email = normalize_email(email)

    match = users_df[
        (users_df["email"] == normalized_email) & (users_df["is_current"]) & (~users_df["is_deleted"].fillna(False))
    ]
    if match.empty:
        raise HTTPException(status_code=404, detail="User not found")

    user_id = match.iloc[0]["user_id"]

    # Generate OTP
    otp = f"{secrets.randbelow(1000000):06}"  # 6-digit numeric
    salt = bcrypt.gensalt()
    hashed_otp = bcrypt.hashpw(otp.encode("utf-8"), salt).decode("utf-8")

    reset_token = PasswordResetToken(
        token_id=uuid4(),
        user_id=user_id,
        otp_code=hashed_otp,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_EXPIRY_HOURS),
        used=False,
        created_at=datetime.now(timezone.utc),
    )
    save_version(reset_token, "password_reset_tokens", "token_id")
    log_action(
        None,
        "request_password_reset",
        "users",
        str(match.user_id),
        {"email": normalized_email, "otp_issued": True},  # Don’t log raw OTP
    )

    return {"message": "Password reset token generated", "otp": otp, "expires_in_minutes": 15}
    # Hybrid: return token in dev/test, send email in prod
    # if os.getenv("ENV", "dev") == "dev":
    #     return {
    #         "message": "Password reset token generated",
    #         "otp": otp,
    #         "expires_in_minutes": 15
    #     }
    # else:
    #     # TODO: replace with SES email later
    #     send_email(email, subject="Password Reset", body=f"Your OTP is {otp}")
    #     return {"message": "Password reset email sent"}


@router.post("/change-password")
def change_password(current_password: str, new_password: str, user=Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    users_df = load_versions("users", User)
    row = users_df[(users_df["user_id"] == str(user["user_id"])) & (users_df["is_current"])]

    user = row.iloc[0]

    if row.empty or not bcrypt.checkpw(current_password.encode("utf-8"), user["hashed_password"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    history = load_versions("password_history", PasswordHistory)
    user_history = history[history["user_id"] == str(user["user_id"])].sort_values("changed_at", ascending=False)
    recent_passwords = user_history.head(MIN_NUMBER_OF_PREVIOUS_PASSWORDS)["hashed_password"].tolist()

    if any(bcrypt.checkpw(new_password.encode("utf-8"), p.encode("utf-8")) for p in recent_passwords):
        raise HTTPException(
            status_code=400, detail=f"Cannot reuse the last {MIN_NUMBER_OF_PREVIOUS_PASSWORDS} passwords"
        )

    validate_password_strength(new_password)

    mark_old_version_as_stale("users", user["user_id"], "user_id")
    salt = bcrypt.gensalt()
    # Create new version with new password
    updated_user = User(
        user_id=user["user_id"],
        user_name=user["user_name"],
        email=user["email"],
        hashed_password=bcrypt.hashpw(new_password.encode("utf-8"), salt),
        created_at=user["created_at"],
        updated_at=now,
        password_changed_at=now,
        is_current=True,
        is_deleted=False,
    )

    password_history = PasswordHistory(
        history_id=uuid4(),
        user_id=user["user_id"],
        hashed_password=user["hashed_password"],  # the *old* hash
        changed_at=now,
    )

    save_version(updated_user, "users", "user_id")
    log_action(user["user_id"], "change_password", "users", str(user["user_id"]))

    save_version(password_history, "password_history", "history_id")
    on_password_change(UUID(user["user_id"]))

    return {"message": "Password changed successfully. Please log in again."}


@router.post("/reset-password")
def reset_password(email: str, otp_code: str, new_password: str):
    users_df = load_versions("users", User)

    normalized_email = normalize_email(email)

    match = users_df[
        (users_df["email"] == normalized_email) & (users_df["is_current"]) & (~users_df["is_deleted"].fillna(False))
    ]
    if match.empty:
        raise HTTPException(status_code=404, detail="User not found")

    user_id = match.iloc[0]["user_id"]

    tokens_df = load_versions("password_reset_tokens", PasswordResetToken)
    token_row = (
        tokens_df[
            (tokens_df["user_id"] == str(user_id))
            & (tokens_df["is_current"])
            & (~tokens_df.get("is_deleted", False).fillna(False))
            & (~tokens_df["used"].fillna(False))
        ]
        .sort_values("created_at", ascending=False)
        .head(1)
    )

    if token_row.empty:
        raise HTTPException(status_code=400, detail="No valid reset token found")

    token = token_row.iloc[0]

    if datetime.now(timezone.utc) > pd.to_datetime(token["expires_at"]):
        raise HTTPException(status_code=400, detail="Reset token expired")

    if not bcrypt.checkpw(otp_code.encode("utf-8"), token["otp_code"].encode("utf-8")):
        raise HTTPException(status_code=400, detail="Invalid OTP code")

    # Enforce password strength + history
    validate_password_strength(new_password)
    history = load_versions("password_history", PasswordHistory)
    user_history = history[history["user_id"] == str(user_id)].sort_values("changed_at", ascending=False)
    recent_passwords = user_history.head(MIN_NUMBER_OF_PREVIOUS_PASSWORDS)["hashed_password"].tolist()
    if any(bcrypt.checkpw(new_password.encode("utf-8"), p.encode("utf-8")) for p in recent_passwords):
        raise HTTPException(
            status_code=400, detail=f"Cannot reuse the last {MIN_NUMBER_OF_PREVIOUS_PASSWORDS} passwords"
        )

    # Update password
    mark_old_version_as_stale("users", user_id, "user_id")
    salt = bcrypt.gensalt()
    updated_user = User(
        **{k: match.iloc[0][k] for k in User.model_fields if k in match.iloc[0]},
        hashed_password=bcrypt.hashpw(new_password.encode("utf-8"), salt),
        updated_at=datetime.now(timezone.utc),
        password_changed_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
    )
    save_version(updated_user, "users", "user_id")

    # Store password history
    password_history = PasswordHistory(
        history_id=uuid4(),
        user_id=user_id,
        hashed_password=updated_user.hashed_password,
        changed_at=datetime.now(timezone.utc),
    )
    save_version(password_history, "password_history", "history_id")
    log_action(
        None,
        "reset_password",
        "users",
        str(match.user_id),
        {"otp_validated": True, "method": "otp"},  # instead of logging the OTP
    )

    # Mark token used
    mark_old_version_as_stale("password_reset_tokens", token["token_id"], "token_id")
    used_token = PasswordResetToken(**{**token.to_dict(), "used": True, "is_current": True})
    save_version(used_token, "password_reset_tokens", "token_id")

    log_action(user_id, "reset_password", "users", str(user_id))

    return {"message": "Password reset successful"}


@router.get("/{user_id}")
def get_user(user_id: UUID, user=Depends(get_current_user)):
    df = load_versions("users", User, record_id=user_id)

    match = df[(df["is_current"]) & (~df.get("is_deleted", False).fillna(False))]

    if match.empty:
        raise HTTPException(status_code=404, detail="User not found")
    log_action(user["user_id"], "get", "user", str(user_id))
    return match.iloc[0].to_dict()


@router.post("/{user_id}/suspend")
def suspend_user(user_id: UUID, reason: str, admin=Depends(get_current_user)):
    if not admin.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Not authorized to suspend users")
    users = load_versions("users", User, record_id=user_id)
    match = users[(users["is_current"]) & (~users["is_deleted"])]

    if match.empty:
        raise HTTPException(status_code=404, detail="User not found")

    row = match.iloc[0].to_dict()
    mark_old_version_as_stale("users", user_id, "user_id")

    updated = User(
        **row,
        user_id=user_id,
        updated_at=datetime.now(timezone.utc),
        is_suspended=True,
        suspended_at=datetime.now(timezone.utc),
        suspension_reason=reason,
        is_active=False,
        is_current=True,
    )

    save_version(updated, "users", "user_id")
    on_user_suspended(user_id, reason, admin["user_id"])
    log_action(admin["user_id"], "suspend", "users", str(user_id), {"reason": reason})
    return {"message": "User suspended", "user_id": str(user_id)}


@router.post("/{user_id}/unsuspend")
def unsuspend_user(user_id: UUID, admin=Depends(get_current_user)):
    users = load_versions("users", User, record_id=user_id)
    match = users[(users["is_current"]) & (~users["is_deleted"])]

    if match.empty:
        raise HTTPException(status_code=404, detail="User not found")

    row = match.iloc[0].to_dict()
    mark_old_version_as_stale("users", user_id, "user_id")

    updated = User(
        **row,
        user_id=user_id,
        updated_at=datetime.now(timezone.utc),
        is_suspended=False,
        suspended_at=None,
        suspension_reason=None,
        is_active=True,
        is_current=True,
    )

    save_version(updated, "users", "user_id")
    on_user_unsuspended(user_id, admin["user_id"])

    return {"message": "User unsuspended", "user_id": str(user_id)}
