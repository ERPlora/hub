"""erplora.com's WhatsApp doors into the Hub (``apps/whatsapp_inbox/WORKBOOK.md``, «Contrato con el SaaS», doors 1–4).

Three doors under ``/internal/whatsapp/``, signed as the rest of ``/internal``, each the system operation of the inbox
on the business the body names (``hub``: its slug in phase 1): ``POST …/inbound`` → ``whatsapp_inbox.message.receive``
(200 ``{id, conversation_id, created}``; the same WhatsApp id again is ``created: false``), ``POST …/status`` →
``whatsapp_inbox.message.update_status`` (200 ``{updated, status}``) and ``PUT …/channel`` →
``whatsapp_inbox.channel.sync`` (200 ``{applied, version}``). A business the registry does not know is 404, one that
does not open answers as its host does (410 gone, 503 being prepared, 402 suspended), the app off in it is 404
``app_inactive`` (erplora.com keeps the message and tries again) and a body out of contract 422. The photo
(``PUT /internal/hubs/{id}/state``) carries the same channel state under ``whatsapp`` (door 4), applied with the
photo's own version.
"""

import json
import time

import psycopg
import pytest
from django.db import connections
from live.context import Scope, system_context
from live.errors import OperationError
from live.models import OutboxEvent
from live.operations import get as get_operation
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from apps.whatsapp_inbox.models import Channel, Message
from base import relay
from base.models import Hub
from base.tests.test_internal import HUB_ID, PATH as STATE_PATH, SECRET, code, signed

INBOUND = "/internal/whatsapp/inbound"
STATUS = "/internal/whatsapp/status"
CHANNEL = "/internal/whatsapp/channel"
ACME = Scope("host", "acme")
OTHER = Scope("host", "other")


@pytest.fixture(autouse=True)
def secret(settings):
    settings.INTERNAL_SHARED_SECRET = SECRET
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""


@pytest.fixture
def acme(db, every_app_on):
    """A business with WhatsApp on (a new one is born with every app off, round 2026-10-27)."""
    hub = Hub.objects.create(id=HUB_ID, slug="acme", status="ready")
    every_app_on("acme")
    return hub


@pytest.fixture
def other(db, every_app_on):
    hub = Hub.objects.create(id="0199c4b0-0000-7000-8000-000000000002", slug="other", status="ready")
    every_app_on("other")
    return hub


def message(wa_id: str = "wamid.1", hub: str = "acme", **fields) -> dict:
    """What erplora.com sends to ``/internal/whatsapp/inbound`` for a customer's text (door 1)."""
    return {
        "hub": hub,
        "wa_message_id": wa_id,
        "from": "34600111222",
        "contact_name": "Ana",
        "direction": "inbound",
        "source": "live",
        "type": "text",
        "text": "Hola, ¿tenéis hora mañana?",
        "reply_to": "",
        "reply": None,
        "sent_at": "2026-10-15T10:00:00Z",
        "payload": {"id": wa_id},
        **fields,
    }


def channel_state(version: int = 42, **fields) -> dict:
    """The number's state as erplora.com reports it (door 3 without ``hub``, the photo's ``whatsapp``)."""
    return {
        "version": version,
        "status": "connected",
        "phone_number": "+34910000000",
        "display_name": "Peluquería Ana",
        "monthly_limit": 150,
        "monthly_usage": 12,
        "usage_month": "2026-10",
        "templates": None,
        **fields,
    }


def status(wa_id: str, new: str = "read", hub: str = "acme", **fields) -> dict:
    return {"hub": hub, "wa_message_id": wa_id, "status": new, "status_at": "2026-10-15T10:00:05Z", **fields}


def post(client, path: str, body, **kwargs):
    method = "put" if path == CHANNEL else "post"
    return signed(client, method, path, body, **kwargs)


def door_body(path: str, hub: str = "acme") -> dict:
    if path == INBOUND:
        return message(hub=hub)
    if path == STATUS:
        return status("wamid.unknown", hub=hub)
    return {"hub": hub, **channel_state()}


def channel_now():
    op = get_operation("whatsapp_inbox.channel.get")
    return op(system_context(ACME), op.input.model_validate({}))


DOORS = [INBOUND, STATUS, CHANNEL]


# Door 1: a customer's message (or the echo of the owner's phone)


def test_inbound_stores_the_message_in_the_named_business(client, acme):
    answer = post(client, INBOUND, message())

    assert answer.status_code == 200
    stored = Message.objects.get(wa_message_id="wamid.1")
    assert answer.json() == {"id": str(stored.id), "conversation_id": str(stored.conversation_id), "created": True}
    assert (stored.direction, stored.body) == ("inbound", "Hola, ¿tenéis hora mañana?")
    # The operation ran on the business of the body: its event is recorded in that hub's scope.
    received = OutboxEvent.objects.get(name="whatsapp_inbox.message.received")
    assert (received.scope_kind, received.scope_key) == ("host", "acme")


def test_the_same_whatsapp_id_again_is_200_and_not_created(client, acme):
    first = post(client, INBOUND, message())
    again = post(client, INBOUND, message())

    assert again.status_code == 200
    assert again.json() == {**first.json(), "created": False}
    assert Message.objects.filter(wa_message_id="wamid.1").count() == 1


# Door 2: Meta's status of a message the Hub sent


def test_status_moves_a_message_sent_from_the_business(client, acme):
    # The echo of the owner's reply from the phone app is a message of the business, «sent».
    post(client, INBOUND, message("wamid.echo", direction="outbound"))

    answer = post(client, STATUS, status("wamid.echo", "read"))

    assert answer.status_code == 200 and answer.json() == {"updated": True, "status": "read"}
    assert Message.objects.get(wa_message_id="wamid.echo").status == "read"


def test_the_status_of_an_unknown_message_is_200_and_not_updated(client, acme):
    answer = post(client, STATUS, status("wamid.unknown", "delivered"))

    assert answer.status_code == 200 and answer.json() == {"updated": False, "status": None}


# Door 3: the number, its month and its templates


def test_channel_applies_the_numbers_state(client, acme):
    answer = post(client, CHANNEL, {"hub": "acme", **channel_state(42)})

    assert answer.status_code == 200 and answer.json() == {"applied": True, "version": 42}
    shown = channel_now()
    assert (shown.status, shown.phone_number, shown.monthly_limit) == ("connected", "+34910000000", 150)


def test_an_older_channel_state_is_not_applied(client, acme):
    post(client, CHANNEL, {"hub": "acme", **channel_state(42)})

    answer = post(client, CHANNEL, {"hub": "acme", **channel_state(41, status="reconnect_needed")})

    assert answer.status_code == 200 and answer.json() == {"applied": False, "version": 42}
    assert channel_now().status == "connected"


def test_channel_is_only_put(client, acme):
    answer = signed(client, "post", CHANNEL, {"hub": "acme", **channel_state()})
    assert answer.status_code == 405


@pytest.mark.parametrize("path", [INBOUND, STATUS])
def test_inbound_and_status_are_only_posted(client, acme, path):
    assert signed(client, "put", path, door_body(path)).status_code == 405


# The signature: every door, as the rest of /internal


@pytest.mark.parametrize("path", DOORS)
def test_an_unsigned_call_is_401(client, acme, path):
    method = "put" if path == CHANNEL else "post"
    raw = json.dumps(door_body(path)).encode()
    answer = getattr(client, method)(path, raw, content_type="application/json", HTTP_HOST="hubs.localhost")

    assert answer.status_code == 401 and code(answer) == "internal.unsigned"
    assert not Message.objects.exists() and not Channel.objects.exists()


@pytest.mark.parametrize("path", DOORS)
def test_another_secret_or_a_stale_timestamp_is_401(client, acme, path):
    assert post(client, path, door_body(path), secret="other").status_code == 401
    assert post(client, path, door_body(path), ts=int(time.time()) - 400).status_code == 401
    assert not Message.objects.exists() and not Channel.objects.exists()


@pytest.mark.parametrize("path", DOORS)
def test_a_v2_signature_binds_the_door(client, acme, path):
    # Signed for one door, replayed on another: refused.
    body = door_body(path)
    other_door = INBOUND if path != INBOUND else STATUS
    answer = post(client, path, body, with_v1=False, with_v2=True, v2_path=other_door)
    assert answer.status_code == 401


# The business the body names


@pytest.mark.parametrize("path", DOORS)
def test_a_business_the_registry_does_not_know_is_404(client, acme, path):
    answer = post(client, path, door_body(path, hub="nobody"))

    assert answer.status_code == 404 and code(answer) == "not_found"
    assert not Message.objects.exists() and not Channel.objects.exists()


@pytest.mark.parametrize("path", DOORS)
@pytest.mark.parametrize("hub", [None, "", 7, ["acme"]])
def test_a_body_without_a_business_is_422(client, acme, path, hub):
    body = door_body(path)
    if hub is None:
        body.pop("hub")
    else:
        body["hub"] = hub

    answer = post(client, path, body)

    assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"
    assert "hub" in answer.json()["error"]["fields"]


@pytest.mark.parametrize(
    ("change", "status_code", "error"),
    [
        ({"status": "cancelled"}, 410, "base.hub_gone"),
        ({"status": "requested"}, 503, "base.hub_preparing"),
        ({"state": {"status": "suspended"}}, 402, "base.hub_suspended"),
    ],
)
@pytest.mark.parametrize("path", DOORS)
def test_a_business_that_does_not_open_answers_as_its_host(client, acme, path, change, status_code, error):
    Hub.objects.filter(id=acme.id).update(**change)

    answer = post(client, path, door_body(path))

    assert answer.status_code == status_code and code(answer) == error
    assert not Message.objects.exists() and not Channel.objects.exists()


# The app in that business


@pytest.mark.parametrize("path", DOORS)
def test_the_app_off_in_the_business_is_404_app_inactive(client, acme, path, monkeypatch):
    every = relay.active_apps(ACME)
    monkeypatch.setattr(relay, "active_apps", lambda scope: every - {"whatsapp_inbox"})

    answer = post(client, path, door_body(path))

    assert answer.status_code == 404 and code(answer) == "app_inactive"
    assert not Message.objects.exists() and not Channel.objects.exists()


def test_the_app_is_asked_about_the_business_of_the_body(client, acme, other, monkeypatch):
    every = relay.active_apps(ACME)
    asked = []

    def active(scope):
        asked.append(scope)
        return every if scope == ACME else every - {"whatsapp_inbox"}

    monkeypatch.setattr(relay, "active_apps", active)

    assert post(client, INBOUND, message(hub="other")).status_code == 404
    assert post(client, INBOUND, message(hub="acme")).status_code == 200
    assert asked == [OTHER, ACME]


@pytest.mark.parametrize("path", DOORS)
def test_the_refusal_of_the_operation_reaches_erplora_as_it_is(client, acme, path, monkeypatch):
    # Whatever ``@operation`` refuses (an app without the right to run, 402) is answered with its own envelope.
    name = {
        INBOUND: "whatsapp_inbox.message.receive",
        STATUS: "whatsapp_inbox.message.update_status",
        CHANNEL: "whatsapp_inbox.channel.sync",
    }[path]

    def blocked(ctx, data):
        raise OperationError("WhatsApp is not in this plan.", code="app_entitlement_blocked", status=402)

    monkeypatch.setattr(get_operation(name), "fn", blocked)

    answer = post(client, path, door_body(path))

    assert answer.status_code == 402
    assert answer.json() == {"error": {"code": "app_entitlement_blocked", "message": "WhatsApp is not in this plan."}}


# The body


@pytest.mark.parametrize("path", DOORS)
@pytest.mark.parametrize("raw", [b"not json", b"[]", b""])
def test_a_body_that_is_no_object_is_422(client, acme, path, raw):
    answer = post(client, path, raw)
    assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"


@pytest.mark.parametrize(
    ("path", "body", "field"),
    [
        (INBOUND, message(wa_message_id=""), "wa_message_id"),
        (INBOUND, message(direction="sideways"), "direction"),
        (INBOUND, message(media={"url": "https://elsewhere.example/x.jpg"}), "media.url"),
        (STATUS, status("wamid.1", "seen"), "status"),
        (CHANNEL, {"hub": "acme", **channel_state(-1)}, "version"),
        (CHANNEL, {"hub": "acme", **channel_state(status="maybe")}, "status"),
    ],
)
def test_fields_out_of_contract_are_422_with_their_field(client, acme, path, body, field):
    answer = post(client, path, body)

    assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"
    assert field in answer.json()["error"]["fields"]
    assert not Message.objects.exists() and not Channel.objects.exists()


def test_a_number_that_is_no_number_is_422(client, acme):
    answer = post(client, INBOUND, message(**{"from": "0000"}))

    assert answer.status_code == 422 and "from" in answer.json()["error"]["fields"]
    assert not Message.objects.exists()


# Door 4: the photo's ``whatsapp``


def photo(version: int, **fields) -> dict:
    return {"hub_id": HUB_ID, "slug": "acme", "version": version, "status": "active", **fields}


def test_the_photo_applies_its_whatsapp_with_its_own_version(client, acme):
    # The block carries no version of its own that counts: the photo's is the channel's.
    answer = signed(client, "put", STATE_PATH, photo(7, whatsapp={**channel_state(1), "display_name": "Ana"}))

    assert answer.status_code == 200 and answer.json() == {"applied": True, "version": 7}
    assert Channel.objects.get().version == 7
    shown = channel_now()
    assert (shown.status, shown.display_name) == ("connected", "Ana")


def test_a_photo_without_whatsapp_leaves_the_channel_alone(client, acme):
    post(client, CHANNEL, {"hub": "acme", **channel_state(3)})

    answer = signed(client, "put", STATE_PATH, photo(9))

    assert answer.json() == {"applied": True, "version": 9}
    assert Channel.objects.get().version == 3


def test_an_older_photo_does_not_apply_its_whatsapp(client, acme):
    signed(client, "put", STATE_PATH, photo(7, whatsapp=channel_state()))

    answer = signed(client, "put", STATE_PATH, photo(6, whatsapp=channel_state(status="reconnect_needed")))

    assert answer.json() == {"applied": False, "version": 7}
    assert channel_now().status == "connected"


def test_with_the_app_off_the_photo_applies_and_its_whatsapp_is_ignored(client, acme, monkeypatch):
    every = relay.active_apps(ACME)
    monkeypatch.setattr(relay, "active_apps", lambda scope: every - {"whatsapp_inbox"})

    answer = signed(client, "put", STATE_PATH, photo(5, whatsapp=channel_state()))

    assert answer.status_code == 200 and answer.json() == {"applied": True, "version": 5}
    acme.refresh_from_db()
    assert acme.state_version == 5
    assert not Channel.objects.exists()


@pytest.mark.parametrize(
    "block",
    [[], "connected", {**channel_state(), "status": "maybe"}, {**channel_state(), "monthly_limit": -1}],
)
def test_a_whatsapp_out_of_contract_keeps_nothing_of_the_photo(client, acme, block):
    # As its VeriFactu block: the SaaS hears 422 and the photo is kept by none of its parts.
    answer = signed(client, "put", STATE_PATH, photo(5, whatsapp=block))

    assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"
    acme.refresh_from_db()
    assert (acme.state, acme.state_version) == ({}, 0)
    assert not Channel.objects.exists()


# Two businesses: a write in one never reaches the other


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
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}


@pytest.mark.django_db(transaction=True)
def test_a_message_for_one_business_tells_only_that_business(client, acme, other, listening):
    on_acme, on_other = listening(ACME), listening(OTHER)

    assert post(client, INBOUND, message(hub="other")).status_code == 200

    assert "whatsapp_inbox.message.received" in heard(on_other)
    assert heard(on_acme, timeout=0.5) == set()
    assert set(OutboxEvent.objects.values_list("scope_key", flat=True)) == {"other"}


@pytest.mark.django_db(transaction=True)
def test_the_photos_whatsapp_tells_the_business_of_the_photo_after_its_commit(client, acme, other, listening):
    on_acme, on_other = listening(ACME), listening(OTHER)

    assert signed(client, "put", STATE_PATH, photo(4, whatsapp=channel_state())).json()["applied"] is True

    assert "whatsapp_inbox.channel.synced" in heard(on_acme)
    assert heard(on_other, timeout=0.5) == set()
