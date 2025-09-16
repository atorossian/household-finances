# tests/test_accounts.py
import pytest
from fastapi.testclient import TestClient


def test_only_admin_can_create_account(client: TestClient, auth_headers, another_user):
    another_user_id, another_headers = another_user

    # Create household as user1 (admin)
    r = client.post("/households/", json={"name": "Account HH"}, headers=auth_headers)
    assert r.status_code == 200
    hh_id = r.json()["household_id"]

    # Try account create as another user (not invited yet) → should fail
    payload = {"name": "Acc1", "household_id": hh_id}
    r = client.post("/accounts/", json=payload, headers=another_headers)
    assert r.status_code == 403

    # Add another_user as member
    r = client.post(
        f"/households/{hh_id}/members",
        params={"target_user_id": another_user_id, "role": "member"},
        headers=auth_headers,
    )
    assert r.status_code == 200

    # Try account create as member (not admin) → should fail
    r = client.post("/accounts/", json=payload, headers=another_headers)
    assert r.status_code == 403

    # Create account as admin (user1)
    r = client.post("/accounts/", json=payload, headers=auth_headers)
    assert r.status_code == 200
    acc_id = r.json()["account_id"]

    # Assign user to account (user must belong to household)
    r = client.post(
        f"/accounts/{acc_id}/assign-user",
        params={"target_user_id": another_user_id},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["user_id"] == str(another_user_id)


def test_account_can_be_reassigned_but_only_one_user(client: TestClient, auth_headers, another_user, third_user):
    another_user_id, another_headers = another_user
    third_user_id, third_headers = third_user

    # Create household
    r = client.post("/households/", json={"name": "Reassign HH"}, headers=auth_headers)
    assert r.status_code == 200
    hh_id = r.json()["household_id"]

    # Invite both users
    r = client.post(
        f"/households/{hh_id}/members",
        params={"target_user_id": another_user_id, "role": "member"},
        headers=auth_headers,
    )
    assert r.status_code == 200

    r = client.post(
        f"/households/{hh_id}/members",
        params={"target_user_id": third_user_id, "role": "member"},
        headers=auth_headers,
    )
    assert r.status_code == 200

    # Create account
    r = client.post("/accounts/", json={"name": "AccR", "household_id": hh_id}, headers=auth_headers)
    assert r.status_code == 200
    acc_id = r.json()["account_id"]

    # Assign to user2 (another_user)
    r = client.post(
        f"/accounts/{acc_id}/assign-user",
        params={"target_user_id": another_user_id},
        headers=auth_headers,
    )
    assert r.status_code == 200

    # Reassign to user3 (third_user), should overwrite
    r = client.post(
        f"/accounts/{acc_id}/assign-user",
        params={"target_user_id": third_user_id},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["user_id"] == str(third_user_id)
