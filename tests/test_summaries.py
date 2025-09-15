from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import date
import pytest
import app.main as app

client = TestClient(app.app)

def test_summary_flow(client: TestClient):
    # --- Register + login ---
    register_payload = {
        "email": f"summary-{uuid4().hex[:6]}@example.com",
        "user_name": "summaryuser",
        "password": "Summary123!",
    }
    r = client.post("/users/register", json=register_payload)
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    login_payload = {"email": register_payload["email"], "password": register_payload["password"]}
    r = client.post("/users/login", json=login_payload)
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # --- Create household (user automatically admin) ---
    household_payload = {"name": "Summary Household"}
    r = client.post("/households/", json=household_payload, headers=headers)
    assert r.status_code == 200
    household_id = r.json()["household_id"]

    # --- Create account (as admin) ---
    account_payload = {"name": "Summary Account", "household_id": household_id}
    r = client.post("/accounts/", json=account_payload, headers=headers)
    assert r.status_code == 200
    account_id = r.json()["account_id"]

    # --- Assign user to account (so they can create entries) ---
    r = client.post(f"/accounts/{account_id}/assign-user",
                    params={"target_user_id": user_id},
                    headers=headers)
    assert r.status_code == 200

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
        "description": "Weekly groceries",
    }
    r = client.post("/entries/", json=entry_payload, headers=headers)
    assert r.status_code == 200


def test_summary_trends(client: TestClient):
    # --- Register + login ---
    register_payload = {
        "email": f"trend-{uuid4().hex[:6]}@example.com",
        "user_name": "trenduser",
        "password": "Trend123!"
    }
    r = client.post("/users/register", json=register_payload)
    user_id = r.json()["user_id"]

    r = client.post("/users/login", json={"email": register_payload["email"], "password": register_payload["password"]})
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # --- Household + account ---
    r = client.post("/households/", json={"name": "Trend Household"}, headers=headers)
    household_id = r.json()["household_id"]

    r = client.post("/accounts/", json={"name": "Trend Account", "household_id": household_id}, headers=headers)
    account_id = r.json()["account_id"]

    # --- Assign user to account ---
    r = client.post(f"/accounts/{account_id}/assign-user",
                    params={"target_user_id": user_id},
                    headers=headers)
    assert r.status_code == 200

    # --- Two entries in different categories + months ---
    entry1 = {
        "user_id": user_id,
        "account_name": "Trend Account",
        "household_name": "Trend Household",
        "entry_date": "2025-07-01",
        "value_date": "2025-07-01",
        "type": "expense",
        "category": "groceries",
        "amount": 100,
        "description": "July groceries"
    }
    client.post("/entries/", json=entry1, headers=headers)

    entry2 = {
        "user_id": user_id,
        "account_name": "Trend Account",
        "household_name": "Trend Household",
        "entry_date": "2025-08-01",
        "value_date": "2025-08-01",
        "type": "income",
        "category": "salary",
        "amount": 1000,
        "description": "August salary"
    }
    client.post("/entries/", json=entry2, headers=headers)

    # --- Get last 3 months summary ---
    r = client.get("/summaries/summary?last_n_months=3", headers=headers)
    result = r.json()

    assert "type_trends" in result
    assert "category_trends" in result
    assert any(trend["type"] == "expense" for trend in result["type_trends"])
    assert any(trend["type"] == "income" for trend in result["type_trends"])

