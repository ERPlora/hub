"""The way in's live queries (APP-BASE-3): what re-runs them, and a change in hub B never reaches A.

The grid of «Switch user» (``base.access.faces``) is the door's, for a session: it follows the PINs being chosen, the
SaaS's photo (people come and go), the business's dial and the devices, so somebody who gets a PIN shows up without
reloading and somebody removed leaves the grid (the old Hub's HUB_SHELL-F04 left them until a reload).
"""

import json

import psycopg
import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from live.context import OperationContext, Scope, system_context
from live.live_registry import live_registry
from live.operations import get
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from base import access, events
from base.models import Credential, Membership, TrustedDevice
from base.schemas import AccessDoorIn, AccessSettingsUpdateIn

pytestmark = pytest.mark.django_db

A, B = Scope("host", "a"), Scope("host", "b")


def test_the_way_in_s_live_queries_and_what_re_runs_them():
    on = live_registry.subscribable
    devices = sorted({events.DEVICE_MODE_CHANGED, events.DEVICE_RENAMED, events.DEVICE_REMOVED, events.DEVICES_PRUNED})
    assert on["base.access.faces"] == sorted(
        {events.PIN_SET, events.HUB_STATE_APPLIED, events.ACCESS_SETTINGS_CHANGED, *devices, events.PROFILE_UPDATED}
        # APP-BASE-5: a PIN that whoever runs the business takes away leaves the grid too.
        | {events.PERSON_PIN_REMOVED}
    )
    assert on["base.device.list"] == devices
    assert on["base.device.current"] == sorted({events.DEVICE_MODE_CHANGED, events.DEVICE_REMOVED, events.DEVICES_PRUNED})
    assert on["base.access.settings"] == [events.ACCESS_SETTINGS_CHANGED]
    assert on["base.profile.get"] == sorted({events.PROFILE_UPDATED, events.PIN_SET, events.ACCESS_SETTINGS_CHANGED})


class FakeRequest:
    def __init__(self, token=""):
        self.COOKIES = {access.DEVICE_COOKIE: token} if token else {}
        self.META = {"REMOTE_ADDR": "127.0.0.1"}


def test_the_grid_of_switch_user_is_the_door_s_for_a_member_of_the_hub(make_user):
    ana = make_user("saas:1", host="a", role=Membership.Role.EMPLOYEE, first_name="Ana")
    Credential.objects.create(username=ana.username, pin_hash=make_password("4826", hasher="argon2"))
    token = access.new_device_token()
    TrustedDevice.objects.create(token_digest=access.token_digest(token), last_entry_at=timezone.now())
    faces = get("base.access.faces")
    seen = faces(OperationContext(scope=A, actor=ana, permissions=frozenset({"base.view_home"}), request=FakeRequest(token)), AccessDoorIn())
    assert [person.name for person in seen.people] == ["Ana"]
    elsewhere = faces(OperationContext(scope=A, actor=ana, permissions=frozenset({"base.view_home"}), request=FakeRequest()), AccessDoorIn())
    assert elsewhere.people == []
    assert faces.permission == "base.view_home"


@pytest.fixture
def listen(django_db_setup):
    from django.db import connections

    params = connections["default"].settings_dict
    dsn = make_conninfo(dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"], host=params["HOST"], port=params["PORT"])
    sessions = []

    def open_session(scope):
        session = psycopg.connect(dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=1.0, stop_after=None):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


@pytest.mark.django_db(transaction=True)
def test_changing_the_dial_in_b_tells_b_only(listen):
    on_a, on_b = listen(A), listen(B)
    get("base.access.settings_update")(system_context(B), AccessSettingsUpdateIn(pin_length=6))
    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": [events.ACCESS_SETTINGS_CHANGED]})]
    assert received(on_a, timeout=0.3) == []
    assert {"base.access.faces", "base.access.settings", "base.profile.get"} <= live_registry.affected(
        [events.ACCESS_SETTINGS_CHANGED]
    )
