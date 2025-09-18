import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import date
import io
import pandas as pd


def test_entries_full_lifecycle(client: TestClient):
    # --- Register + login user ---
    register_payload = {
        "email": f"entriesuser-{uuid4().hex[:6]}@example.com",
        "user_name": "entriesuser",
        "password": "EntryTest1234!",
    }
    r = client.post("/users/register", json=register_payload)
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    r = client.post("/users/login", json=register_payload)
    assert r.status_code == 200
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # --- Create household (only one per user) ---
    household_payload = {"name": "My Household"}
    r = client.post("/households/", json=household_payload, headers=headers)
    assert r.status_code == 200
    household_id = r.json()["household_id"]

    # --- Create account in household (allowed: admin only) ---
    account_payload = {"name": "Main Account", "household_id": household_id}
    r = client.post("/accounts/", json=account_payload, headers=headers)
    assert r.status_code == 200
    account_id = r.json()["account_id"]
    client.post(f"/accounts/{account_id}/assign-user", params={"target_user_id": user_id}, headers=headers)

    # --- Assign user to account ---
    r = client.post(f"/accounts/{account_id}/assign-user",
                    params={"target_user_id": user_id},
                    headers=headers)
    assert r.status_code == 200

    # --- Create entry ---
    entry_payload = {
        "user_id": user_id,
        "account_name": "Main Account",
        "household_name": "My Household",
        "entry_date": str(date.today()),
        "value_date": str(date.today()),
        "type": "expense",
        "category": "groceries",
        "amount": 42.5,
        "description": "Weekly groceries",
    }
    r = client.post("/entries/", json=entry_payload, headers=headers)
    assert r.status_code == 200
    entry_id = r.json()["entry_id"]

    # --- List entries ---
    r = client.get("/entries/", headers=headers)
    entries = r.json()
    assert any(e["entry_id"] == entry_id for e in entries)

    # --- Update entry ---
    updated_payload = {**entry_payload, "amount": 55.0, "description": "Groceries updated"}
    r = client.put(f"/entries/{entry_id}", json=updated_payload, headers=headers)
    assert r.status_code == 200

    # --- Entry history should include 2 versions ---
    r = client.get(f"/entries/{entry_id}/history", headers=headers)
    history = r.json()
    assert len(history) == 2
    assert history[0]["description"] == "Groceries updated"

    # --- Delete entry ---
    r = client.delete(f"/entries/{entry_id}", headers=headers)
    assert r.status_code == 200

    # Verify deleted entry not listed
    r = client.get("/entries/", headers=headers)
    assert all(e["entry_id"] != entry_id for e in r.json())

def _bootstrap_user_household_account(client):
    # Register & login
    email = f"import-{uuid4().hex[:6]}@example.com"
    password = "Imp0rtTest!"
    client.post("/users/register", json={"email": email, "user_name": "importer", "password": password})
    r = client.post("/users/login", json={"email": email, "password": password})
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    
    # sanity check
    me = client.get("/users/me", headers=headers)
    assert me.status_code == 200
    user_id = me.json()["user_id"]
    print(me.json())

    # Household
    r = client.post("/households/", json={"name": "Import HH"}, headers=headers)
    assert r.status_code == 200
    household_id = r.json()["household_id"]

    # Account
    r = client.post("/accounts/", json={"name": "Import ACC", "household_id": household_id}, headers=headers)
    assert r.status_code == 200
    account_id = r.json()["account_id"]

    # Assign user to account
    client.post(f"/accounts/{account_id}/assign-user", params={"target_user_id": user_id}, headers=headers)

    return headers, household_id, account_id

def test_import_entries_csv(client):
    headers, household_id, account_id = _bootstrap_user_household_account(client)

    df = pd.DataFrame(
        [
            {
                "entry_date": str(date.today()),
                "value_date": str(date.today()),
                "type": "expense",
                "category": "groceries",
                "amount": 10.5,
                "description": "CSV row 1",
                "account_id": account_id,
                "household_id": household_id,
            },
            {
                "entry_date": str(date.today()),
                "value_date": str(date.today()),
                "type": "expense",
                "category": "groceries",
                "amount": 12.0,
                "description": "CSV row 2",
                "account_id": account_id,
                "household_id": household_id,
            },
        ]
    )
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    files = {"file": ("entries.csv", buf.getvalue().encode("utf-8"), "text/csv")}

    r = client.post("/entries/import", files=files, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0
    assert len(body["entry_ids"]) == 2

    # Verify they are present
    r = client.get("/entries/", headers=headers)
    entries = r.json()
    descs = {e["description"] for e in entries}
    assert "CSV row 1" in descs and "CSV row 2" in descs

def test_import_entries_xlsx(client):
    pytest.importorskip("openpyxl")  # ensure engine available

    headers, household_id, account_id = _bootstrap_user_household_account(client)

    df = pd.DataFrame(
        [
            {
                "entry_date": str(date.today()),
                "value_date": str(date.today()),
                "type": "expense",
                "category": "groceries",
                "amount": 20.0,
                "description": "XLSX row 1",
                "account_id": account_id,
                "household_id": household_id,
            }
        ]
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    buf.seek(0)

    files = {"file": ("entries.xlsx", buf.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = client.post("/entries/import", files=files, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 1
    assert body["skipped"] == 0

    # Verify present
    r = client.get("/entries/", headers=headers)
    entries = r.json()
    assert any(e["description"] == "XLSX row 1" for e in entries)