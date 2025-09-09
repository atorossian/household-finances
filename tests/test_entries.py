import pytest
from fastapi.testclient import TestClient
from uuid import uuid4, UUID
from datetime import date



def test_entries_full_lifecycle(client: TestClient):
    # --- Register + login user ---
    register_payload = {
        "email": f"entriesuser-{uuid4().hex[:6]}@example.com",
        'user_name': "entriesuser",
        "password": "EntryTest1234!"
        }
    r = client.post("/users/register", json=register_payload)
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    r = client.post("/users/login", json=register_payload)
    assert r.status_code == 200
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # --- Create account & household ---
    household_name = "My Household"
    account_name = "Main Account"
    household_payload = {"name": household_name}
    r = client.post("/households/", json=household_payload, headers=headers)
    assert r.status_code == 200
    household_id = r.json()["household_id"]

    account_payload = {"name": account_name, "household_id": household_id, "user_id": user_id}
    r = client.post("/accounts/", json=account_payload, headers=headers)
    assert r.status_code == 200
    account_id = r.json()["account_id"]

    # --- Create entry ---
    entry_payload = {
        "user_id": UUID(user_id),
        "account_name": account_name,
        "household_name": household_name,
        "entry_date": str(date.today()),
        "value_date": str(date.today()),
        "type": "expense",
        "category": "groceries",
        "amount": 42.5,
        "description": "Weekly groceries"
    }
    r = client.post("/entries/", json=entry_payload, headers=headers)
    assert r.status_code == 200
    entry_id = r.json()["entry_id"]

    # --- List current entries (should include new one) ---
    r = client.get("/entries/", headers=headers)
    assert r.status_code == 200
    entries = r.json()
    assert any(e["entry_id"] == entry_id for e in entries)

    # --- Update entry ---
    updated_payload = {
        **entry_payload,
        "amount": 55.0,
        "description": "Groceries updated"
    }
    r = client.put(f"/entries/{entry_id}", json=updated_payload, headers=headers)
    assert r.status_code == 200

    # --- Get entry history (should have 2 versions) ---
    r = client.get(f"/entries/{entry_id}", headers=headers)
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 2
    assert history[0]["description"] == "Groceries updated"

    # --- Soft delete entry ---
    r = client.post(f"/entries/{entry_id}/delete", headers=headers)
    assert r.status_code == 200

    # --- List entries again (deleted one should not appear) ---
    r = client.get("/entries/", headers=headers)
    assert r.status_code == 200
    entries_after = r.json()
    assert all(e["entry_id"] != entry_id for e in entries_after)

