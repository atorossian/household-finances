from uuid import UUID, uuid4
import pyarrow.parquet as pq
import boto3
import io
import pyarrow as pa
import botocore
import pyarrow.dataset as ds
import pandas as pd
from fastapi import HTTPException
from app.config import config

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
    record_id = str(record_data[id_field])
    df = pd.DataFrame([record_data])
    table = pa.Table.from_pandas(df)

    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    buffer.seek(0)

    timestamp = record_data["updated_at"].replace(":", "").replace("-", "").replace("T", "").split(".")[0]
    key = f"{record_type}/{id_field}={record_id}/{record_type[:-1]}-{record_id}-{timestamp}.parquet"

    s3.put_object(Bucket=BUCKET_NAME, Key=key, Body=buffer.read())

def load_versions(entity: str):
    key = f"{entity}.parquet"
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        return pd.read_parquet(obj['Body'])
    except s3.exceptions.NoSuchKey:
        return pd.DataFrame(columns=entity.__fields__.keys())
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "NoSuchKey":
            return pd.DataFrame(columns=entity.__fields__.keys())
        raise

def resolve_id_by_name(record_type: str, name: str, id_field: str) -> str:
    df = load_versions(record_type)

    match = df[
        (df["user_name"].str == name) &
        (df["is_current"] == True) &
        (~df["is_deleted"].fillna(False))
    ]

    if match.empty:
        raise HTTPException(status_code=404, detail=f"{record_type[:-1].capitalize()} '{name}' not found")

    return match.iloc[0][id_field]

def resolve_name_by_id(record_type: str, id: str, name_field: str) -> str:
    df = load_versions(record_type)

    match = df[
        (df["user_id"] == id) &
        (df["is_current"] == True) &
        (~df["is_deleted"].fillna(False))
    ]

    if match.empty:
        raise HTTPException(status_code=404, detail=f"{record_type[:-1].capitalize()} '{id}' not found")

    return match.iloc[0][name_field]