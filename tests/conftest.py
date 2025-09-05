import os
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
import boto3
import app.main as app
from app.config import config


@pytest.fixture(autouse=True)
def clean_bucket(setup_s3):
    bucket = "household-finances-test"
    resp = setup_s3.list_objects_v2(Bucket=bucket)
    for obj in resp.get("Contents", []):
        setup_s3.delete_object(Bucket=bucket, Key=obj["Key"])
    yield

@pytest.fixture(scope="session", autouse=True)
def setup_s3():
    env = os.getenv("APP_ENV", "dev")
    bucket_name = config.get("s3", {}).get("bucket_name", "household-finances-dev")

    if env == "dev":
        # Use moto for local testing
        with mock_aws():
            s3 = boto3.client("s3", region_name=config.get("region", "eu-west-1"))
            s3.create_bucket(Bucket=bucket_name)
            yield s3
    else:
        # Use real S3 in test env
        s3 = boto3.client("s3", region_name=config.get("region", "eu-west-1"))
        yield s3

@pytest.fixture(scope="function")
def client():
    return TestClient(app.app)