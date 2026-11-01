"""The dumps bucket of the tests: a real S3 server (moto's, in a thread of the session) behind boto3, never a mock.

:func:`moto_s3` starts it once per session (and xdist worker) on a free port of the loopback; :func:`dumps_bucket`
gives each test a bucket of its own on it and points ``base.tenancy.dumps`` there (``HUB_DUMPS_BUCKET``,
``HUB_DUMPS_ENDPOINT_URL``), with throwaway credentials: the shell's AWS session is never signed with (a red diff would
print it, as saas's presign tests once did). Its objects are read back with :func:`objects` and :func:`body`.
"""

import uuid
from collections.abc import Iterator

import boto3
import pytest
from botocore.config import Config

REGION = "eu-west-1"
#: What the tests sign with: moto takes any key.
FAKE_CREDENTIALS = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SESSION_TOKEN": "testing",
}


@pytest.fixture(scope="session")
def moto_s3() -> Iterator[str]:
    """The S3 server of the session: its endpoint (``http://127.0.0.1:<port>``)."""
    from moto.server import ThreadedMotoServer

    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


def client(endpoint: str):
    return boto3.client(
        "s3",
        region_name=REGION,
        endpoint_url=endpoint,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        aws_session_token="testing",
        config=Config(signature_version="s3v4"),
    )


@pytest.fixture
def aws_test_credentials(monkeypatch) -> None:
    """Throwaway credentials and region in the environment, the shell's profile out of reach."""
    for variable in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", "/dev/null")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/dev/null")
    for variable, value in FAKE_CREDENTIALS.items():
        monkeypatch.setenv(variable, value)
    monkeypatch.setenv("AWS_REGION", REGION)


@pytest.fixture
def dumps_bucket(moto_s3, aws_test_credentials, monkeypatch) -> str:
    """A bucket of this test's own on the session's S3 server, named as ``HUB_DUMPS_BUCKET``."""
    name = f"erplora-test-hub-dumps-{uuid.uuid4().hex[:12]}"
    client(moto_s3).create_bucket(Bucket=name, CreateBucketConfiguration={"LocationConstraint": REGION})
    monkeypatch.setenv("HUB_DUMPS_BUCKET", name)
    monkeypatch.setenv("HUB_DUMPS_ENDPOINT_URL", moto_s3)
    return name


@pytest.fixture
def no_dumps_bucket(monkeypatch, aws_test_credentials) -> None:
    """No bucket named: the environment of a process without ``HUB_DUMPS_BUCKET`` (local development)."""
    monkeypatch.setenv("HUB_DUMPS_BUCKET", "")
    monkeypatch.delenv("HUB_DUMPS_ENDPOINT_URL", raising=False)


def objects(endpoint: str, bucket: str) -> dict[str, int]:
    """Every key of ``bucket`` with its size."""
    listed = client(endpoint).list_objects_v2(Bucket=bucket)
    return {item["Key"]: item["Size"] for item in listed.get("Contents", [])}


def body(endpoint: str, bucket: str, key: str) -> bytes:
    return client(endpoint).get_object(Bucket=bucket, Key=key)["Body"].read()
