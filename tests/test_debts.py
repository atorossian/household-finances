import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import date


def test_debt_creates_entries(client: TestClient):
    # --- Register + login user ---
    register_payload = {
        "email": f"debtuser-{uuid4().hex[:6]}@example.com",
        "user_name": "debtuser",
        "password": "DebtTest123!",
    }
    r = client.post("/users/register", json=register_payload)
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    login_payload = {"email": register_payload["email"], "password": register_payload["password"]}
    r = client.post("/users/login", json=login_payload)
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # --- Create household (allowed: one per user) ---
    household_payload = {"name": "Debt Household"}
    r = client.post("/households/", json=household_payload, headers=headers)
    assert r.status_code == 200
    household_id = r.json()["household_id"]

    # --- Create account ---
    account_payload = {"name": "Debt Account", "household_id": household_id}
    r = client.post("/accounts/", json=account_payload, headers=headers)
    assert r.status_code == 200
    account_id = r.json()["account_id"]

    # --- Assign user to account ---
    r = client.post(f"/accounts/{account_id}/assign-user",
                    params={"target_user_id": user_id},
                    headers=headers)
    assert r.status_code == 200

    # --- Create debt ---
    debt_payload = {
        "user_id": user_id,
        "account_name": "Debt Account",
        "household_name": "Debt Household",
        "name": "Car Loan",
        "principal": 1000.0,
        "interest_rate": 0.0,
        "installments": 4,
        "start_date": str(date.today()),
        "due_day": date.today().day,
    }
    r = client.post("/debts/", json=debt_payload, headers=headers)
    assert r.status_code == 200
    debt_id = r.json()["debt_id"]
    assert r.json()["installments"] == 4

    # --- Verify audit log ---
    r = client.get("/audit/logs", params={"resource_type": "debts", "user_id": user_id}, headers=headers)
    logs = r.json()
    assert any(log["resource_type"] == "debts" for log in logs)
    assert any("Car Loan" in log["details"] for log in logs)

    # --- Verify debt entries created ---
    r = client.get("/entries/", headers=headers)
    debt_entries = [e for e in r.json() if "Car Loan" in e["description"]]
    assert len(debt_entries) == 4
    assert all(e["category"] == "financing" for e in debt_entries)

    # --- Delete debt ---
    r = client.delete(f"/debts/{debt_id}", headers=headers)
    assert r.status_code == 200

    # Verify debt removed
    r = client.get("/debts/", headers=headers)
    assert all(d["debt_id"] != debt_id for d in r.json())

    # Verify related entries removed
    r = client.get("/entries/", headers=headers)
    assert all("Car Loan" not in e["description"] for e in r.json())
