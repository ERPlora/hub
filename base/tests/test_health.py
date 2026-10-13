"""/healthz answers before the Host is validated (the ALB probes by IP) and never touches the DB.

/readyz is the deploy pipeline's gate and Route 53's probe (PLAN-AWS §5): 200 with the control
database reachable and every migration applied, 503 otherwise. It answers on a hub's host, on the
platform host (hubs.erplora.com) without a session and on the private name. Its answer is kept
10 s in the process, as saas-next's.
"""

import logging

import pytest
from django.db import OperationalError, connection
from django.db.migrations.recorder import MigrationRecorder

from base import health


@pytest.fixture(autouse=True)
def _forget_the_last_readiness():
    """Every test starts without a remembered /readyz answer."""
    health.forget_readiness()
    yield
    health.forget_readiness()


@pytest.mark.parametrize(
    "host", ["a.localhost:8000", "10.0.3.17:8000", "evil.example.com"]
)
def test_healthz_is_ok_on_any_host_without_the_database(client, host):
    # No django_db mark: any query would fail the test.
    response = client.get("/healthz", HTTP_HOST=host)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_other_paths_still_validate_the_host(client):
    response = client.get("/demo/items", HTTP_HOST="evil.example.com")
    assert response.status_code == 400


def test_only_the_exact_path_is_answered(client):
    response = client.get("/healthz/extra", HTTP_HOST="evil.example.com")
    assert response.status_code == 400


READY_HOSTS = ["a.localhost:8000", "hubs.localhost:8000", "www.localhost:8000"]


@pytest.mark.django_db
class TestReadyz:
    @pytest.mark.parametrize("host", READY_HOSTS)
    def test_is_ok_with_the_database_and_every_migration_applied(self, client, host):
        response = client.get("/readyz", HTTP_HOST=host, HTTP_ACCEPT="text/html")
        assert (response.status_code, response.json()) == (200, {"status": "ok"})
        assert response["Cache-Control"].startswith("max-age=0")

    @pytest.mark.parametrize("host", READY_HOSTS)
    def test_is_503_when_the_database_is_unreachable(
        self, client, monkeypatch, caplog, host
    ):
        def unreachable(*args, **kwargs):
            raise OperationalError("connection refused")

        monkeypatch.setattr(connection, "ensure_connection", unreachable)
        with caplog.at_level(logging.WARNING, logger="base.health"):
            response = client.get("/readyz", HTTP_HOST=host)
        assert (response.status_code, response.json()) == (
            503,
            {"status": "unavailable", "reason": "database"},
        )
        assert "connection refused" in caplog.text

    def test_is_503_while_a_migration_is_pending(self, client):
        MigrationRecorder(connection).record_unapplied(
            "base", "0002_prefixed_membership_roles"
        )
        response = client.get("/readyz", HTTP_HOST="a.localhost:8000")
        assert (response.status_code, response.json()) == (
            503,
            {"status": "unavailable", "reason": "migrations"},
        )

    def test_still_validates_the_host(self, client):
        assert client.get("/readyz", HTTP_HOST="evil.example.com").status_code == 400

    @pytest.mark.parametrize("path", ["/readyz/", "/readyz/extra", "/readyzz"])
    def test_only_the_exact_path_skips_the_platform_host_gate(self, client, path):
        # Anything else on hubs.localhost without a session still goes to the SaaS admin's Hubs page.
        response = client.get(
            path, HTTP_HOST="hubs.localhost:8000", HTTP_ACCEPT="text/html"
        )
        assert response.status_code == 302


# The answer is kept 10 s in the process (Route 53 probes it about 30 times a minute): the database
# is read at most once per window. Never in Valkey: if Valkey falls, /readyz must not fall with it.

HOST = "a.localhost:8000"


class Clock:
    """``health.monotonic`` under the test's control."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(health, "monotonic", fake)
    return fake


@pytest.fixture
def reads(monkeypatch):
    """How many times /readyz read the migrations of the control database."""
    count = {"reads": 0}
    real = health.MigrationExecutor

    def counted(*args, **kwargs):
        count["reads"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(health, "MigrationExecutor", counted)
    return count


@pytest.mark.django_db
class TestReadyzKeepsItsAnswer:
    def test_reads_the_database_once_per_ten_seconds(self, client, clock, reads):
        first = client.get("/readyz", HTTP_HOST=HOST)
        clock.now += 9.9
        second = client.get("/readyz", HTTP_HOST=HOST)

        assert (first.status_code, second.status_code) == (200, 200)
        assert second.json() == {"status": "ok"}
        assert reads["reads"] == 1
        # The kept answer is still never cached by anything in between.
        assert second["Cache-Control"].startswith("max-age=0")

    def test_reads_the_database_again_after_ten_seconds(self, client, clock, reads):
        client.get("/readyz", HTTP_HOST=HOST)
        clock.now += 10
        client.get("/readyz", HTTP_HOST=HOST)

        assert reads["reads"] == 2

    def test_a_503_is_kept_too_and_the_next_window_recovers(
        self, client, clock, monkeypatch
    ):
        real = health.MigrationExecutor
        database = {"up": False}

        def executor(*args, **kwargs):
            if not database["up"]:
                raise OperationalError("connection refused")
            return real(*args, **kwargs)

        monkeypatch.setattr(health, "MigrationExecutor", executor)

        down = client.get("/readyz", HTTP_HOST=HOST)
        database["up"] = True
        still_kept = client.get("/readyz", HTTP_HOST=HOST)
        clock.now += 10
        recovered = client.get("/readyz", HTTP_HOST=HOST)

        assert (down.status_code, still_kept.status_code, recovered.status_code) == (
            503,
            503,
            200,
        )
        assert still_kept.json() == {"status": "unavailable", "reason": "database"}

    def test_a_kept_answer_still_validates_the_host(self, client, clock):
        assert client.get("/readyz", HTTP_HOST=HOST).status_code == 200

        assert client.get("/readyz", HTTP_HOST="evil.example.com").status_code == 400

    def test_does_not_depend_on_the_cache(self, client, clock, settings):
        """A Valkey that is down (the cache backend fails) changes nothing: the answer lives in
        the process."""
        settings.CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": "redis://127.0.0.1:1",
                "OPTIONS": {"socket_connect_timeout": 0.1, "socket_timeout": 0.1},
            }
        }

        first = client.get("/readyz", HTTP_HOST=HOST)
        second = client.get("/readyz", HTTP_HOST=HOST)

        assert (first.status_code, second.status_code) == (200, 200)
