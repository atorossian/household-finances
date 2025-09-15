import pytest
from uuid import uuid4
from fastapi.testclient import TestClient


def test_register_login_update_change_password(client: TestClient):
    # --- Register user ---
    register_payload = {
        "email": f"testuser-{uuid4().hex[:6]}@example.com",
        "user_name": "testuser",
        "password": "UserTest1234!",
    }
    response = client.post("/users/register", json=register_payload)
    assert response.status_code == 200
    body = response.json()
    user_id = body["user_id"]
    assert body["message"] == "User registered successfully"

    # --- Login with same user ---
    login_payload = {
        "email": register_payload["email"],
        "password": register_payload["password"],
    }
    response = client.post("/users/login", json=login_payload)
    assert response.status_code == 200
    body = response.json()
    access_token = body["access_token"]
    refresh_token = body["refresh_token"]
    assert body["token_type"] == "bearer"

    headers = {"Authorization": f"Bearer {access_token}"}

    # --- Create household (allowed: one per user) ---
    household_payload = {"name": "Test Household"}
    r = client.post("/households/", json=household_payload, headers=headers)
    assert r.status_code == 200
    household_id = r.json()["household_id"]

    # Try to create a second household (should fail)
    r = client.post("/households/", json={"name": "Second Household"}, headers=headers)
    assert r.status_code == 400

    # --- Create account (allowed: admin of household) ---
    account_payload = {"name": "Test Account", "household_id": household_id}
    r = client.post("/accounts/", json=account_payload, headers=headers)
    assert r.status_code == 200
    account_id = r.json()["account_id"]

    # --- Update user info ---
    update_payload = {"email": "newemail@example.com"}
    response = client.put(f"/users/{user_id}", json=update_payload, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "User updated successfully"

    # --- Change password ---
    change_pw_payload = {
        "current_password": register_payload["password"],
        "new_password": "NewPassw0rd!",
    }
    response = client.post(
        "/users/change-password", params=change_pw_payload, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"].startswith("Password changed successfully")

    # --- Login with new password ---
    new_login_payload = {"email": "newemail@example.com", "password": "NewPassw0rd!"}
    response = client.post("/users/login", json=new_login_payload)
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body

    # Delete user
    r = client.delete(f"/users/{user_id}", headers=headers)
    assert r.status_code == 200

    # Verify user cannot be retrieved
    r = client.get(f"/users/{user_id}", headers=headers)
    assert r.status_code == 404

    # Verify deleted user has no memberships left
    r = client.get("/accounts/memberships", headers=headers)
    assert all(m["user_id"] != user_id for m in r.json())

    r = client.get("/households/memberships", headers=headers)
    assert all(m["user_id"] != user_id for m in r.json())
