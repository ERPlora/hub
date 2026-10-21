"""Secrets that cannot be read again (WORKBOOK FLOW-F26; old hub HUB-F99).

A secret has a name (upper case, up to 64 characters) and a value, sealed with the server's key; from then
on only its name is shown: no route, live query, event or log gives the value back. Saving a name again
replaces its value; deleting it empties it, and a step that used it fails (FLOW-F27). Without the
server's key nothing is kept (``flow.secrets_key_missing``).
"""

import json
import logging

import pydantic
import pytest
from cryptography.fernet import Fernet
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.flow import vault
from apps.flow.models import Secret

from .conftest import ctx_for, run

pytestmark = pytest.mark.django_db

VALUE = "sk_live_51HxYz"


@pytest.fixture(autouse=True)
def key(settings):
    settings.FLOW_SECRETS_KEY = Fernet.generate_key().decode()


def test_a_secret_is_kept_sealed_and_only_its_name_comes_back(caplog):
    caplog.set_level(logging.DEBUG)
    saved = run("flow.secret.set", {"name": "STRIPE_KEY", "value": VALUE})
    dumped = saved.model_dump_json()
    assert saved.name == "STRIPE_KEY" and VALUE not in dumped
    kept = Secret.objects.get()
    assert VALUE not in kept.ciphertext and vault.open_value(kept.ciphertext) == VALUE
    events = [(event.name, event.payload) for event in OutboxEvent.objects.filter(name__startswith="flow.secret.")]
    assert events == [("flow.secret.saved", {"id": str(kept.id)})]
    listed = run("flow.secret.list", {})
    assert [row.name for row in listed.rows] == ["STRIPE_KEY"] and listed.available is True
    assert VALUE not in listed.model_dump_json()
    assert VALUE not in caplog.text


def test_saving_a_name_again_replaces_its_value():
    run("flow.secret.set", {"name": "API_TOKEN", "value": "first"})
    first = Secret.objects.get().ciphertext
    run("flow.secret.set", {"name": "API_TOKEN", "value": "second"}, ctx_for(actor="ana"))
    kept = Secret.objects.get()
    assert kept.ciphertext != first and vault.open_value(kept.ciphertext) == "second"
    assert (kept.created_by, kept.updated_by) == ("tester", "ana")


def test_a_name_is_upper_case_and_a_value_is_not_empty():
    for name in ("stripe", "1KEY", "KEY-1", "K" * 65, ""):
        with pytest.raises(pydantic.ValidationError):
            run("flow.secret.set", {"name": name, "value": VALUE})
    with pytest.raises(pydantic.ValidationError) as empty:
        run("flow.secret.set", {"name": "KEY", "value": ""})
    assert "value" in str(empty.value) and VALUE not in str(empty.value)
    assert Secret.objects.count() == 0


def test_a_refused_value_is_never_echoed():
    with pytest.raises(pydantic.ValidationError) as long:
        run("flow.secret.set", {"name": "KEY", "value": "sk_" + "x" * 5000})
    assert "sk_xxx" not in str(long.value)


def test_without_the_servers_key_nothing_is_kept(settings):
    settings.FLOW_SECRETS_KEY = ""
    with pytest.raises(Conflict) as refused:
        run("flow.secret.set", {"name": "KEY", "value": VALUE})
    assert refused.value.code == "flow.secrets_key_missing"
    assert Secret.objects.count() == 0
    assert run("flow.secret.list", {}).available is False


def test_deleting_a_secret_forgets_it():
    run("flow.secret.set", {"name": "KEY", "value": VALUE})
    kept = Secret.objects.get()
    run("flow.secret.delete", {"name": "KEY"})
    assert Secret.objects.count() == 0
    assert OutboxEvent.objects.filter(name="flow.secret.deleted", payload={"id": str(kept.id)}).count() == 1
    with pytest.raises(NotFound):
        run("flow.secret.delete", {"name": "KEY"})


def test_only_who_manages_automations_touches_secrets():
    viewer = ctx_for(permissions={"flow.view"})
    with pytest.raises(PermissionDenied):
        run("flow.secret.set", {"name": "KEY", "value": VALUE}, viewer)
    with pytest.raises(PermissionDenied):
        run("flow.secret.list", {}, viewer)
    with pytest.raises(PermissionDenied):
        run("flow.secret.delete", {"name": "KEY"}, viewer)


def test_the_route_never_gives_the_value_back(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_owner"))
    answer = client.post(
        "/api/flow/secrets",
        json.dumps({"name": "KEY", "value": VALUE}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
    )
    assert answer.status_code == 200, answer.content
    assert VALUE.encode() not in answer.content
    listed = client.get("/api/flow/secrets", HTTP_HOST="a.localhost")
    assert listed.status_code == 200 and VALUE.encode() not in listed.content
    assert json.loads(listed.content)["rows"][0]["name"] == "KEY"
