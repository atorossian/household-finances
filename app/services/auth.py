import jwt
from fastapi import Header, HTTPException, Depends
import pandas as pd
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app.services.storage import save_version, load_versions
from fastapi.security import OAuth2PasswordBearer
from app.config import config

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")
SECRET_KEY = config.get("auth", {}).get("secret_key")
ALGORITHM = config.get("auth", {}).get("algorithm", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = config.get("auth", {}).get("access_token_expire_minutes", 15)
REFRESH_TOKEN_EXPIRE_DAYS = config.get("auth", {}).get("refresh_token_expire_days", 7)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: str):
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    token_id = str(uuid4())  # unique ID for rotation
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
        "refresh_token_id"
    )
    return token

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"user_id": user_id}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
