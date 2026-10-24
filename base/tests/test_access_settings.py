"""BASE-G62 and G151: how the business asks who is at the till (Settings › General, «PIN pad»).

«Show the PIN pad» on or off (``never``), «Ask again after inactivity» (1, 5, 10, 15 or 30 minutes: ``always``; «Until
signing out»: ``per_shift``, the factory value) and «PIN digits» (4 or 6). Each control is saved on its own and the
card shows what the Hub confirmed. A stored value that is not understood reads as the factory one, never as «not
asking»; the PINs of the other length keep working until their owners change them.
"""

import json

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from live.models import OutboxEvent

from base import access
from base.models import AccessSettings, Credential, Membership, TrustedDevice

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"


def read(client):
    response = client.get("/api/access/settings", HTTP_HOST=HOST)
    assert response.status_code == 200, response.content
    return response.json()


def change(client, **body):
    return client.post("/api/access/settings/update", json.dumps(body), content_type="application/json", HTTP_HOST=HOST)


@pytest.fixture
def owner(client, make_user):
    user = make_user("saas:1", host="a", role=Membership.Role.OWNER, first_name="Olga")
    client.force_login(user)
    return user


@pytest.fixture
def employee(client, make_user):
    user = make_user("saas:2", host="a", role=Membership.Role.EMPLOYEE)
    client.force_login(user)
    return user


def test_without_a_row_the_factory_values(client, owner):
    assert read(client) == {"pin_policy": "per_shift", "pin_inactivity_minutes": 5, "pin_length": 4, "can_change": True}


def test_everyone_reads_it_and_only_an_administrator_changes_it(client, employee):
    assert read(client)["can_change"] is False
    assert change(client, pin_policy="never").status_code == 403
    assert not AccessSettings.objects.exists()


def test_each_control_is_saved_on_its_own_and_the_answer_is_what_was_confirmed(client, owner):
    answer = change(client, pin_policy="always", pin_inactivity_minutes=15)
    assert answer.status_code == 200
    assert answer.json() == {"pin_policy": "always", "pin_inactivity_minutes": 15, "pin_length": 4, "can_change": True}
    change(client, pin_length=6)
    row = AccessSettings.objects.get()
    assert (row.pin_policy, row.pin_inactivity_minutes, row.pin_length, row.updated_by) == ("always", 15, 6, "Olga")
    assert OutboxEvent.objects.filter(name="base.access.settings_changed").count() == 2


@pytest.mark.parametrize("body", [{"pin_policy": "sometimes"}, {"pin_inactivity_minutes": 7}, {"pin_length": 5}, {}])
def test_a_value_out_of_the_controls_is_refused(client, owner, body):
    assert change(client, **body).status_code == 422
    assert not AccessSettings.objects.exists()


def test_a_stored_value_it_does_not_understand_reads_as_the_factory_one(client, owner):
    AccessSettings.objects.create()
    AccessSettings.objects.update(pin_policy="per_shift")
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE base_accesssettings DROP CONSTRAINT base_accesssettings_policy")
        cursor.execute("UPDATE base_accesssettings SET pin_policy = 'sometimes'")
    assert read(client)["pin_policy"] == "per_shift"


def test_a_pin_of_the_other_length_keeps_working_until_its_owner_changes_it(client, owner, make_user):
    ana = make_user("saas:3", host="a", first_name="Ana")
    credential = Credential.objects.create(username=ana.username, pin_hash=make_password("4826", hasher="argon2"))
    change(client, pin_length=6)
    token = access.new_device_token()
    TrustedDevice.objects.create(token_digest=access.token_digest(token), last_entry_at=timezone.now())
    anonymous = type(client)()
    anonymous.cookies[access.DEVICE_COOKIE] = token
    body = json.dumps({"person": str(credential.pk), "pin": "4826", "next": "/"})
    assert anonymous.post("/auth/pin", body, content_type="application/json", HTTP_HOST=HOST).status_code == 200
