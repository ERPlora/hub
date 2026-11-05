"""What a refused request leaves in the Hub's log (settings.LOGGING, CloudWatch Logs in production).

A Host outside ALLOWED_HOSTS (a scanner, someone pointing a domain at the balancer) is answered 400 and leaves no line
at all: Django would write an ERROR with its whole traceback for each one (hub#817). Every other suspicious request
(django.security.*) is still an ERROR.
"""

import io
import logging

import pytest
from django.core.exceptions import (
    SuspiciousFileOperation,
    SuspiciousOperation,
    TooManyFieldsSent,
)
from django.core.handlers.exception import response_for_exception

from base import registry


@pytest.fixture
def console():
    """What the console handler of settings.LOGGING writes during the test, as configured when Django started."""
    handler = next(
        handler
        for handler in logging.getLogger("django").handlers
        if handler.get_name() == "console"
    )
    written = io.StringIO()
    before = handler.setStream(written)
    yield written
    handler.setStream(before)


@pytest.fixture
def nobody_has_a_domain(monkeypatch):
    """A host outside ALLOWED_HOSTS may read who has which domain (base.custom_domains): no business has one here."""
    monkeypatch.setattr(registry, "custom_domains", list)


@pytest.mark.parametrize(
    ("host", "path"),
    [("scanner.example.test", "/"), ("203.0.113.9", "/wp-login.php")],
)
def test_an_unknown_host_is_refused_without_a_line_in_the_log(
    client, console, nobody_has_a_domain, host, path
):
    response = client.get(path, HTTP_HOST=host)

    assert response.status_code == 400
    assert console.getvalue() == ""


@pytest.mark.parametrize(
    "suspicious",
    [
        SuspiciousOperation("Something odd in the request"),
        SuspiciousFileOperation("Detected path traversal attempt"),
        TooManyFieldsSent("The number of GET/POST parameters exceeded"),
    ],
    ids=lambda suspicious: type(suspicious).__name__,
)
def test_any_other_suspicious_request_is_still_an_error(rf, console, suspicious):
    # The very function the request handler hands every exception to, on a host the Hub serves.
    response = response_for_exception(rf.get("/"), suspicious)

    assert response.status_code == 400
    line = console.getvalue().splitlines()[0]
    assert f" ERROR django.security.{type(suspicious).__name__} " in line
