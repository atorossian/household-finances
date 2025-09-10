import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import date

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
