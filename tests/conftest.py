import os
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
import boto3
import app.main as app
from app.config import load_config

@pytest.fixture(scope="session", autouse=True)
def setup_s3():
    env = os.getenv("APP_ENV", "dev")

    if env == "dev":
        # Use moto for local testing
        with mock_aws():
            s3 = boto3.client("s3", region_name="eu-west-1")
            s3.create_bucket(Bucket="household-finances-dev")
            yield s3
    else:
        # Use real S3 in test env
        s3 = boto3.client("s3", region_name="eu-west-1")
        yield s3

@pytest.fixture(scope="function")
def client():
    return TestClient(app.app)
