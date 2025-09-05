from fastapi import APIRouter, HTTPException, Depends
from uuid import UUID, uuid4
from datetime import datetime, timezone
from app.models.schemas import Household, User
from app.services.storage import save_version, mark_old_version_as_stale, load_versions
from app.services.auth import get_current_user

router = APIRouter()

@router.post("/")
def create_household(household: Household, user=Depends(get_current_user)):
    new_household = Household(
        household_id=uuid4(),
        name=household.name,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False
    )
    save_version(new_household, "households", "household_id")
    return {"message": "Household created", "household_id": str(new_household.household_id)}


@router.put("/{household_id}")
def update_household(household_id: UUID, name: str):
    mark_old_version_as_stale("households", household_id, "household_id")
    households = load_versions("households", Household)
    current = households[households["household_id"] == str(household_id)].iloc[-1].to_dict()
    updated = Household(
        household_id=household_id,
        name=name,
        created_at=current["created_at"],
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=False
    )
    save_version(updated, "households", "household_id")
    return {"message": "Household updated", "household_id": str(household_id)}


@router.post("/{household_id}/delete")
def soft_delete_household(household_id: UUID):
    mark_old_version_as_stale("households", household_id, "household_id")
    households = load_versions("households", Household)
    current = households[households["household_id"] == str(household_id)].iloc[-1].to_dict()
    deleted = Household(
        household_id=household_id,
        name=current["name"],
        created_at=current["created_at"],
        updated_at=datetime.now(timezone.utc),
        is_current=True,
        is_deleted=True
    )
    save_version(deleted, "households", "household_id")
    return {"message": "Household deleted", "household_id": str(household_id)}


@router.get("/")
def list_households():
    households = load_versions("households", Household)
    current = households[(households["is_current"] == True) & (households["is_deleted"] == False)]
    return current.to_dict(orient="records")


@router.get("/{household_id}")
def get_household(household_id: UUID):
    households = load_versions("households", Household)
    record = households[(households["household_id"] == str(household_id)) & (households["is_current"])]
    if record.empty:
        raise HTTPException(status_code=404, detail="Household not found")
    return record.iloc[0].to_dict()


@router.post("/users/{user_id}/assign-household")
def assign_household_to_user(user_id: UUID, household_id: UUID):
    mark_old_version_as_stale("users", user_id, "user_id")
    users = load_versions("users", User)
    current = users[users["user_id"] == str(user_id)].iloc[-1].to_dict()
    updated = User(
        **{k: current[k] for k in User.model_fields if k in current},
        household_id=household_id,
        updated_at=datetime.now(timezone.utc),
        is_current=True
    )
    save_version(updated, "users", "user_id")
    return {"message": "User assigned to household", "user_id": str(user_id), "household_id": str(household_id)}
