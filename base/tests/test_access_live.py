"""The way in's live queries: what re-runs them, and a change in hub B never reaches A.

The grid of «Switch user» (``base.access.faces``) is the door's, for a session: it follows the PINs being chosen, the
SaaS's photo (people come and go), the business's dial and the devices, so somebody who gets a PIN shows up without
reloading and somebody removed leaves the grid.

Each business is on a database of its own (``hub_a``, ``hub_b``) and its operations run inside its context.
"""

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from live.context import OperationContext, Scope, system_context
from live.live_registry import live_registry
from live.operations import get
from live.outbox import channel_for

from base import access, events
from base.models import Credential, Membership, TrustedDevice
from base.schemas.access import AccessDoorIn, AccessSettingsUpdateIn
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_auth_views import ON_HUB_A
from base.tests.test_auth_views import A as SLUG_A
from base.tests.test_auth_views import B as SLUG_B
from base.tests.test_queries_home import listen, received  # noqa: F401 (listen: a fixture)

pytestmark = ON_HUB_A

A, B = Scope("host", SLUG_A), Scope("host", SLUG_B)


def test_the_way_in_s_live_queries_and_what_re_runs_them():
    on = live_registry.subscribable
    devices = sorted({events.DEVICE_MODE_CHANGED, events.DEVICE_RENAMED, events.DEVICE_REMOVED, events.DEVICES_PRUNED})
    assert on["base.access.faces"] == sorted(
        {events.PIN_SET, events.HUB_STATE_APPLIED, events.ACCESS_SETTINGS_CHANGED, *devices, events.PROFILE_UPDATED}
        # A PIN that whoever runs the business takes away leaves the grid too.
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


def test_the_grid_of_switch_user_is_the_door_s_for_a_member_of_the_hub(make_user, hub_a):
    ana = make_user("saas:1", host=SLUG_A, role=Membership.Role.EMPLOYEE, first_name="Ana")
    token = access.new_device_token()
    faces = get("base.access.faces")
    with use_hub(hub_a):
        Credential.objects.create(username=ana.username, pin_hash=make_password("4826", hasher="argon2"))
        TrustedDevice.objects.create(token_digest=access.token_digest(token), last_entry_at=timezone.now())
        seen = faces(OperationContext(scope=A, actor=ana, permissions=frozenset({"base.view_home"}), request=FakeRequest(token)), AccessDoorIn())
        elsewhere = faces(OperationContext(scope=A, actor=ana, permissions=frozenset({"base.view_home"}), request=FakeRequest()), AccessDoorIn())
    assert [person.name for person in seen.people] == ["Ana"]
    assert elsewhere.people == []
    assert faces.permission == "base.view_home"


@pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)
def test_changing_the_dial_in_b_tells_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        get("base.access.settings_update")(system_context(B), AccessSettingsUpdateIn(pin_length=6))
    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": [events.ACCESS_SETTINGS_CHANGED]})]
    assert received(on_a, timeout=0.3) == []
    assert {"base.access.faces", "base.access.settings", "base.profile.get"} <= live_registry.affected(
        [events.ACCESS_SETTINGS_CHANGED]
    )
