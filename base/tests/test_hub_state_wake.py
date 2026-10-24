"""The SaaS's photo that closes a business reaches its open apps at once (BILLING-F16 of the SaaS, step 4).

An open ``/api/live`` stream or print socket only hears the host gate again when it re-runs
(``base.operations.HubContextBuilder.refresh``), and it re-runs on a notification of the hub's channel, which only
the hub's own writes send: a business suspended while nobody writes would keep its app open until the safety re-run
(300 s). So the photo that suspends it (``PUT /internal/hubs/{id}/state``) notifies the hub's channel after its
COMMIT, with «*» (everything may have changed): every open stream re-runs, hears the gate and ends. A photo that
keeps the business open, or one already seen, wakes nobody.
"""

import json

import psycopg
import pytest
from django.db import connections
from live.context import Scope
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from base.events import HUB_STATE_APPLIED
from base.models import Hub
from base.tests.test_internal import HUB_ID, PATH, signed

pytestmark = pytest.mark.django_db(transaction=True)

ACME = Scope("host", "acme")


@pytest.fixture
def acme():
    return Hub.objects.create(id=HUB_ID, slug="acme", status="ready")


@pytest.fixture
def listening():
    params = connections["default"].settings_dict
    dsn = make_conninfo(
        dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"], host=params["HOST"], port=params["PORT"]
    )
    sessions = []

    def open_session(scope: Scope):
        session = psycopg.connect(dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout: float = 1.0) -> set[str]:
    """The event names the hub's channel heard (the VeriFactu block of the photo sends its own; «*» is the wake)."""
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}


def test_the_photo_that_suspends_a_business_wakes_its_open_apps(client, acme, listening):
    on_acme = listening(ACME)

    answer = signed(client, "put", PATH, {"slug": "acme", "version": 1, "status": "suspended"})

    assert answer.json() == {"applied": True, "version": 1}
    assert "*" in heard(on_acme)


def test_a_photo_that_keeps_the_business_open_wakes_nobody(client, acme, listening):
    on_acme = listening(ACME)

    signed(client, "put", PATH, {"slug": "acme", "version": 1, "status": "past_due"})
    signed(client, "put", PATH, {"slug": "acme", "version": 2, "status": "active"})

    assert "*" not in heard(on_acme, timeout=0.5)


def test_a_photo_already_seen_or_still_suspended_wakes_nobody_again(client, acme, listening):
    on_acme = listening(ACME)
    signed(client, "put", PATH, {"slug": "acme", "version": 1, "status": "suspended"})
    assert "*" in heard(on_acme)

    signed(client, "put", PATH, {"slug": "acme", "version": 1, "status": "suspended"})  # already seen
    signed(client, "put", PATH, {"slug": "acme", "version": 2, "status": "suspended"})  # still suspended

    assert "*" not in heard(on_acme, timeout=0.5)


def test_the_delete_that_ends_a_business_wakes_its_open_apps_too(client, acme, listening):
    # The same gap for a business the SaaS deleted (410): its open apps hear the gate now, not at the next write.
    on_acme = listening(ACME)

    answer = signed(client, "delete", f"/internal/hubs/{HUB_ID}", {})
    assert answer.status_code == 202
    assert "*" in heard(on_acme)

    signed(client, "delete", f"/internal/hubs/{HUB_ID}", {})  # already cancelled: nothing changed, nobody woken
    assert "*" not in heard(on_acme, timeout=0.5)


def test_every_new_photo_reaches_the_live_queries_of_its_business_only(client, acme, listening):
    # The live queries that follow the photo (the Home's three, Apps, «Plan and limits»: base/live.py) listen on the
    # business's channel; the photo is applied as the platform (/internal), so its event went to the platform's
    # channel only and nothing of the business moved until a reload. Now it reaches the business after the COMMIT,
    # and no other business hears it; a photo already seen tells nobody.
    on_acme = listening(ACME)
    on_other = listening(Scope("host", "other"))
    plan = {"slug": "starter", "max_users": 3, "max_devices": 2}

    assert signed(client, "put", PATH, {"slug": "acme", "version": 1, "plan": plan}).json()["applied"] is True
    assert HUB_STATE_APPLIED in heard(on_acme)
    assert heard(on_other, timeout=0.5) == set()

    assert signed(client, "put", PATH, {"slug": "acme", "version": 1, "plan": plan}).json()["applied"] is False
    assert heard(on_acme, timeout=0.5) == set()
