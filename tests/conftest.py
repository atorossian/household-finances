# tests/conftest.py
import os
from uuid import uuid4

# --- Configure env for tests *before* importing app code ---
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AWS_REGION", "eu-west-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_SESSION_TOKEN", "test")
# Ensure we always have a bucket name for tests
os.environ.setdefault("S3_BUCKET", f"hf-test-{uuid4().hex}")

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
import boto3

# Import after env is set so settings reads the values above
from app.config import settings
import app.main as app

from app.services.storage import load_versions, save_version
from app.models.schemas.user import User


def _empty_bucket(s3, bucket_name: str):
    """Helper: delete all objects in the bucket."""
    if not bucket_name:
        return
    resp = s3.list_objects_v2(Bucket=bucket_name)
    for obj in resp.get("Contents", []):
        s3.delete_object(Bucket=bucket_name, Key=obj["Key"])


@pytest.fixture(scope="session", autouse=True)
def aws_moto():
    """Global Moto for all tests (no real AWS calls)."""
    with mock_aws():
        yield


@pytest.fixture(scope="session", autouse=True)
def setup_s3(aws_moto):
    """Create the test bucket inside Moto."""
    bucket_name = settings.s3_bucket
    region = settings.aws_region
    s3 = boto3.client("s3", region_name=region)

    # us-east-1 doesn't need LocationConstraint; others do
    if region == "us-east-1":
        s3.create_bucket(Bucket=bucket_name)
    else:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": region},
        )

    yield s3, bucket_name

    # Final cleanup
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


@pytest.fixture(scope="function")
def superuser_client(client):
    # Bootstrap superuser
    register_payload = {
        "email": f"admin-{uuid4().hex[:6]}@example.com",
        "user_name": "admin",
        "password": "AdminTest123!",
    }
    r = client.post("/users/register", json=register_payload)
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    # Promote to superuser
    users_df = load_versions("users", User, record_id=user_id)
    row = users_df.iloc[0].to_dict()
    row.update({"is_superuser": True})
    save_version(User(**row), "users", "user_id")

    # Login
    login_payload = {"email": register_payload["email"], "password": register_payload["password"]}
    r = client.post("/users/login", json=login_payload)
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    return client, headers


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
def another_user(client: TestClient):
    payload = {"email": f"another-{uuid4().hex[:6]}@example.com", "user_name": "anotheruser", "password": "Another123!"}
    r = client.post("/users/register", json=payload)
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    r = client.post("/users/login", json={"email": payload["email"], "password": payload["password"]})
    assert r.status_code == 200
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    return user_id, headers


@pytest.fixture
def third_user(client: TestClient):
    payload = {"email": f"third-{uuid4().hex[:6]}@example.com", "user_name": "thirduser", "password": "Third123!"}
    r = client.post("/users/register", json=payload)
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    r = client.post("/users/login", json={"email": payload["email"], "password": payload["password"]})
    assert r.status_code == 200
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    return user_id, headers
