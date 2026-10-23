"""The SaaS's door into the Hub (PLAN-SAAS §2, §2.2): ``/internal`` calls signed with HMAC-SHA256 and a timestamp.

A call is heard by its v2 signature when it carries one (method, path and body; v2 alone decides), else by its v1
(the body only), within five minutes and with the current secret or, during a rotation, the previous one. The
signature is the authentication: the ALB never publishes ``/internal``, so the door answers on any host (the
SaaS reaches it by the private name).

The demos (§1.5, §1.6): ``POST /internal/demos`` gives a browser of the SaaS its demo (201 new, 200 its live one, 503
``base.demo_full`` with ``Retry-After`` at the cap) and ``POST /internal/demos/{slug}/codes`` a one-time code into it
for that browser only (201; 403 another browser's, 410 once it ended, 404 none), as the SaaS's ``hub_client`` reads them.

The registry (plan 2026-10-17, §1.5): ``PUT /internal/hubs/{id}`` registers a business (202, ready at once in phase 1,
and the SaaS hears ``ready`` after the COMMIT; 200 when it updates it), ``GET`` reads it, ``DELETE`` cancels it and
``POST …/restore`` brings it back. ``PUT …/state`` (the photo) keeps it on the registry's row, by the path's id, and
applies its VeriFactu block and the business's status through ``verifactu.config.sync`` on the hub's slug.
"""

import hashlib
import hmac
import json
import re
import time

import pytest

from django.test import Client
from django.utils.dateparse import parse_datetime

from apps.verifactu.models import Config
from base.models import DemoCode, Hub
from base.signing import verify_signed

HUB_ID = "0199c4b0-0000-7000-8000-000000000001"
PATH = f"/internal/hubs/{HUB_ID}/state"
SECRET = "local-internal-shared-secret"
APPROVED = {"status": "approved", "updated_at": "2026-10-15T10:00:00Z", "reason": ""}


def v1(raw: bytes, ts: str, secret: str = SECRET) -> str:
    return hmac.new(
        secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256
    ).hexdigest()


def v2(method: str, path: str, raw: bytes, ts: str, secret: str = SECRET) -> str:
    message = f"v2\n{ts}\n{method.upper()}\n{path}\n".encode() + raw
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signed(
    client,
    method,
    path,
    body,
    secret=SECRET,
    ts=None,
    host="hubs.localhost",
    v2_path=None,
    with_v1=True,
    with_v2=False,
    v2_secret=None,
    **meta,
):
    """``method`` on ``path`` with ``body`` (a dict, or raw bytes), signed as the SaaS signs it (more ``meta``)."""
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    ts = str(ts or int(time.time()))
    headers = {"HTTP_X_ERPLORA_TIMESTAMP": ts, "HTTP_HOST": host, **meta}
    if with_v1:
        headers["HTTP_X_ERPLORA_SIGNATURE"] = v1(raw, ts, secret)
    if with_v2:
        headers["HTTP_X_ERPLORA_SIGNATURE_V2"] = v2(
            method, v2_path or path, raw, ts, v2_secret or secret
        )
    return getattr(client, method)(
        path, raw, content_type="application/json", **headers
    )


def code(answer) -> str:
    return answer.json()["error"]["code"]


@pytest.fixture(autouse=True)
def registered(request):
    """The business of ``HUB_ID`` in the registry (``acme``), for the tests that use the database."""
    if "db" not in request.fixturenames:
        return None
    request.getfixturevalue("db")
    return Hub.objects.create(id=HUB_ID, slug="acme", status="ready")


# The signature


def test_unsigned_state_is_401(client, db):
    answer = client.put(
        PATH, b"{}", content_type="application/json", HTTP_HOST="hubs.localhost"
    )
    assert answer.status_code == 401 and code(answer) == "internal.unsigned"


def test_a_stale_timestamp_is_401(client, db):
    answer = signed(
        client, "put", PATH, {"slug": "a", "version": 1}, ts=int(time.time()) - 400
    )
    assert answer.status_code == 401 and code(answer) == "internal.unsigned"


def test_a_timestamp_from_the_future_is_401(client, db):
    answer = signed(
        client, "put", PATH, {"slug": "a", "version": 1}, ts=int(time.time()) + 400
    )
    assert answer.status_code == 401


def test_another_secret_is_401(client, db):
    answer = signed(client, "put", PATH, {"slug": "a", "version": 1}, secret="other")
    assert answer.status_code == 401


def test_the_previous_secret_still_signs(client, db, settings):
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = "old"
    body = {"slug": "a", "version": 1, "verifactu": {"live_paid": True}}
    assert signed(client, "put", PATH, body, secret="old").status_code == 200


def test_without_a_rotation_the_old_secret_opens_nothing(client, db, settings):
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""
    body = {"slug": "a", "version": 1}
    assert signed(client, "put", PATH, body, secret="old").status_code == 401


def test_a_v2_signature_alone_decides(client, db):
    body = {"slug": "a", "version": 1, "verifactu": {"live_paid": True}}
    alone = signed(client, "put", PATH, body, with_v1=False, with_v2=True)
    assert alone.status_code == 200
    # Naming v2 and failing it is refused even with a good v1: no downgrade.
    forged = signed(
        client,
        "put",
        PATH,
        {"slug": "a", "version": 2},
        with_v2=True,
        v2_secret="other",
    )
    assert forged.status_code == 401


def test_v2_binds_the_signature_to_its_path(client, db):
    other = f"/internal/hubs/{HUB_ID}/elsewhere"
    answer = signed(
        client,
        "put",
        PATH,
        {"slug": "a", "version": 1},
        with_v1=False,
        with_v2=True,
        v2_path=other,
    )
    assert answer.status_code == 401


@pytest.mark.parametrize("host", ["hubs.localhost", "hub.localhost", "a.localhost"])
def test_the_signature_opens_the_door_on_any_host(client, db, host):
    # The platform host (no session: it would go to the SaaS admin), the private name (`hub`, reserved) and a hub's.
    answer = signed(client, "put", PATH, {"slug": "a", "version": 1}, host=host)
    assert answer.status_code == 200


# Attempts: past 30 calls with a bad signature from an address in 5 minutes, its next bad one is 429 until the window
# of the first one ends; a good signature is always heard. The SaaS never signs wrong: this is for whatever else reaches
# the door (a scanner inside the network).

BAD_SIGNATURES = 30


def test_past_thirty_bad_signatures_the_next_bad_one_is_429_with_retry_after(client, db):
    for _ in range(BAD_SIGNATURES):
        assert signed(client, "put", PATH, {"slug": "a", "version": 1}, secret="other").status_code == 401
    answer = signed(client, "put", PATH, {"slug": "a", "version": 1}, secret="other")
    assert (answer.status_code, code(answer)) == (429, "base.rate_limited")
    assert 290 <= int(answer["Retry-After"]) <= 300
    assert answer["Cache-Control"].startswith("max-age=0")


def test_a_good_signature_is_heard_while_the_address_is_past_the_limit(client, db):
    for _ in range(BAD_SIGNATURES + 1):
        signed(client, "put", PATH, {"slug": "a", "version": 1}, secret="other")
    assert signed(client, "put", PATH, {"slug": "a", "version": 1}).status_code == 200
    assert Hub.objects.get(id=HUB_ID).state_version == 1


def test_a_good_signature_is_not_counted(client, db):
    for _ in range(BAD_SIGNATURES - 1):
        signed(client, "put", PATH, {"slug": "a", "version": 1}, secret="other")
    for version in range(1, 6):
        assert signed(client, "put", PATH, {"slug": "a", "version": version}).status_code == 200
    assert signed(client, "put", PATH, {"slug": "a", "version": 9}, secret="other").status_code == 401
    assert signed(client, "put", PATH, {"slug": "a", "version": 9}, secret="other").status_code == 429


def test_the_bad_signatures_count_per_address(db):
    scanner, other = Client(REMOTE_ADDR="10.0.9.9"), Client(REMOTE_ADDR="10.0.1.20")
    for _ in range(BAD_SIGNATURES):
        signed(scanner, "put", PATH, {"slug": "a", "version": 1}, secret="other")
    assert signed(scanner, "put", PATH, {"slug": "a", "version": 1}, secret="other").status_code == 429
    assert signed(other, "put", PATH, {"slug": "a", "version": 1}, secret="other").status_code == 401


@pytest.mark.parametrize(
    ("caller", "same", "neighbour"),
    [("203.0.113.7", "203.0.113.7", "203.0.113.8"), ("2001:db8:1:2::7", "2001:db8:1:2:ffff::1", "2001:db8:1:3::7")],
)
def test_the_bad_signatures_count_per_address_as_the_proxies_saw_it(db, settings, caller, same, neighbour):
    settings.TRUSTED_PROXY_HOPS = 1
    behind = Client(REMOTE_ADDR="10.0.0.5")

    def bad(address):
        return signed(behind, "put", PATH, {"slug": "a", "version": 1}, secret="other", HTTP_X_FORWARDED_FOR=address)

    for _ in range(BAD_SIGNATURES):
        bad(caller)
    assert bad(same).status_code == 429
    assert bad(neighbour).status_code == 401


def test_with_the_cache_away_the_signature_still_decides(client, db, monkeypatch):
    from django.core.cache import caches

    def away(*args, **kwargs):
        raise ConnectionError("Valkey is not answering")

    for method in ("get_many", "add", "incr", "set", "touch"):
        monkeypatch.setattr(caches["default"], method, away)
    assert signed(client, "put", PATH, {"slug": "a", "version": 1}, secret="other").status_code == 401
    assert signed(client, "put", PATH, {"slug": "a", "version": 1}).status_code == 200


def test_the_state_is_only_put(client, db):
    assert signed(client, "post", PATH, {"slug": "a", "version": 1}).status_code == 405


# The photo


def test_state_applies_the_verifactu_block_on_the_slugs_scope(client, db):
    # The SaaS still sends ``live_paid`` until VeriFactu's retirement of it is out (PLAN §30, expand/contract): the
    # photo is applied as ever and the retired field is written nowhere.
    answer = signed(
        client,
        "put",
        PATH,
        {
            "hub_id": HUB_ID,
            "slug": "a",
            "version": 3,
            "status": "active",
            "verifactu": {"live_paid": True, "representation": APPROVED},
        },
    )
    assert answer.status_code == 200 and answer.json() == {
        "applied": True,
        "version": 3,
    }
    config = Config.objects.get()
    assert (
        config.live_paid,
        config.hub_status,
        config.representation_status,
        config.synced_version,
    ) == (False, "active", "approved", 3)


def test_the_business_status_travels_on_its_own(client, db):
    body = {"slug": "a", "version": 4, "status": "past_due"}
    assert signed(client, "put", PATH, body).json() == {"applied": True, "version": 4}
    assert Config.objects.get().hub_status == "past_due"


def test_the_photo_that_reactivates_a_suspended_business_opens_it_again(client, db):
    # BILLING-F17 of the SaaS: the way back of a suspended business is this photo, which its own 402 never blocks.
    Hub.objects.filter(id=HUB_ID).update(state={"status": "suspended"}, state_version=1)
    host = "acme.localhost:8000"
    assert client.get("/api/me", HTTP_HOST=host).status_code == 402
    body = {"slug": "acme", "version": 2, "status": "active"}
    assert signed(client, "put", PATH, body).json() == {"applied": True, "version": 2}
    assert client.get("/api/me", HTTP_HOST=host).status_code == 200  # served again, as any open hub


def test_the_photo_tells_the_hub_its_id_in_erplora(client, db):
    # Where the signed authorisation is sent (verifactu.representation.submit): POST /internal/hubs/{id}/representation.
    body = {"slug": "a", "version": 5, "status": "active"}
    assert signed(client, "put", PATH, body).json() == {"applied": True, "version": 5}
    assert str(Config.objects.get().hub_id) == HUB_ID


def test_an_older_photo_is_ignored(client, db):
    signed(
        client,
        "put",
        PATH,
        {"slug": "a", "version": 5, "verifactu": {"representation": APPROVED}},
    )
    answer = signed(
        client,
        "put",
        PATH,
        {"slug": "a", "version": 4, "verifactu": {"representation": {"status": "revoked"}}},
    )
    assert answer.status_code == 200 and answer.json() == {
        "applied": False,
        "version": 5,
    }
    assert Config.objects.get().representation_status == "approved"


def test_without_the_block_verifactu_is_left_alone(client, db, registered):
    answer = signed(client, "put", PATH, {"slug": "a", "version": 1})
    assert answer.status_code == 200 and answer.json() == {"applied": True, "version": 1}
    assert not Config.objects.exists()


def test_a_photo_of_a_hub_the_registry_does_not_know_is_404(client, db):
    # The SaaS registers a business (PUT /internal/hubs/{id}) before it sends its photo.
    other = "/internal/hubs/0199c4b0-0000-7000-8000-0000000000ff/state"
    answer = signed(client, "put", other, {"slug": "a", "version": 1, "status": "active"})
    assert answer.status_code == 404 and code(answer) == "not_found"
    assert not Config.objects.exists()


def test_the_photo_is_kept_on_the_registry_as_it_came(client, db, registered):
    body = {"hub_id": HUB_ID, "slug": "acme", "version": 2, "status": "active", "plan": {"slug": "starter"}}
    assert signed(client, "put", PATH, body).json() == {"applied": True, "version": 2}
    registered.refresh_from_db()
    assert (registered.state, registered.state_version) == (body, 2)


@pytest.mark.parametrize(
    "body",
    [
        {"slug": "a"},
        {"slug": "a", "version": -1},
        {"slug": "a", "version": "7"},
        {"slug": "a", "version": True},
        {"slug": "a", "version": 1, "status": "gone"},
        {"slug": "a", "version": 1, "verifactu": {"live_paid": "yes"}},
        {"slug": "a", "version": 1, "verifactu": {"live_paid": 1}},
        {
            "slug": "a",
            "version": 1,
            "verifactu": {"representation": {"status": "maybe"}},
        },
        {"slug": "a", "version": 1, "verifactu": []},
    ],
)
def test_a_photo_out_of_contract_is_422(client, db, body, registered):
    answer = signed(client, "put", PATH, body)
    assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"
    assert not Config.objects.exists()
    registered.refresh_from_db()
    assert (registered.state, registered.state_version) == ({}, 0)


@pytest.mark.parametrize("raw", [b"not json", b"[]", b""])
def test_a_body_that_is_no_object_is_422(client, db, raw):
    answer = signed(client, "put", PATH, raw)
    assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"


def test_a_body_naming_another_hub_is_refused(client, db):
    # v1 signs the body only: the SaaS names the hub of the path in it, and the Hub compares them.
    body = {"hub_id": "0199c4b0-0000-7000-8000-000000000002", "slug": "a", "version": 1}
    answer = signed(client, "put", PATH, body)
    assert answer.status_code == 422 and code(answer) == "internal.hub_mismatch"



# The registry: PUT, GET and DELETE /internal/hubs/{id}, POST …/restore (plan 2026-10-17, §1.5)

NEW_ID = "0199c4b0-0000-7000-8000-000000000010"
HUB_PATH = f"/internal/hubs/{NEW_ID}"
REGISTRY = {
    "id": NEW_ID,
    "slug": "bar-pepe",
    "name": "Bar Pepe",
    "country": "ES",
    "timezone": "Europe/Madrid",
    "language": "es",
    "vertical": None,
}


@pytest.fixture
def saas_at(fake_saas, settings):
    """The SaaS stand-in (``base.auth.post``), with this module's secret on both sides."""

    def install(**kwargs):
        fake = fake_saas(**kwargs)
        settings.INTERNAL_SHARED_SECRET = SECRET
        return fake

    return install


@pytest.fixture
def saas_hears(saas_at):
    return saas_at(body={"id": NEW_ID, "status": "active"})


def test_unsigned_registry_calls_are_401_and_write_nothing(client, db):
    for method in ("put", "delete"):
        answer = getattr(client, method)(HUB_PATH, b"{}", content_type="application/json", HTTP_HOST="hub.localhost")
        assert answer.status_code == 401 and code(answer) == "internal.unsigned"
    answer = client.get(HUB_PATH, HTTP_HOST="hub.localhost")
    assert answer.status_code == 401 and code(answer) == "internal.unsigned"
    restore = client.post(f"{HUB_PATH}/restore", b"{}", content_type="application/json", HTTP_HOST="hub.localhost")
    assert restore.status_code == 401
    assert not Hub.objects.filter(pk=NEW_ID).exists()


def test_a_registration_signed_301_seconds_ago_is_401(client, db):
    answer = signed(client, "put", HUB_PATH, REGISTRY, ts=int(time.time()) - 301)
    assert answer.status_code == 401
    assert not Hub.objects.filter(pk=NEW_ID).exists()


@pytest.mark.parametrize("host", ["hub.erplora.internal", "localhost:8000", "hubs.localhost"])
def test_the_registry_answers_on_the_private_name_and_locally(client, db, settings, saas_hears, host):
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "hub.erplora.internal"]
    answer = signed(client, "put", HUB_PATH, REGISTRY, host=host, with_v2=True)
    assert answer.status_code == 202


def test_a_new_business_is_ready_at_once_and_the_saas_hears_it_after_the_commit(
    client, db, saas_hears, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        answer = signed(client, "put", HUB_PATH, REGISTRY, with_v2=True)
    assert answer.status_code == 202
    body = answer.json()
    assert {key: body[key] for key in ("id", "slug", "status", "is_demo", "expires_at", "state_version")} == {
        "id": NEW_ID,
        "slug": "bar-pepe",
        "status": "ready",
        "is_demo": False,
        "expires_at": None,
        "state_version": 0,
    }
    assert body["ready_at"] is not None and "created" not in body
    hub = Hub.objects.get(pk=NEW_ID)
    assert (hub.status, hub.name, hub.country) == ("ready", "Bar Pepe", "ES")
    [call] = saas_hears.calls
    ready_path = f"/internal/hubs/{NEW_ID}/ready"
    assert call["url"] == f"http://localhost:8001{ready_path}"
    assert json.loads(call["body"]) == {"id": NEW_ID}
    now = int(call["headers"]["X-Erplora-Timestamp"])
    assert verify_signed("POST", ready_path, call["body"], call["headers"], secrets=[SECRET], now=now)
    assert "X-Erplora-Signature-V2" in call["headers"]


def test_registering_it_again_is_200_and_the_saas_hears_nothing_more(
    client, db, saas_hears, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        signed(client, "put", HUB_PATH, REGISTRY)
    with django_capture_on_commit_callbacks(execute=True):
        again = signed(client, "put", HUB_PATH, {**REGISTRY, "name": "Bar Pepe 2"})
    assert again.status_code == 200 and again.json()["status"] == "ready"
    assert Hub.objects.get(pk=NEW_ID).name == "Bar Pepe 2"
    assert len(saas_hears.calls) == 1


def test_a_saas_that_is_away_never_breaks_the_registration(
    client, db, saas_at, django_capture_on_commit_callbacks, caplog
):
    saas_at(raises=OSError("connection refused"))
    with django_capture_on_commit_callbacks(execute=True):
        answer = signed(client, "put", HUB_PATH, REGISTRY)
    assert answer.status_code == 202
    assert Hub.objects.get(pk=NEW_ID).status == "ready"
    assert "base.hub.ready_unreported" in caplog.text


@pytest.mark.parametrize("slug", ["demo-x1234567", "hub", "Bar Pepe"])
def test_a_slug_no_business_may_take_is_422(client, db, slug):
    answer = signed(client, "put", HUB_PATH, {**REGISTRY, "slug": slug})
    assert answer.status_code == 422 and code(answer) == "base.slug_invalid"
    assert not Hub.objects.filter(pk=NEW_ID).exists()


def test_the_slug_of_another_hub_is_409(client, db):
    answer = signed(client, "put", HUB_PATH, {**REGISTRY, "slug": "acme"})
    assert answer.status_code == 409 and code(answer) == "base.slug_taken"


def test_a_registration_naming_another_hub_is_refused(client, db):
    answer = signed(client, "put", HUB_PATH, {**REGISTRY, "id": HUB_ID})
    assert answer.status_code == 422 and code(answer) == "internal.hub_mismatch"
    assert not Hub.objects.filter(pk=NEW_ID).exists()


@pytest.mark.parametrize(
    "raw",
    [b"not json", b"[]", json.dumps({**REGISTRY, "slug": None}).encode(), json.dumps({**REGISTRY, "country": "ESP"}).encode()],
)
def test_a_registration_out_of_contract_is_422(client, db, raw):
    answer = signed(client, "put", HUB_PATH, raw)
    assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"


def test_get_answers_the_status_the_saas_waits_for(client, db):
    answer = signed(client, "get", f"/internal/hubs/{HUB_ID}", b"", with_v2=True)
    assert answer.status_code == 200
    assert (answer.json()["id"], answer.json()["slug"], answer.json()["status"]) == (HUB_ID, "acme", "ready")


def test_get_of_an_unknown_hub_is_the_404_envelope(client, db):
    answer = signed(client, "get", HUB_PATH, b"", with_v2=True)
    assert answer.status_code == 404 and code(answer) == "not_found"


def test_delete_cancels_the_hub(client, db, registered):
    answer = signed(client, "delete", f"/internal/hubs/{HUB_ID}", {"id": HUB_ID}, with_v2=True)
    assert answer.status_code == 202 and answer.json()["status"] == "cancelled"
    registered.refresh_from_db()
    assert registered.status == "cancelled" and registered.cancelled_at is not None


def test_delete_of_an_unknown_hub_is_404(client, db):
    # The SaaS's _delete takes a 404 as «nothing to delete».
    answer = signed(client, "delete", HUB_PATH, {"id": NEW_ID})
    assert answer.status_code == 404


def test_restore_brings_a_cancelled_hub_back(client, db, registered):
    signed(client, "delete", f"/internal/hubs/{HUB_ID}", {"id": HUB_ID})
    answer = signed(client, "post", f"/internal/hubs/{HUB_ID}/restore", {"id": HUB_ID}, with_v2=True)
    assert answer.status_code == 200 and answer.json()["status"] == "ready"


def test_restore_of_a_purged_hub_is_hub_purged(client, db, registered):
    # Literal: the SaaS's _restore compares this code and marks the business deleted.
    Hub.objects.filter(pk=HUB_ID).update(status="purged")
    answer = signed(client, "post", f"/internal/hubs/{HUB_ID}/restore", {"id": HUB_ID})
    assert answer.status_code == 409 and code(answer) == "hub_purged"


def test_restore_of_an_unknown_hub_is_404(client, db):
    # The SaaS then registers it again (PUT).
    answer = signed(client, "post", f"{HUB_PATH}/restore", {"id": NEW_ID})
    assert answer.status_code == 404


def test_a_registry_call_naming_another_hub_is_refused(client, db):
    for method, path in (("delete", f"/internal/hubs/{HUB_ID}"), ("post", f"/internal/hubs/{HUB_ID}/restore")):
        answer = signed(client, method, path, {"id": NEW_ID})
        assert answer.status_code == 422 and code(answer) == "internal.hub_mismatch"
    assert Hub.objects.get(pk=HUB_ID).status == "ready"


def test_each_registry_route_takes_only_its_methods(client, db):
    assert signed(client, "post", HUB_PATH, REGISTRY).status_code == 405
    assert signed(client, "get", f"{HUB_PATH}/restore", b"").status_code == 405


# The demos: POST /internal/demos and POST /internal/demos/{slug}/codes (plan 2026-10-17, §1.5 and §1.6)

DEMOS_PATH = "/internal/demos"
#: Two browsers of the SaaS, as it names them: the sha256 of a random token of each session.
OWNER = hashlib.sha256(b"ana's browser").hexdigest()
STRANGER = hashlib.sha256(b"bea's browser").hexdigest()


def new_demo(client, session_key=OWNER, **body):
    """The SaaS's ``create_demo``: its body as it sends it, signed v1 + v2."""
    payload = {"session_key": session_key, "vertical": None, "language": "en", **body}
    return signed(client, "post", DEMOS_PATH, payload, with_v2=True)


def demo_code(client, slug, session_key=OWNER, language="es"):
    """The SaaS's ``create_demo_code``."""
    path = f"/internal/demos/{slug}/codes"
    return signed(client, "post", path, {"session_key": session_key, "language": language}, with_v2=True)


def test_a_new_demo_is_201_with_what_the_saas_reads(client, db):
    answer = new_demo(client)
    assert answer.status_code == 201
    body = answer.json()
    assert set(body) == {"id", "slug", "expires_at", "created"} and body["created"] is True
    assert re.fullmatch(r"demo-[0-9a-f]{8}", body["slug"])
    hub = Hub.objects.get(slug=body["slug"])
    assert (body["id"], hub.is_demo, hub.status, hub.demo_session_key) == (str(hub.id), True, "ready", OWNER)
    # An aware ISO 8601, as the SaaS's door parses it (``parse_datetime`` and ``is_aware``).
    expires_at = parse_datetime(body["expires_at"])
    assert expires_at.tzinfo is not None and expires_at == hub.expires_at


def test_the_same_browser_again_is_200_with_its_live_demo(client, db):
    first = new_demo(client).json()
    again = new_demo(client)
    assert again.status_code == 200
    assert again.json() == {**first, "created": False}


def test_at_the_cap_it_is_503_demo_full_with_retry_after(client, db, settings):
    settings.MAX_CONCURRENT_DEMOS = 1
    new_demo(client)
    answer = new_demo(client, STRANGER)
    assert (answer.status_code, code(answer), answer["Retry-After"]) == (503, "base.demo_full", "60")
    assert Hub.objects.filter(is_demo=True).count() == 1


@pytest.mark.parametrize(
    "raw",
    [b"[]", b"nope", b"{}", json.dumps({"session_key": "not-a-sha256"}).encode()],
    ids=["array", "not-json", "no-key", "bad-key"],
)
def test_a_demo_asked_out_of_contract_is_422(client, db, raw):
    answer = signed(client, "post", DEMOS_PATH, raw)
    assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"
    assert not Hub.objects.filter(is_demo=True).exists()


def test_unsigned_demo_calls_are_401_and_make_nothing(client, db):
    raw = json.dumps({"session_key": OWNER}).encode()
    answer = client.post(DEMOS_PATH, raw, content_type="application/json", HTTP_HOST="hub.localhost")
    assert answer.status_code == 401 and code(answer) == "internal.unsigned"
    slug = new_demo(client).json()["slug"]
    answer = client.post(f"/internal/demos/{slug}/codes", raw, content_type="application/json", HTTP_HOST="hub.localhost")
    assert answer.status_code == 401
    assert Hub.objects.filter(is_demo=True).count() == 1 and not DemoCode.objects.exists()


def test_the_owner_gets_a_one_time_code_201(client, db):
    slug = new_demo(client).json()["slug"]
    answer = demo_code(client, slug)
    assert answer.status_code == 201
    body = answer.json()
    assert set(body) == {"code", "expires_at"} and len(body["code"]) >= 43
    assert parse_datetime(body["expires_at"]).tzinfo is not None
    [row] = DemoCode.objects.all()
    assert (row.hub.slug, row.language, row.used_at) == (slug, "es", None)
    assert row.code_hash == hashlib.sha256(body["code"].encode()).hexdigest()


def test_another_browser_s_code_is_403_demo_not_owner(client, db):
    slug = new_demo(client).json()["slug"]
    answer = demo_code(client, slug, STRANGER)
    assert (answer.status_code, code(answer)) == (403, "base.demo_not_owner")
    assert not DemoCode.objects.exists()


def test_a_code_of_a_demo_that_ended_is_410_hub_gone(client, db):
    slug = new_demo(client).json()["slug"]
    Hub.objects.filter(slug=slug).update(expires_at=Hub.objects.get(slug=slug).created_at)
    answer = demo_code(client, slug)
    assert (answer.status_code, code(answer)) == (410, "base.hub_gone")


@pytest.mark.parametrize("slug", ["demo-00000000", "acme"])
def test_a_code_of_no_demo_is_404(client, db, slug):
    answer = demo_code(client, slug)
    assert (answer.status_code, code(answer)) == (404, "not_found")


def test_each_demo_route_takes_only_post(client, db):
    assert signed(client, "get", DEMOS_PATH, b"").status_code == 405
    slug = new_demo(client).json()["slug"]
    assert signed(client, "put", f"/internal/demos/{slug}/codes", {"session_key": OWNER}).status_code == 405
