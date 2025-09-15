def test_only_admin_can_create_account(client, auth_headers, another_auth_headers, another_user_id):
    # Create household as user1 (admin)
    r = client.post("/households/", json={"name": "Account HH"}, headers=auth_headers)
    hh_id = r.json()["household_id"]

    # Try account create as another user (not invited yet)
    payload = {"name": "Acc1", "household_id": hh_id}
    r = client.post("/accounts/", json=payload, headers=another_auth_headers)
    assert r.status_code == 403

    # Add another_user as member
    client.post(f"/households/{hh_id}/members", 
                params={"target_user_id": another_user_id, "role": "member"},
                headers=auth_headers)

    # Try account create as member (not admin)
    r = client.post("/accounts/", json=payload, headers=another_auth_headers)
    assert r.status_code == 403

    # Create account as admin
    r = client.post("/accounts/", json=payload, headers=auth_headers)
    assert r.status_code == 200
    acc_id = r.json()["account_id"]

    # Assign user to account (user must belong to household)
    r = client.post(f"/accounts/{acc_id}/assign-user", 
                    params={"target_user_id": another_user_id}, 
                    headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["user_id"] == str(another_user_id)

def test_account_can_be_reassigned_but_only_one_user(client, auth_headers, another_user_id, third_user_id):
    # Create household
    r = client.post("/households/", json={"name": "Reassign HH"}, headers=auth_headers)
    hh_id = r.json()["household_id"]

    # Invite both users
    client.post(f"/households/{hh_id}/members", 
                params={"target_user_id": another_user_id, "role": "member"},
                headers=auth_headers)
    client.post(f"/households/{hh_id}/members", 
                params={"target_user_id": third_user_id, "role": "member"},
                headers=auth_headers)

    # Create account
    r = client.post("/accounts/", json={"name": "AccR", "household_id": hh_id}, headers=auth_headers)
    acc_id = r.json()["account_id"]

    # Assign user1
    r = client.post(f"/accounts/{acc_id}/assign-user", 
                    params={"target_user_id": another_user_id}, headers=auth_headers)
    assert r.status_code == 200

    # Reassign to user2 (overwrites)
    r = client.post(f"/accounts/{acc_id}/assign-user", 
                    params={"target_user_id": third_user_id}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["user_id"] == str(third_user_id)
