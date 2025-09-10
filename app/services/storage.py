from uuid import UUID, uuid4
import pyarrow.parquet as pq
import boto3
import json
import io
import pyarrow as pa
import botocore
from datetime import datetime, timezone, date, timedelta
import pyarrow.dataset as ds
import pandas as pd
from typing import Type, Optional
from fastapi import HTTPException
from app.config import config
from app.models.schemas import Entry, User, Household, Account, UserAccount, UserHousehold, RefreshToken, AuditLog

s3 = boto3.client("s3", region_name=config.get("region", "eu-west-1"))
BUCKET_NAME = config.get("s3", {}).get("bucket_name", "household-finances-dev")
SENSITIVE_FIELDS = {"password", "hashed_password", "access_token", "refresh_token"}

def mark_old_version_as_stale(record_type: str, record_id: UUID, id_column: str = "id") -> None:
    prefix = f"{record_type}/{id_column}={record_id}/"
    result = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)

    if "Contents" not in result:
        raise HTTPException(status_code=404, detail=f"No versions found for {record_type} {record_id}")

    for obj in result["Contents"]:
        key = obj["Key"]
        obj_data = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        body = io.BytesIO(obj_data["Body"].read())
        table = pq.read_table(body)
        df = table.to_pandas()

        if df.get("is_current", True).iloc[0]:
            df["is_current"] = False
            buffer = io.BytesIO()
            pq.write_table(pa.Table.from_pandas(df), buffer)
            buffer.seek(0)
            s3.put_object(Bucket=BUCKET_NAME, Key=key, Body=buffer.read())

def cascade_stale(record_type: str, record_id: str, mapping_type: str, foreign_key: str):
    df = load_versions(mapping_type)
    matches = df[
        (df[foreign_key] == record_id) &
        (df["is_current"]) &
        (~df["is_deleted"].fillna(False))
    ]

    for _, row in matches.iterrows():
        mark_old_version_as_stale(mapping_type, row["mapping_id"], "mapping_id")
        

def save_version(record, record_type: str, id_field: str):
    # Handle both Pydantic models and plain dicts
    if hasattr(record, "model_dump"):  # Pydantic v2
        record_data = record.model_dump()
    elif hasattr(record, "dict"):  # Pydantic v1
        record_data = record.dict()
    elif isinstance(record, dict):
        record_data = record
    else:
        raise TypeError(f"Unsupported object type for save_version: {type(record)}")

    # Convert UUIDs and datetimes
    for k, v in record_data.items():
        if isinstance(v, UUID):
            record_data[k] = str(v)
        if isinstance(v, datetime):
            record_data[k] = pd.to_datetime(v)

    df = pd.DataFrame([record_data])

    record_id = record_data[id_field]
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%S%fZ")

    # Hybrid partitioning: id → year → month → day
    key = (
        f"{record_type}/{id_field}={record_id}/"
        f"year={now.year}/month={now.month:02}/day={now.day:02}/"
        f"{record_type[:-1]}-{record_id}-{timestamp}.parquet"
    )

    table = pa.Table.from_pandas(df, preserve_index=False)
    out_buffer = pa.BufferOutputStream()
    pq.write_table(table, out_buffer)

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=out_buffer.getvalue().to_pybytes()
    )

def _empty_df(schema):
    if schema is None:
        return pd.DataFrame()
    if hasattr(schema, "model_fields"):  # Pydantic v2
        return pd.DataFrame(columns=list(schema.model_fields.keys()))
    if hasattr(schema, "__fields__"):  # Pydantic v1
        return pd.DataFrame(columns=list(schema.__fields__.keys()))
    return pd.DataFrame(columns=list(schema))

def load_versions(
    record_type: str,
    schema,
    record_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None
):
    prefix = f"{record_type}/"

    if start and end:
        # Only scan partitions within the date range
        keys = []
        current = start
        while current <= end:
            prefix_dt = f"{record_type}/year={current.year}/month={current.month:02d}/day={current.day:02d}/"
            resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix_dt)
            for obj in resp.get("Contents", []):
                keys.append(obj["Key"])
            current += timedelta(days=1)
    elif record_id:
        prefix = f"{record_type}/{schema.__name__.lower()}_id={record_id}/"
        resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
        keys = [obj["Key"] for obj in resp.get("Contents", [])]
    else:
        resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
        keys = [obj["Key"] for obj in resp.get("Contents", [])]

    if not keys:
        return pd.DataFrame(columns=schema.model_fields.keys())

    dfs = []
    for key in keys:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        dfs.append(pd.read_parquet(io.BytesIO(obj["Body"].read())))

    return pd.concat(dfs, ignore_index=True)


def resolve_id_by_name(record_type: str, name: str, schema, name_field: str, id_field: str) -> str:
    df = load_versions(record_type, schema)

    match = df[
        (df[name_field] == name) &
        (df["is_current"]) &
        (~df["is_deleted"].fillna(False))
    ]

    if match.empty:
        raise HTTPException(status_code=404, detail=f"{record_type[:-1].capitalize()} '{name}' not found")

    return match.iloc[0][id_field]


def resolve_name_by_id(record_type: str, record_id: str, schema, id_field: str, name_field: str) -> str:
    df = load_versions(record_type, schema)

    match = df[
        (df[id_field] == record_id) &
        (df["is_current"]) &
        (~df["is_deleted"].fillna(False))
    ]

    if match.empty:
        raise HTTPException(status_code=404, detail=f"{record_type[:-1].capitalize()} '{record_id}' not found")

    return match.iloc[0][name_field]

def soft_delete_record(
    record_type: str,
    record_id: str,
    id_field: str,
    model_cls: Type,
    *,
    user: Optional[dict] = None,
    owner_field: str = "user_id",
    require_owner: bool = True
):
    """
    Generic soft delete helper:
      - marks old versions stale
      - saves a new version with is_deleted=True and is_current=True
      - performs built-in cascade for 'users' and 'debts'
    """
    df = load_versions(record_type, model_cls)

    match = df[
        (df[id_field] == str(record_id)) &
        (df["is_current"]) &
        (~df.get("is_deleted", False).fillna(False))
    ]

    if match.empty:
        raise HTTPException(status_code=404, detail=f"{record_type[:-1].capitalize()} not found")

    row = match.iloc[0]

    # Authorization / ownership check
    if require_owner and user is not None:
        # only check if owner field exists in row
        if owner_field in row and str(row[owner_field]) != str(user.get("user_id")):
            raise HTTPException(status_code=403, detail="Not authorized to delete this resource")

    # Mark existing versions stale
    mark_old_version_as_stale(record_type, record_id, id_field)

    # Build deleted object, copying values from the found row
    now = datetime.now(timezone.utc)
    data = row.to_dict()
    # ensure id is present
    data[id_field] = data.get(id_field) or str(record_id)
    data.update({
        "updated_at": now,
        "is_current": True,   # latest version will indicate deleted
        "is_deleted": True,
    })

    # instantiate model and save
    deleted_obj = model_cls(**data)
    save_version(deleted_obj, record_type, id_field)
    log_action(user.get("user_id") if user else None, "delete", record_type, str(record_id))

    # Built-in cascades:
    if record_type == "users":
        _cascade_user_deletion(str(record_id), now)
    elif record_type == "debts":
        # try to cascade debt -> entries (best-effort)
        _cascade_debt_deletion(str(record_id), row, now)

    return {"message": f"{record_type[:-1].capitalize()} deleted", id_field: str(record_id)}


def _cascade_user_deletion(user_id: str, now: datetime):
    """Mark user_accounts, user_households and refresh_tokens as deleted for this user."""
    # user_accounts
    ua_df = load_versions("user_accounts", UserAccount)

    for _, r in ua_df[
        (ua_df["user_id"] == str(user_id)) &
        (ua_df["is_current"]) &
        (~ua_df.get("is_deleted", False).fillna(False))
    ].iterrows():
        mark_old_version_as_stale("user_accounts", r["mapping_id"], "mapping_id")
        data = r.to_dict()
        data.update({"updated_at": now, "is_current": True, "is_deleted": True})
        save_version(UserAccount(**data), "user_accounts", "mapping_id")
        log_action(user_id, "cascade_delete", "account_membership", r["mapping_id"])

    # user_households
    uh_df = load_versions("user_households", UserHousehold)

    for _, r in uh_df[
        (uh_df["user_id"] == str(user_id)) &
        (uh_df["is_current"]) &
        (~uh_df.get("is_deleted", False).fillna(False))
    ].iterrows():
        mark_old_version_as_stale("user_households", r["mapping_id"], "mapping_id")
        data = r.to_dict()
        data.update({"updated_at": now, "is_current": True, "is_deleted": True})
        save_version(UserHousehold(**data), "user_households", "mapping_id")
        log_action(user_id, "cascade_delete", "household_membership", r["mapping_id"])

    # refresh_tokens (invalidate)
    rt_df = load_versions("refresh_tokens", RefreshToken)

    for _, r in rt_df[
        (rt_df["user_id"] == str(user_id)) &
        (rt_df["is_current"])
    ].iterrows():
        mark_old_version_as_stale("refresh_tokens", r["refresh_token_id"], "refresh_token_id")
        # Optionally save a deleted refresh token object if you have a schema, else skipping saving a deleted record is fine.


def _cascade_debt_deletion(debt_id: str, debt_row: pd.Series, now: datetime):
    """
    Cascade delete entries generated by a debt.

    Two modes:
    - If entries have 'debt_id' stored, use it.
    - Otherwise best-effort: match description containing debt.name and same user.
    """

    entries_df = load_versions("entries", Entry)
    debt_name = debt_row.get("name", "")
    user_id = debt_row.get("user_id")
    # If entries include debt_id column, prefer that
    if "debt_id" in entries_df.columns:
        sel = entries_df[
            (entries_df["debt_id"] == str(debt_id)) &
            (entries_df["is_current"]) &
            (~entries_df.get("is_deleted", False).fillna(False))
        ]
    else:
        # fallback: match by description (best-effort)
        sel = entries_df[
            (entries_df["description"].str.contains(str(debt_name), na=False)) &
            (entries_df["user_id"] == str(user_id)) &
            (entries_df["is_current"]) &
            (~entries_df.get("is_deleted", False).fillna(False))
        ]

    for _, row in sel.iterrows():
        mark_old_version_as_stale("entries", row["entry_id"], "entry_id")
        data = row.to_dict()
        data.update({"updated_at": now, "is_current": True, "is_deleted": True})
        save_version(Entry(**data), "entries", "entry_id")
        log_action(user_id, "cascade_delete", "entries", row["entry_id"])

def log_action(user_id: str | None, action: str, resource_type: str, resource_id: str | None, details: dict | None = None):

    # Normalize details: convert UUIDs and datetimes to strings
    normalized = {}
    for k, v in (details or {}).items():
        if k in SENSITIVE_FIELDS:
            normalized[k] = "***REDACTED***"
        elif isinstance(v, UUID):
            normalized[k] = str(v)
        elif isinstance(v, (datetime, date)):
            normalized[k] = v.isoformat()
        else:
            normalized[k] = v
    details_json = json.dumps(normalized) 

    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details_json,
    )
    
    save_version(entry, "audit_logs", "log_id")
