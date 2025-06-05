from fastapi import Header, HTTPException, Depends
from app.services.storage import load_versions
import pandas as pd

def get_current_user(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="Invalid auth header")

    token = authorization.replace("Bearer ", "").strip()
    users = load_versions("users")
    user = users[
        (users["token"] == token) & 
        (users["is_current"]) & 
        (~users["is_deleted"])
    ]

    if user.empty:
        raise HTTPException(status_code=403, detail="Invalid or expired token")

    return user.iloc[0].to_dict()
