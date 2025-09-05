from uuid import UUID, uuid4
import pyarrow.parquet as pq
import boto3
import io
import pyarrow as pa
import botocore
from datetime import datetime, timezone
import pyarrow.dataset as ds
import pandas as pd
from fastapi import HTTPException
from app.config import config
from app.models.schemas import Entry, User, Household, Account

s3 = boto3.client("s3", region_name=config.get("region", "eu-west-1"))
BUCKET_NAME = config.get("s3", {}).get("bucket_name", "household-finances-dev")

def mark_old_version_as_stale(record_type: str, record_id: UUID, id_column: str = "id") -> None:
    prefix = f"{record_type}/{id_column}={record_id}/"
    result = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)

    if "Contents" not in result:
        raise HTTPException(status_code=404, detail=f"No versions found for {record_type} {record_id}")

    for obj in result["Contents"]:
        key = obj["Key"]
        obj_data = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        table = pq.read_table(obj_data["Body"])
        df = table.to_pandas()

        if df.get("is_current", True).iloc[0]:
            df["is_current"] = False
            buffer = io.BytesIO()
            pq.write_table(pa.Table.from_pandas(df), buffer)
            buffer.seek(0)
            s3.put_object(Bucket=BUCKET_NAME, Key=key, Body=buffer.read())
        

def save_version(record, record_type: str, id_field: str):
    record_data = record.model_dump()

    # Convert UUIDs and datetimes
    for k, v in record_data.items():
        if isinstance(v, UUID):
            record_data[k] = str(v)
        if isinstance(v, datetime):
            record_data[k] = pd.to_datetime(v)

    df = pd.DataFrame([record_data])

    record_id = record_data[id_field]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    key = f"{record_type}/{id_field}={record_id}/{record_type[:-1]}-{record_id}-{timestamp}.parquet"

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

def load_versions(record_type: str, schema=None):
    prefix = f"{record_type}/"
    objects = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix).get("Contents", [])

    dfs = []
    for obj in objects:
        key = obj["Key"]
        body = s3.get_object(Bucket=BUCKET_NAME, Key=key)["Body"].read()
        dfs.append(pd.read_parquet(io.BytesIO(body)))

    if not dfs:
        return _empty_df(schema)

    return pd.concat(dfs, ignore_index=True)

def resolve_id_by_name(record_type: str, name: str, id_field: str) -> str:
    df = load_versions(record_type, User)

    match = df[
        (df["user_name"].str == name) &
        (df["is_current"] == True) &
        (~df["is_deleted"].fillna(False))
    ]

    if match.empty:
        raise HTTPException(status_code=404, detail=f"{record_type[:-1].capitalize()} '{name}' not found")

    return match.iloc[0][id_field]

def resolve_name_by_id(record_type: str, id: str, name_field: str) -> str:
    df = load_versions(record_type, User)

    match = df[
        (df["user_id"] == id) &
        (df["is_current"] == True) &
        (~df["is_deleted"].fillna(False))
    ]

    if match.empty:
        raise HTTPException(status_code=404, detail=f"{record_type[:-1].capitalize()} '{id}' not found")

    return match.iloc[0][name_field]