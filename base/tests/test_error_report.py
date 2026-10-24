"""``POST /api/error-report``: the errors the screen reports by itself (BASE-G95, G13, G50; HUB_SHELL-F149).

PLAN-SAAS §1.1 (round 2026-10-15b, PLAN-HUB «Embudo de errores»): each report is one structured log line that
CloudWatch counts and alarms on; no table and no issue. Only a session of the hub sends them, a caller cannot flood the
log, and a report that cannot be read is refused without a line.
"""

import json
import logging

import pytest
from django.test import Client
from django.urls import resolve

from base import error_report

pytestmark = pytest.mark.django_db

URL = "/api/error-report"
HOST = "a.localhost:8000"
REPORT = {
    "kind": "error",
    "message": "TypeError: Cannot read properties of undefined (reading 'total')",
    "stack": "TypeError: Cannot read properties of undefined\n    at setup (CartPage.vue:42:7)",
    "url": "/sale/cart",
    "component": "CartPage",
}


@pytest.fixture
def owner(client, make_user):
    client.force_login(make_user("ana", host="a", role="hub_owner"))
    return client


@pytest.fixture(autouse=True)
def fresh_window(settings):
    """Each test counts from zero: the throttle lives in the cache."""
    from django.core.cache import cache

    cache.clear()


def post(client, body, host=HOST, **extra):
    data = body if isinstance(body, (str, bytes)) else json.dumps(body)
    return client.post(URL, data, content_type="application/json", HTTP_HOST=host, **extra)


def reports(caplog):
    return [
        json.loads(record.getMessage().split(" ", 1)[1])
        for record in caplog.records
        if record.name == "base.error_report"
    ]


def test_the_route_is_the_reports_own_and_not_the_apis():
    assert resolve(URL).func is error_report.error_report


def test_a_report_is_one_error_line_with_where_and_who(client, make_user, caplog):
    user = make_user("ana", host="a", role="hub_owner")
    client.force_login(user)

    with caplog.at_level(logging.INFO, logger="base.error_report"):
        response = post(client, REPORT, HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 14)")

    assert response.status_code == 204
    [record] = [r for r in caplog.records if r.name == "base.error_report"]
    assert record.levelno == logging.ERROR
    assert record.getMessage().startswith("frontend.error ")
    [logged] = reports(caplog)
    assert logged == {**REPORT, "hub": "a", "user": str(user.pk), "user_agent": "Mozilla/5.0 (Linux; Android 14)"}


def test_long_fields_are_cut_and_unknown_ones_dropped(owner, caplog):
    body = {**REPORT, "message": "m" * 2000, "stack": "s" * 10000, "extra": "never logged"}  # within MAX_BODY

    with caplog.at_level(logging.INFO, logger="base.error_report"):
        assert post(owner, body).status_code == 204

    [logged] = reports(caplog)
    assert (len(logged["message"]), len(logged["stack"])) == (error_report.MESSAGE_LENGTH, error_report.STACK_LENGTH)
    assert "extra" not in logged


def test_without_a_session_nothing_is_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger="base.error_report"):
        response = post(client, REPORT)

    assert (response.status_code, response.json()["error"]["code"]) == (401, "unauthorized")
    assert reports(caplog) == []


@pytest.mark.parametrize(
    "body",
    ["not json", json.dumps(["a list"]), json.dumps({"kind": "error"}), json.dumps({**REPORT, "message": ""}),
     json.dumps({**REPORT, "kind": "whatever"}), json.dumps({**REPORT, "message": 42})],
)
def test_a_report_that_cannot_be_read_is_refused_without_a_line(owner, caplog, body):
    with caplog.at_level(logging.INFO, logger="base.error_report"):
        response = post(owner, body)

    assert (response.status_code, response.json()["error"]["code"]) == (400, "invalid_payload")
    assert reports(caplog) == []


def test_a_body_too_large_is_refused(owner, caplog):
    with caplog.at_level(logging.INFO, logger="base.error_report"):
        response = post(owner, {**REPORT, "stack": "s" * (error_report.MAX_BODY + 1)})

    assert (response.status_code, response.json()["error"]["code"]) == (413, "payload_too_large")
    assert reports(caplog) == []


def test_only_post(owner):
    assert owner.get(URL, HTTP_HOST=HOST).status_code == 405


def test_a_beacon_carries_no_csrf_token_and_is_taken(make_user, caplog):
    """``navigator.sendBeacon`` cannot send the CSRF header: the route only writes a log line, never data."""
    client = Client(enforce_csrf_checks=True)
    client.force_login(make_user("ana", host="a", role="hub_owner"))

    with caplog.at_level(logging.INFO, logger="base.error_report"):
        assert post(client, REPORT).status_code == 204

    assert len(reports(caplog)) == 1


def test_a_caller_cannot_flood_the_log(owner, caplog):
    with caplog.at_level(logging.INFO, logger="base.error_report"):
        answers = [post(owner, {**REPORT, "message": f"error {n}"}).status_code for n in range(error_report.LIMIT + 2)]

    assert answers == [204] * error_report.LIMIT + [429, 429]
    assert len(reports(caplog)) == error_report.LIMIT


def test_each_hub_is_named_in_its_own_lines(client, make_user, caplog):
    client.force_login(make_user("bea", host="b", role="hub_owner"))

    with caplog.at_level(logging.INFO, logger="base.error_report"):
        assert post(client, REPORT, host="b.localhost:8000").status_code == 204

    assert [logged["hub"] for logged in reports(caplog)] == ["b"]
