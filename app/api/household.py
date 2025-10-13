from fastapi import APIRouter, HTTPException, Depends
from uuid import UUID, uuid4
from datetime import datetime, timezone
from app.models.schemas.household import Household, HouseholdCreate, HouseholdOut
from app.models.schemas.membership import UserHousehold, UserHouseholdOut
from app.services.storage import save_version, mark_old_version_as_stale, load_versions, soft_delete_record, log_action
from app.services.auth import get_current_user
from app.services.roles import require_household_role
from app.services.utils import page_params
from app.services.fetchers import fetch_record
from app.models.enums import Role

router = APIRouter()


@router.post("/")
def create_household(payload: HouseholdCreate, user=Depends(get_current_user)):
    # Enforce one household per creator
    hh = load_versions("households", Household)
    existing = hh[
        (hh.get("created_by_user_id") == str(user["user_id"]))
        & (hh["is_current"])
        & (~hh.get("is_deleted", False).fillna(False))
    ]
    if not existing.empty:
        raise HTTPException(status_code=400, detail="User already created a household")

    now = datetime.now(timezone.utc)
    household = Household(
        household_id=uuid4(),
        name=payload.name,
        created_by_user_id=user["user_id"],
        created_at=now,
        updated_at=now,
        is_current=True,
        is_deleted=False,
    )
    save_version(household, "households", "household_id")
    log_action(user["user_id"], "create", "households", str(household.household_id), payload.model_dump())

    # Automatically assign the creator as a member
    mapping = UserHousehold(
        mapping_id=uuid4(),
        user_id=user["user_id"],
        household_id=household.household_id,
        role=Role("admin"),
    )
    save_version(mapping, "user_households", "mapping_id")
    log_action(
        user["user_id"], "assign_user", "households", str(household.household_id), {"user_id": str(user["user_id"])}
    )

    return {"message": "Household created", "household_id": str(household.household_id)}


@router.post("/assign-user-to-household")
def assign_user_to_household(user_id: UUID, household_id: UUID, user=Depends(get_current_user)):
    require_household_role(user, household_id, required_role=Role("admin"))
    mapping = UserHousehold(user_id=user_id, household_id=household_id)
    save_version(mapping, "user_households", "mapping_id")
    log_action(user["user_id"], "assign_user", "households", str(household_id), {"user_id": str(user_id)})

    return {"message": "User assigned to household"}


@router.put("/{household_id}")
def update_household(household_id: UUID, name: str, user=Depends(get_current_user)):
    require_household_role(user, household_id, required_role=Role("admin"))
    mark_old_version_as_stale("households", household_id, "household_id")
    households = load_versions("households", Household)
    current = households[households["household_id"] == str(household_id)].iloc[-1].to_dict()

    updated = Household(
        household_id=household_id,
        name=name,
        created_at=current["created_at"],
        created_by_user_id=current["created_by_user_id"],
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False,
    )
    save_version(updated, "households", "household_id")
    log_action(user["user_id"], "update", "households", str(household_id), {"name": name})

    return {"message": "Household updated", "household_id": str(household_id)}


@router.delete("/{household_id}")
def delete_household(household_id: UUID, user=Depends(get_current_user)):
    require_household_role(user, household_id, required_role=Role("admin"))

    return soft_delete_record(
        "households", household_id, "household_id", Household, user=user, owner_field="user_id", require_owner=True
    )


@router.get("/", response_model=list[HouseholdOut])
def list_households(user=Depends(get_current_user), page=Depends(page_params)):
    households = load_versions("households", Household)
    current = households[(households["is_current"]) & (~households["is_deleted"].fillna(False))]

    # Only return households where user is a member
    memberships = load_versions("user_households", UserHousehold)
    memberships = memberships[
        (memberships["user_id"] == str(user["user_id"]))
        & (memberships["is_current"])
        & (~memberships["is_deleted"].fillna(False))
    ]
    allowed_ids = set(memberships["household_id"])

    current = current[current["household_id"].isin(allowed_ids)]
    current = current.iloc[page["offset"] : page["offset"] + page["limit"]]
    log_action(user["user_id"], "list", "households", None, {"count": len(current)})
    return current.to_dict(orient="records")


@router.get("/memberships", response_model=list[UserHouseholdOut])
def list_household_memberships(user=Depends(get_current_user), page=Depends(page_params)):
    df = load_versions("user_households", UserHousehold)

    if df.empty:
        return []

    # Filter only current user + active memberships
    df = df[(df["user_id"] == str(user["user_id"])) & (df["is_current"]) & (~df.get("is_deleted", False).fillna(False))]
    df = df.iloc[page["offset"] : page["offset"] + page["limit"]]
    log_action(user["user_id"], "list", "household_memberships", None, {"count": len(df)})
    return df.to_dict(orient="records")


@router.get("/{household_id}", response_model=HouseholdOut)
def get_account(household_id: UUID, user=Depends(get_current_user)):
    row = fetch_record(
        "households",
        Household,
        household_id,
        permission_check=lambda r: require_household_role(user, r["household_id"], required_role=Role("member")),
        history=False,
    )
    log_action(user["user_id"], "get", "households", str(household_id))
    return row


@router.get("/{household_id}/history", response_model=list[HouseholdOut])
def get_account_history(household_id: UUID, user=Depends(get_current_user), page=Depends(page_params)):
    versions = fetch_record(
        "households",
        Household,
        household_id,
        permission_check=lambda r: require_household_role(user, r["household_id"], required_role=Role("member")),
        history=True,
        page=page,
        sort_by="updated_at",
    )
    log_action(
        user["user_id"],
        "get_history",
        "households",
        str(household_id),
        {"offset": page["offset"], "limit": page["limit"]},
    )
    return versions


@router.post("/{household_id}/members")
def add_member(household_id: UUID, target_user_id: UUID, role: str = "member", user=Depends(get_current_user)):
    require_household_role(user, household_id, required_role=Role("admin"))
    mapping = UserHousehold(user_id=target_user_id, household_id=household_id, role=Role(role))
    save_version(mapping, "user_households", "mapping_id")
    log_action(
        user["user_id"], "add_member", "households", str(household_id), {"user_id": str(target_user_id), "role": role}
    )
    return {"message": "Member added", "household_id": str(household_id), "user_id": str(target_user_id)}


@router.delete("/{household_id}/members/{target_user_id}")
def remove_member(household_id: UUID, target_user_id: UUID, user=Depends(get_current_user)):
    require_household_role(user, household_id, required_role=Role("admin"))
    df = load_versions("user_households", UserHousehold)
    cur = df[
        (df["user_id"] == str(target_user_id))
        & (df["household_id"] == str(household_id))
        & (df["is_current"])
        & (~df.get("is_deleted", False).fillna(False))
    ]
    if cur.empty:
        raise HTTPException(status_code=404, detail="Membership not found")
    row = cur.iloc[0]
    mark_old_version_as_stale("user_households", row["mapping_id"], "mapping_id")
    # save a deleted version
    deleted = row.to_dict()
    deleted.update({"is_current": True, "is_deleted": True, "updated_at": datetime.now(timezone.utc)})
    save_version(UserHousehold(**deleted), "user_households", "mapping_id")
    log_action(user["user_id"], "remove_member", "households", str(household_id), {"user_id": str(target_user_id)})
    return {"message": "Member removed", "household_id": str(household_id), "user_id": str(target_user_id)}
