"""The SaaS's door into the Hub (PLAN-SAAS §2, §2.2): ``/internal`` calls signed with HMAC-SHA256 and a timestamp.

A call is heard by its v2 signature when it carries one (method, path and body; v2 alone decides), else by its v1
(the body only), within five minutes and with the current secret or, during a rotation, the previous one. The
signature is the authentication: the ALB never publishes ``/internal``, so the door answers on any host (the
SaaS reaches it by the private name).

Phase 1 has no registry of hubs: ``PUT /internal/hubs/{id}/state`` (the photo) names its hub by ``slug`` and only
its VeriFactu block and the business's status are applied, through ``verifactu.config.sync`` on that hub.
"""

import hashlib
import hmac
import json
import time

import pytest

from apps.verifactu.models import Config

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
):
    """``method`` on ``path`` with ``body`` (a dict, or raw bytes), signed as the SaaS signs it."""
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    ts = str(ts or int(time.time()))
    headers = {"HTTP_X_ERPLORA_TIMESTAMP": ts, "HTTP_HOST": host}
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


def test_the_state_is_only_put(client, db):
    assert signed(client, "post", PATH, {"slug": "a", "version": 1}).status_code == 405


# The photo


def test_state_applies_the_verifactu_block_on_the_slugs_scope(client, db):
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
    ) == (True, "active", "approved", 3)


def test_the_business_status_travels_on_its_own(client, db):
    body = {"slug": "a", "version": 4, "status": "past_due"}
    assert signed(client, "put", PATH, body).json() == {"applied": True, "version": 4}
    assert Config.objects.get().hub_status == "past_due"


def test_an_older_photo_is_ignored(client, db):
    signed(
        client,
        "put",
        PATH,
        {"slug": "a", "version": 5, "verifactu": {"live_paid": True}},
    )
    answer = signed(
        client,
        "put",
        PATH,
        {"slug": "a", "version": 4, "verifactu": {"live_paid": False}},
    )
    assert answer.status_code == 200 and answer.json() == {
        "applied": False,
        "version": 5,
    }
    assert Config.objects.get().live_paid is True


def test_without_the_block_nothing_is_applied(client, db):
    answer = signed(client, "put", PATH, {"slug": "a", "version": 1})
    assert answer.status_code == 200 and answer.json() == {"applied": False}
    assert not Config.objects.exists()


@pytest.mark.parametrize("slug", ["hub", "A B", "", None])
def test_a_slug_that_names_no_hub_is_422(client, db, slug):
    answer = signed(client, "put", PATH, {"slug": slug, "version": 1})
    assert answer.status_code == 422 and code(answer) == "internal.slug_invalid"


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
def test_a_photo_out_of_contract_is_422(client, db, body):
    answer = signed(client, "put", PATH, body)
    assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"
    assert not Config.objects.exists()


@pytest.mark.parametrize("raw", [b"not json", b"[]", b""])
def test_a_body_that_is_no_object_is_422(client, db, raw):
    answer = signed(client, "put", PATH, raw)
    assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"


def test_a_body_naming_another_hub_is_refused(client, db):
    # v1 signs the body only: the SaaS names the hub of the path in it, and the Hub compares them.
    body = {"hub_id": "0199c4b0-0000-7000-8000-000000000002", "slug": "a", "version": 1}
    answer = signed(client, "put", PATH, body)
    assert answer.status_code == 422 and code(answer) == "internal.hub_mismatch"
