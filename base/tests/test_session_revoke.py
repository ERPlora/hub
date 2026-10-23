"""The SaaS ends a person's sessions in the Hub: ``POST /internal/sessions/revoke {user_id, hub_id?}`` (PLAN-SAAS §2.1,
the back-channel logout of OIDC; PLAN-HUB «Admin»: without a hub it ends the admin's sessions of that account too).

The SaaS sends it after removing a member, changing their role or handing a business over (with the business's id),
and after a password change, «sign out everywhere» or deleting the account (without it): HUBS-F26, HUBS-F27 and
HUBS-F28 of the SaaS. Every login notes whose and where its session is (``base.SessionOwner``: the SaaS account and the
host the login noted), so the door ends exactly those sessions through that index, never decoding the sessions of the
table. An open ``/api/live`` stream of an ended session gets no more results: its next re-run ends it with ``bye``,
and the door wakes the hub's open apps after the COMMIT so that re-run comes now.
"""

import json

import psycopg
import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.base import SessionBase
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.sessions.models import Session
from django.db import close_old_connections, connections
from django.test import RequestFactory
from live.context import Scope
from live.executor import BYE_FRAME, Stream, Subscription, executor
from live.operations import get
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from base.auth import PLATFORM_ADMIN, RedeemedUser
from base.middleware import PLATFORM_SESSION_HOST
from base.models import Hub, Membership, SessionOwner
from base.operations import HubContextBuilder
from base.services import open_admin_session_from_saas, open_session_from_saas
from base.tests.test_internal import code, signed

REVOKE = "/internal/sessions/revoke"
ANA = "0199c4b0-0000-7000-8000-00000000a0a0"
OLGA = "0199c4b0-0000-7000-8000-00000000b0b0"
ACME_ID = "0199c4b0-0000-7000-8000-0000000000a1"
BETA_ID = "0199c4b0-0000-7000-8000-0000000000a2"
UNKNOWN_ID = "0199c4b0-0000-7000-8000-0000000000ff"


@pytest.fixture
def acme(db):
    return Hub.objects.create(id=ACME_ID, slug="acme", status="ready")


@pytest.fixture
def beta(db):
    return Hub.objects.create(id=BETA_ID, slug="beta", status="ready")


def login(saas_id: str, hub: Hub | None = None, role: str = "hub_employee") -> str:
    """A session opened as ``/auth/callback`` opens it: on ``hub``'s host for a member, or on the platform host for
    the staff (``hub=None``); its key."""
    host = f"{hub.slug}.localhost:8000" if hub else "hubs.localhost:8000"
    request = RequestFactory().post("/auth/callback", HTTP_HOST=host)
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request.user = AnonymousUser()
    redeemed = RedeemedUser(user_id=saas_id, email=f"{saas_id[-4:]}@example.com", name="Ana", locale="es", role=role)
    if hub is None:
        request.platform_host = True
        open_admin_session_from_saas(request, RedeemedUser(**{**redeemed.__dict__, "role": PLATFORM_ADMIN}))
    else:
        request.hub = hub
        open_session_from_saas(request, redeemed, hub.slug)
    request.session.save()
    return request.session.session_key


def alive(key: str) -> bool:
    return Session.objects.filter(session_key=key).exists()


@pytest.mark.django_db
class TestTheIndex:
    def test_every_login_notes_whose_and_where_its_session_is(self, acme):
        member = login(ANA, acme)
        staff = login(ANA)

        assert set(SessionOwner.objects.values_list("session_id", "saas_user_id", "host")) == {
            (member, ANA, "acme"),
            (staff, ANA, PLATFORM_SESSION_HOST),
        }

    def test_a_session_that_ends_takes_its_note_with_it(self, acme):
        key = login(ANA, acme)

        Session.objects.filter(session_key=key).delete()  # a logout, or clearsessions of an expired one

        assert not SessionOwner.objects.exists()


@pytest.mark.django_db
class TestTheDoor:
    def test_with_a_business_it_ends_that_account_s_sessions_there_and_nowhere_else(self, client, acme, beta):
        on_acme, again_on_acme, on_beta, staff = login(ANA, acme), login(ANA, acme), login(ANA, beta), login(ANA)
        olga_on_acme = login(OLGA, acme)

        answer = signed(client, "post", REVOKE, {"user_id": ANA, "hub_id": ACME_ID})

        assert (answer.status_code, answer.json()) == (200, {"ended": 2})
        assert not alive(on_acme) and not alive(again_on_acme)
        assert alive(on_beta) and alive(staff) and alive(olga_on_acme)

    def test_without_a_business_it_ends_every_session_of_the_account_the_admin_s_too(self, client, acme, beta):
        keys = [login(ANA, acme), login(ANA, beta), login(ANA)]
        olga = login(OLGA, acme)

        answer = signed(client, "post", REVOKE, {"user_id": ANA})

        assert (answer.status_code, answer.json()) == (200, {"ended": 3})
        assert not any(alive(key) for key in keys)
        assert alive(olga)
        assert set(SessionOwner.objects.values_list("saas_user_id", flat=True)) == {OLGA}

    def test_twice_is_the_same_answer_with_nothing_left_to_end(self, client, acme):
        login(ANA, acme)

        first = signed(client, "post", REVOKE, {"user_id": ANA, "hub_id": ACME_ID})
        second = signed(client, "post", REVOKE, {"user_id": ANA, "hub_id": ACME_ID})

        assert (first.status_code, first.json(), second.status_code, second.json()) == (200, {"ended": 1}, 200, {"ended": 0})

    def test_an_unknown_business_answers_like_a_known_one_without_sessions(self, client, acme):
        on_acme = login(ANA, acme)

        unknown = signed(client, "post", REVOKE, {"user_id": ANA, "hub_id": UNKNOWN_ID})
        known_but_empty = signed(client, "post", REVOKE, {"user_id": OLGA, "hub_id": ACME_ID})

        assert (unknown.status_code, unknown.json()) == (known_but_empty.status_code, known_but_empty.json()) == (200, {"ended": 0})
        assert alive(on_acme)

    def test_it_never_decodes_the_sessions_of_the_table(self, client, acme, monkeypatch):
        on_acme = login(ANA, acme)

        def decoding(self, data):
            raise AssertionError("the door decoded a session")

        monkeypatch.setattr(SessionBase, "decode", decoding)
        answer = signed(client, "post", REVOKE, {"user_id": ANA})

        assert answer.status_code == 200 and not alive(on_acme)

    @pytest.mark.parametrize(
        "raw",
        [
            b"not json",
            b"[]",
            json.dumps({}).encode(),
            json.dumps({"user_id": "not-an-id"}).encode(),
            json.dumps({"user_id": ANA, "hub_id": "not-an-id"}).encode(),
        ],
        ids=["not-json", "array", "no-user", "bad-user", "bad-hub"],
    )
    def test_a_body_out_of_contract_is_422_and_ends_nothing(self, client, acme, raw):
        on_acme = login(ANA, acme)

        answer = signed(client, "post", REVOKE, raw)

        assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"
        assert alive(on_acme)

    def test_an_unsigned_call_is_401_and_ends_nothing(self, client, acme):
        on_acme = login(ANA, acme)

        answer = client.post(REVOKE, {"user_id": ANA}, content_type="application/json", HTTP_HOST="hubs.localhost")

        assert answer.status_code == 401 and code(answer) == "internal.unsigned"
        assert alive(on_acme)

    def test_only_post(self, client, db):
        assert signed(client, "get", REVOKE, b"").status_code == 405


# ── The open apps of an ended session ─────────────────────────────────────────────────────────────────────────────


async def in_db(fn, *args, **kwargs):
    def call():
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return await sync_to_async(call)()


def open_stream(saas_id: str, hub: Hub) -> Stream:
    """The ``/api/live`` stream a member of ``hub`` opens with the session of its login: ``demo.item.list``."""
    key = login(saas_id, hub, role="hub_owner")
    request = RequestFactory().get("/api/live", HTTP_HOST=f"{hub.slug}.localhost")
    SessionMiddleware(lambda r: None).process_request(request)
    request.session = request.session.__class__(key)
    request.user = Membership.objects.get(user__username=f"saas:{saas_id}", host=hub.slug).user
    request.LANGUAGE_CODE = "en"
    stream = Stream(HubContextBuilder().from_request(request))
    op = get("demo.item.list")
    stream.subs["items"] = Subscription(id="items", op=op, params=op.input.model_validate({}))
    return stream


@pytest.fixture
def fresh_executor():
    executor.reset()
    yield
    executor.reset()


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("fresh_executor")
class TestTheOpenApps:
    async def test_the_stream_of_an_ended_session_ends_without_a_result(self, client):
        hub = await in_db(Hub.objects.create, id=ACME_ID, slug="acme", status="ready")
        stream = await in_db(open_stream, ANA, hub)
        await executor.run_all(stream)
        assert b"event: result" in stream.queue.get_nowait()

        answer = await in_db(signed, client, "post", REVOKE, {"user_id": ANA, "hub_id": ACME_ID})
        await executor.run_all(stream)

        assert answer.status_code == 200
        assert stream.closed
        assert stream.queue.get_nowait() == BYE_FRAME
        assert stream.queue.empty()

    async def test_the_stream_of_another_account_goes_on(self, client):
        hub = await in_db(Hub.objects.create, id=ACME_ID, slug="acme", status="ready")
        stream = await in_db(open_stream, OLGA, hub)
        await executor.run_all(stream)
        stream.queue.get_nowait()

        await in_db(signed, client, "post", REVOKE, {"user_id": ANA, "hub_id": ACME_ID})
        await executor.run_all(stream)

        assert not stream.closed
        assert stream.queue.empty()  # the same result: nothing new to send

    def test_the_door_wakes_the_hub_s_open_apps_after_the_commit(self, client):
        Hub.objects.create(id=ACME_ID, slug="acme", status="ready")
        login(ANA, Hub.objects.get(pk=ACME_ID))
        params = connections["default"].settings_dict
        dsn = make_conninfo(
            dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"], host=params["HOST"], port=params["PORT"]
        )
        with psycopg.connect(dsn, autocommit=True) as listener:
            listener.execute(f"LISTEN {channel_for(Scope('host', 'acme'))}")

            signed(client, "post", REVOKE, {"user_id": ANA, "hub_id": ACME_ID})

            heard = {name for note in listener.notifies(timeout=1.0) for name in json.loads(note.payload)["events"]}
        assert "*" in heard
