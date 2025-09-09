from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import date
import pytest
import app.main as app

client = TestClient(app.app)

def test_summary_flow():
    # --- Register + login ---
    register_payload = {"email": f"summary-{uuid4().hex[:6]}@example.com", "user_name": "summaryuser", "password": "Summary123!"}
    r = client.post("/users/register", json=register_payload)
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    login_payload = {"email": register_payload["email"], "password": register_payload["password"]}
    r = client.post("/users/login", json=login_payload)
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # --- Create household + account ---
    household_payload = {"name": "Summary Household"}
    r = client.post("/households/", json=household_payload, headers=headers)
    household_id = r.json()["household_id"]

    account_payload = {"name": "Summary Account", "household_id": household_id, "user_id": user_id}
    r = client.post("/accounts/", json=account_payload, headers=headers)
    account_id = r.json()["account_id"]

    # --- Create entries ---
    entry_payload = {
        "user_id": user_id,
        "account_name": "Summary Account",
        "household_name": "Summary Household",
        "entry_date": str(date.today()),
        "value_date": str(date.today()),
        "type": "expense",
        "category": "groceries",
        "amount": 50.0,
        "description": "Weekly groceries"
    }
    r = client.post("/entries/", json=entry_payload, headers=headers)
    assert r.status_code == 200

    # --- Fetch monthly summary ---
    month = date.today().strftime("%Y-%m")
    r = client.get(f"/summary?month={month}", headers=headers)
    assert r.status_code == 200
    result = r.json()
    assert result["total"] == 50.0
    assert "groceries" in result["by_category"]

    # --- Fetch trend summary (last 1 month) ---
    r = client.get("/summary?last_n_months=1", headers=headers)
    assert r.status_code == 200
    result = r.json()
    assert result["trends"] is not None
