"""/healthz answers before the Host is validated (the ALB probes by IP) and never touches the DB."""

import pytest


@pytest.mark.parametrize("host", ["a.localhost:8000", "10.0.3.17:8000", "evil.example.com"])
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
