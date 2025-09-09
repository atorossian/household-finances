import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import date

# in tests/test_debts.py
def test_debt_creates_entries(client: TestClient):
    # --- Register + login user ---
    register_payload = {"email": f"debtuser-{uuid4().hex[:6]}@example.com", "user_name": "debtuser", "password": "DebtTest123!"}
    r = client.post("/users/register", json=register_payload)
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    login_payload = {"email": register_payload["email"], "password": register_payload["password"]}
    r = client.post("/users/login", json=login_payload)
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # --- Create household + account ---
    household_name = "Debt Household"
    account_name = "Debt Account"
    household_payload = {"name": household_name}
    r = client.post("/households/", json=household_payload, headers=headers)
    assert r.status_code == 200
    household_id = r.json()["household_id"]

    account_payload = {"name": account_name, "household_id": household_id, "user_id": user_id}
    r = client.post("/accounts/", json=account_payload, headers=headers)
    assert r.status_code == 200
    account_id = r.json()["account_id"]
    
    # --- Create debt ---
    debt_payload = {
        "user_id": user_id,
        "account_name": account_name,
        "household_name": household_name,
        "name": "Car Loan",
        "principal": 1000.0,
        "interest_rate": 0.0,
        "installments": 4,
        "start_date": str(date.today()),
        "due_day": date.today().day
    }

    r = client.post("/debts/", json=debt_payload, headers=headers)
    debt_id = r.json()["debt_id"]
    assert r.status_code == 200
    assert r.json()["installments"] == 4

    # --- Verify entries were created ---
    r = client.get("/entries/", headers=headers)
    entries = r.json()
    debt_entries = [e for e in entries if "Car Loan" in e["description"]]
    assert len(debt_entries) == 4
    assert all(e["category"] == "financing" for e in debt_entries)

    # Delete debt
    r = client.delete(f"/debts/{debt_id}", headers=headers)
    assert r.status_code == 200

    # Verify debt is gone
    r = client.get("/debts/", headers=headers)
    debts = r.json()
    assert all(d["debt_id"] != debt_id for d in debts)

    # Verify related entries are also hidden
    r = client.get("/entries/", headers=headers)
    print(r.json())
    entries = r.json()
    assert all("Car Loan" in e["description"] for e in entries)
