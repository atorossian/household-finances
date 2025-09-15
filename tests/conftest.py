import os
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
import boto3
import app.main as app
from app.config import config
from uuid import uuid4


def _empty_bucket(s3, bucket_name: str):
    """Helper: delete all objects in the bucket."""
    resp = s3.list_objects_v2(Bucket=bucket_name)
    for obj in resp.get("Contents", []):
        s3.delete_object(Bucket=bucket_name, Key=obj["Key"])


@pytest.fixture(scope="session", autouse=True)
def setup_s3():
    env = os.getenv("APP_ENV", "dev")
    bucket_name = config.get("s3", {}).get("bucket_name", "household-finances-dev")

    if env == "dev":
        with mock_aws():
            s3 = boto3.client("s3", region_name=config.get("region", "eu-west-1"))
            s3.create_bucket(Bucket=bucket_name)
            yield s3, bucket_name
    else:
        s3 = boto3.client("s3", region_name=config.get("region", "eu-west-1"))
        yield s3, bucket_name
        # Final cleanup after all tests
        _empty_bucket(s3, bucket_name)


@pytest.fixture(autouse=True)
def clean_bucket(setup_s3):
    """Ensure the bucket is empty before each test."""
    s3, bucket_name = setup_s3
    _empty_bucket(s3, bucket_name)
    yield


@pytest.fixture(scope="function")
def client():
    return TestClient(app.app)


@pytest.fixture
def auth_headers(client):
    email = f"user-{uuid4().hex[:6]}@example.com"
    payload = {"email": email, "user_name": "user1", "password": "Test123!"}
    client.post("/users/register", json=payload)
    r = client.post("/users/login", json={"email": email, "password": "Test123!"})
    tokens = r.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}

@pytest.fixture
def another_auth_headers(client):
    email = f"user2-{uuid4().hex[:6]}@example.com"
    payload = {"email": email, "user_name": "user2", "password": "Test123!"}
    client.post("/users/register", json=payload)
    r = client.post("/users/login", json={"email": email, "password": "Test123!"})
    tokens = r.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}

@pytest.fixture
def another_user_id(client, another_auth_headers):
    r = client.get("/users/me", headers=another_auth_headers)
    return r.json()["user_id"]

@pytest.fixture
def third_user_id(client):
    email = f"user3-{uuid4().hex[:6]}@example.com"
    payload = {"email": email, "user_name": "user3", "password": "Test123!"}
    client.post("/users/register", json=payload)
    r = client.post("/users/login", json={"email": email, "password": "Test123!"})
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.get("/users/me", headers=headers)
    return r.json()["user_id"]
