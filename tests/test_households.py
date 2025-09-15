from uuid import uuid4

def test_user_can_create_one_household(client, auth_headers):
    # Create household
    payload = {"name": "My Household"}
    r = client.post("/households/", json=payload, headers=auth_headers)
    assert r.status_code == 200
    hh_id = r.json()["household_id"]

    # Verify membership role = admin
    r = client.get("/households/memberships", headers=auth_headers)
    memberships = r.json()
    assert any(m["household_id"] == hh_id and m["role"] == "admin" for m in memberships)

    # Attempt second household creation → should fail
    r = client.post("/households/", json={"name": "Second Household"}, headers=auth_headers)
    assert r.status_code == 400
    assert "already created a household" in r.json()["detail"]

def test_admin_can_invite_and_remove_members(client, auth_headers, another_user_id):
    # Create household
    r = client.post("/households/", json={"name": "Invite HH"}, headers=auth_headers)
    hh_id = r.json()["household_id"]

    # Invite user as member
    r = client.post(f"/households/{hh_id}/members", 
                    params={"target_user_id": another_user_id, "role": "member"},
                    headers=auth_headers)
    assert r.status_code == 200

    # Verify membership
    r = client.get("/households/memberships", headers=auth_headers)
    memberships = r.json()
    assert any(m["user_id"] == str(another_user_id) and m["role"] == "member" for m in memberships)

    # Remove member
    r = client.delete(f"/households/{hh_id}/members/{another_user_id}", headers=auth_headers)
    assert r.status_code == 200
