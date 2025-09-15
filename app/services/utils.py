from fastapi import APIRouter, HTTPException, Depends
from app.services.auth import get_current_user
import re
from datetime import datetime,timezone
import pandas as pd
import os
import boto3
from botocore.exceptions import ClientError


# Utility functions for user management, password handling, and email sending
PASSWORD_EXPIRY_DAYS = 90
PASSWORD_MIN_LENGTH = 8


def validate_password_strength(password: str):
    """Validate that a password meets security requirements."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one special character")
    
def is_password_expired(user_row):
    if not user_row.get("password_changed_at"):
        return False
    last_change = pd.to_datetime(user_row["password_changed_at"])
    return (datetime.now(timezone.utc) - last_change).days >= PASSWORD_EXPIRY_DAYS

def normalize_email(email: str) -> str:
    return email.strip().lower()

# AWS SES setup
SES_REGION = os.getenv("SES_REGION", "us-east-1")
FROM_EMAIL = os.getenv("FROM_EMAIL", "no-reply@yourdomain.com")

ses_client = boto3.client("ses", region_name=SES_REGION)

def send_email(recipient: str, subject: str, body: str) -> bool:
    try:
        ses_client.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": subject},
                "Body": {
                    "Text": {"Data": body},
                    "Html": {"Data": f"<p>{body}</p>"},
                },
            },
        )
        return True
    except ClientError as e:
        print(f"SES send_email error: {e}")
        return False


from fastapi import Depends, HTTPException

def require_role(allowed_roles: list[str], user=Depends(get_current_user), resource=None):
    if user.get("is_superuser"):
        return user  # bypass all checks
    
    role = resource.get("role")  # fetched from membership
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient role permissions")
    
    return user
