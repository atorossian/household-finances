import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
import pandas as pd
from datetime import date, datetime, timezone

def test_audit_logs(client: TestClient):
    # Register user
    payload = {"email": f"audit-{uuid4().hex[:6]}@example.com", "user_name": "audituser", "password": "Audit123!"}
    r = client.post("/users/register", json=payload)
    user_id = r.json()["user_id"]

    # Login
    r = client.post("/users/login", json={"email": payload["email"], "password": payload["password"]})
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Create household
    r = client.post("/households/", json={"name": "Audit Household"}, headers=headers)
    household_id = r.json()["household_id"]

    # Query audit logs
    r = client.get("/audit/logs", headers=headers)
    logs = r.json()
    assert any(l["action"] == "register" and l["resource_type"] == "users" for l in logs)
    assert any(l["action"] == "create" and l["resource_type"] == "households" for l in logs)



def test_audit_log_partitioning(client):
    # --- Register user (this generates an audit log) ---
    payload = {
        "email": f"partition-{uuid4().hex[:6]}@example.com",
        "user_name": "puser",
        "password": "Part123!"
    }
    r = client.post("/users/register", json=payload)
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    # --- Login to get access token ---
    login_payload = {"email": payload["email"], "password": payload["password"]}
    r = client.post("/users/login", json=login_payload)
    assert r.status_code == 200
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # --- Fetch logs using the API (authorized) ---
    r = client.get("/audit/logs", params={"user_id": user_id}, headers=headers)
    print("Audit logs returned:", logs)
    assert r.status_code == 200
    logs = r.json()
    assert len(logs) > 0

    # --- Validate today’s date is present ---
    now = datetime.now(timezone.utc).date()
    timestamps = [pd.to_datetime(log["timestamp"]).date() for log in logs]
    assert any(ts == now for ts in timestamps)

    # --- Extra: confirm action + resource_type ---
    assert any(log["action"] == "register" and log["resource_type"] == "users" for log in logs)
