from app.services.storage import save_version, load_versions, mark_old_version_as_stale, resolve_id_by_name, soft_delete_record, log_action
from datetime import datetime, timezone
from app.models.schemas.entry import EntryCreate, Entry, EntryUpdate, EntryOut
from app.models.schemas.account import Account
from app.models.schemas.household import Household
from app.models.schemas.membership import UserAccount, UserHousehold
from uuid import UUID, uuid4
import boto3
import pandas as pd
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
import io
from app.services.auth import get_current_user
from app.services.roles import validate_entry_permissions
from app.services.utils import page_params
from app.services.fetchers import fetch_record

router = APIRouter()

@router.post("/")
def create_entry(payload: EntryCreate, user=Depends(get_current_user)):
    account_id = resolve_id_by_name("accounts", payload.account_name, Account, "name",  "account_id")
    household_id = resolve_id_by_name("households", payload.household_name, Household, "name", "household_id")
    
    validate_entry_permissions(str(payload.user_id), account_id, household_id, acting_user=user)

    entry = Entry(
        entry_id=uuid4(),
        user_id=payload.user_id,
        account_id=account_id,
        household_id=household_id,
        entry_date=payload.entry_date,
        value_date=payload.value_date,
        type=payload.type,
        category=payload.category,
        amount=payload.amount,
        description=payload.description,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_current=True,
    )

    save_version(entry, "entries", "entry_id")
    log_action(user["user_id"], "create", "entries", str(entry.entry_id), payload.model_dump())

    return {"message": "Entry created", "entry_id": str(entry.entry_id)}

@router.post("/import")
def import_entries_upload(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """
    Import entries from a CSV or Excel (xlsx) file.
    Required columns (case-insensitive):
      - entry_date (YYYY-MM-DD)
      - value_date (YYYY-MM-DD)
      - type ("income" | "expense")
      - category (matches Category enum; e.g., "groceries")
      - amount (number)
    One of:
      - account_id + household_id
      - account_name + household_name (will be resolved)

    Optional:
      - description
    """
    raw = file.file.read()
    name = (file.filename or "").lower()

    # Load dataframe based on extension
    try:
        if name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            # default to CSV
            try:
                df = pd.read_csv(io.StringIO(raw.decode("utf-8-sig")))
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(raw))  # fallback
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    if df.empty:
        return {"imported": 0, "skipped": 0, "entry_ids": []}

    # Normalize columns: lowercase + strip
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = {"entry_date", "value_date", "type", "category", "amount"}
    has_ids = {"account_id", "household_id"}.issubset(set(df.columns))
    has_names = {"account_name", "household_name"}.issubset(set(df.columns))
    if not required.issubset(set(df.columns)):
        missing = required - set(df.columns)
        raise HTTPException(status_code=400, detail=f"Missing required columns: {sorted(missing)}")
    if not (has_ids or has_names):
        raise HTTPException(
            status_code=400,
            detail="Provide either (account_id, household_id) or (account_name, household_name) columns.",
        )

    # Cast/clean minimal types
    # Let pandas parse dates; coerce errors -> NaT to catch invalids
    for dcol in ["entry_date", "value_date"]:
        df[dcol] = pd.to_datetime(df[dcol], errors="coerce").dt.date
    # Basic validations
    bad_dates = df["entry_date"].isna() | df["value_date"].isna()
    if bad_dates.any():
        raise HTTPException(status_code=400, detail=f"Invalid dates in rows: {df.index[bad_dates].tolist()}")

    # Resolve IDs if needed
    if has_names and not has_ids:
        # resolve once per unique name to cut lookups
        hname_to_id = {}
        aname_to_id = {}
        for hname in df["household_name"].dropna().unique():
            hid = resolve_id_by_name("households", hname, Household, "name", "household_id")
            hname_to_id[hname] = hid
        for aname in df["account_name"].dropna().unique():
            aid = resolve_id_by_name("accounts", aname, Account, "name", "account_id")
            aname_to_id[aname] = aid

        df["household_id"] = df["household_name"].map(hname_to_id)
        df["account_id"] = df["account_name"].map(aname_to_id)

        if df["household_id"].isna().any() or df["account_id"].isna().any():
            raise HTTPException(status_code=404, detail="Could not resolve some account/household names to IDs.")

    imported_ids: list[str] = []
    skipped = 0

    # Import each row
    for _, row in df.iterrows():
        try:
            # Permission: entry belongs to the acting user
            acting_user_id = str(user["user_id"])
            account_id = str(row["account_id"])
            household_id = str(row["household_id"])

            # enforce permissions (also checks membership + assignment)
            validate_entry_permissions(
                user_id=acting_user_id,
                account_id=account_id,
                household_id=household_id,
                acting_user=user,
            )

            entry = Entry(
                user_id=acting_user_id,
                account_id=account_id,
                household_id=household_id,
                entry_date=row["entry_date"],
                value_date=row["value_date"],
                type=str(row["type"]).strip().lower(),
                category=str(row["category"]).strip().lower(),
                amount=row["amount"],
                description=(None if pd.isna(row.get("description")) else str(row.get("description"))),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_current=True,
                is_deleted=False,
            )
            save_version(entry, "entries", "entry_id")
            imported_ids.append(str(entry.entry_id))
        except HTTPException:
            # bubble API exceptions
            raise
        except Exception:
            skipped += 1
            continue

    log_action(user["user_id"], "import", "entries", None, {"imported": len(imported_ids), "skipped": skipped})
    return {"imported": len(imported_ids), "skipped": skipped, "entry_ids": imported_ids}

@router.put("/{entry_id}")
def update_entry(entry_id: UUID, payload: EntryUpdate, user=Depends(get_current_user)):
    account_id = resolve_id_by_name("accounts", payload.account_name, Account, "name", "account_id")
    household_id = resolve_id_by_name("households", payload.household_name, Household, "name", "household_id")

    df = load_versions("entries", Entry, record_id=entry_id)
    current = df[(df["is_current"]) & (~df["is_deleted"].fillna(False))]
    if current.empty:
        raise HTTPException(status_code=404, detail="Entry not found")

    validate_entry_permissions(str(payload.user_id), account_id, household_id, user)

    # Stale old version
    mark_old_version_as_stale("entries", entry_id, "entry_id")

    updated = Entry(
        entry_id=entry_id,
        user_id=payload.user_id,
        account_id=account_id,
        household_id=household_id,
        entry_date=payload.entry_date,
        value_date=payload.value_date,
        type=payload.type,
        category=payload.category,
        amount=payload.amount,
        description=payload.description,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_current=True,
    )

    save_version(updated, "entries", "entry_id")
    log_action(user["user_id"], "update", "entries", str(entry_id), payload.model_dump())

    return {"message": "Entry updated", "entry_id": str(entry_id)}


@router.delete("/{entry_id}")
def delete_entry(entry_id: UUID, user=Depends(get_current_user)):
    df = load_versions("entries", Entry, record_id=entry_id)
    current = df[(df["is_current"]) & (~df["is_deleted"].fillna(False))]
    if current.empty:
        raise HTTPException(status_code=404, detail="Entry not found")

    row = current.iloc[0].to_dict()
    validate_entry_permissions(row["user_id"], row["account_id"], row["household_id"], user)

    return soft_delete_record(
        "entries", str(entry_id), "entry_id", Entry,
        user=user, require_owner=False
    )

@router.get("/", response_model=list[EntryOut])
def list_current_entries(user=Depends(get_current_user), page=Depends(page_params)):
    df = load_versions("entries", Entry)
    if df.empty:
        return []

    # Filter current and active
    df = df[(df["is_current"]) & (~df.get("is_deleted", False).fillna(False))]

    # Validate each debt against entry permissions
    allowed = []
    for _, row in df.iterrows():
        try:
            validate_entry_permissions(
                user_id=row["user_id"],
                account_id=row["account_id"],
                household_id=row["household_id"],
                acting_user=user,
            )
            allowed.append(row)
        except HTTPException:
            continue

    # Build new dataframe from allowed rows
    if not allowed:
        return []
    df = pd.DataFrame(allowed)
    df = df.iloc[page["offset"] : page["offset"] + page["limit"]]

    log_action(user["user_id"], "list", "entries", None, {"count": len(df)})

    return df.to_dict(orient="records")

@router.get("/{entry_id}", response_model=EntryOut)
def get_entry(entry_id: UUID, user=Depends(get_current_user)):
    row = fetch_record(
        "entries", Entry, str(entry_id),
        permission_check=lambda r: validate_entry_permissions(r["user_id"], r["account_id"], r["household_id"], user),
        history=False,
    )
    log_action(user["user_id"], "get", "entries", str(entry_id))
    return row

@router.get("/{entry_id}/history", response_model=list[EntryOut])
def get_entry_history(entry_id: UUID, user=Depends(get_current_user), page=Depends(page_params)):
    versions = fetch_record(
        "entries", Entry, str(entry_id),
        permission_check=lambda r: validate_entry_permissions(r["user_id"], r["account_id"], r["household_id"], user),
        history=True, page=page, sort_by="updated_at",
    )
    log_action(
        user["user_id"], "get_history", "entries", str(entry_id),
        {"offset": page["offset"], "limit": page["limit"]}
    )
    return versions