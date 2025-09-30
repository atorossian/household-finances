import jwt
from fastapi import HTTPException, Depends
from datetime import datetime, timedelta, timezone
from uuid import uuid4, UUID
from app.services.storage import save_version, load_versions
from app.models.schemas.user import User
from fastapi.security import OAuth2PasswordBearer
from app.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")
SECRET_KEY = settings.secret_key
ALGORITHM = settings.encoding_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str):
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    token_id = str(uuid4())
    payload = {"sub": str(user_id), "jti": token_id, "exp": expire}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    # Save refresh token metadata in S3
    save_version(
        {
            "refresh_token_id": token_id,
            "user_id": user_id,
            "expires_at": expire.isoformat(),
            "is_current": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "refresh_tokens",
        "refresh_token_id",
    )
    return token


def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: UUID = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    users_df = load_versions("users", User, record_id=user_id)
    match = users_df[(users_df["is_current"]) & (~users_df.get("is_deleted", False).fillna(False))]

    if match.empty:
        raise HTTPException(status_code=401, detail="User not found")

    user = match.iloc[0].to_dict()

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="User is inactive")
    if user.get("is_suspended", False):
        raise HTTPException(status_code=403, detail="User is suspended")

    return user
