"""``config.asgi``: the client never decides the script prefix (ERPlora/hub#2).

Behind Daphne, a client's ``Daphne-Root-Path: /x`` header becomes ``scope["root_path"]`` (Daphne
always sends the full path, ``/x/api/me``). Django would then answer ``/x/api/me`` as ``/api/me`` and
send its redirects to ``/x/…``. The gates already look at the real path (``request.path_info``), but
the prefix still came from the client. ``application`` ignores it: every request gets the answer of
its real path, the same with the header or without it, on the platform host and on a hub's.
"""

import asyncio
from urllib.parse import urlsplit

import pytest
from asgiref.sync import async_to_sync
from django.core.signals import request_finished, request_started
from django.db import close_old_connections

from config.asgi import application

# The SPA reads the session through an operation (a transaction).
pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("keep_the_test_connection", "spa_manifest"),
]

PLATFORM_HOST = "hubs.localhost:8000"
HUB_HOST = "a.localhost:8000"


@pytest.fixture
def keep_the_test_connection():
    """Django's real handler closes old connections when a request starts and ends, which would drop
    the test's own transaction; its test client unhooks them the same way."""
    request_started.disconnect(close_old_connections)
    request_finished.disconnect(close_old_connections)
    yield
    request_started.connect(close_old_connections)
    request_finished.connect(close_old_connections)


def http_scope(host: str, path: str, root_path: str) -> dict:
    """The scope Daphne builds for a browser's ``GET path`` (``root_path`` from ``Daphne-Root-Path``)."""
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": root_path,
        "headers": [(b"host", host.encode()), (b"accept", b"text/html")],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8000),
    }


async def _call(scope: dict) -> tuple[int, dict[str, str], bytes]:
    """Run ``application`` as Daphne would, in this context: Django's sync parts then run in the
    test's thread and transaction (``ApplicationCommunicator`` clears the context, which sends them to
    another thread with a connection of its own)."""
    inbox = asyncio.Queue()
    inbox.put_nowait({"type": "http.request", "body": b"", "more_body": False})
    sent = []

    async def send(message: dict) -> None:
        sent.append(message)

    # After the body, ``inbox.get`` waits like a client that stays connected until the response.
    await asyncio.wait_for(application(scope, inbox.get, send), timeout=10)
    start, *body = sent
    headers = {
        name.decode().lower(): value.decode() for name, value in start["headers"]
    }
    return (
        start["status"],
        headers,
        b"".join(message.get("body", b"") for message in body),
    )


def get(host: str, path: str, root_path: str = "") -> tuple[int, dict[str, str], bytes]:
    """``GET path`` through the ASGI application, in this thread (the test's) for the sync parts."""
    return async_to_sync(_call)(http_scope(host, path, root_path))


def outcome(response: tuple[int, dict[str, str], bytes]) -> tuple[int, str, str | None]:
    status, headers, _ = response
    return status, headers.get("content-type", ""), headers.get("location")


@pytest.mark.parametrize(
    ("host", "path"),
    [
        (PLATFORM_HOST, "/x/"),
        (PLATFORM_HOST, "/x/admin/"),
        (PLATFORM_HOST, "/x/healthz"),
        (HUB_HOST, "/x/admin/"),
        (HUB_HOST, "/x/api/me"),
        (HUB_HOST, "/x/healthz"),
    ],
)
def test_a_client_root_path_changes_nothing(host, path):
    assert outcome(get(host, path, root_path="/x")) == outcome(get(host, path))


def test_a_client_root_path_does_not_reach_the_api_of_a_hub():
    status, headers, _ = get(HUB_HOST, "/x/api/me", root_path="/x")

    # /x/api/me is a SPA route: a browser without a session goes to the SaaS's login, not to /api/me.
    assert status == 302
    assert not headers["content-type"].startswith("application/json")
    assert not urlsplit(headers["location"]).path.startswith("/x/")
