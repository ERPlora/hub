"""The copies of a business's data, where they are read (round 2026-10-30 of PLAN-DB, proposals (k) and (l)).

- ``GET /internal/hubs/{id}/dumps`` (signed, the SaaS's panel and mails; saas ``hubs/README.md``, «Contrato para el Hub»):
  ``{available, dumps: [{id: its S3 key, kind, created_at, bytes, url}]}``, newest first, each link signed for 15
  minutes; ``available`` false for a business without its own database (it never gets a copy); 200 for a business
  that left (the 410 is its host's door, never ``/internal``); 404 for one unknown or purged.
- ``base.hub.dumps`` (Settings › Data, who runs the business): the copies without links, and how the last reset went;
  in a business that still shares its database, nothing and ``available`` false.
- ``base.hub.dump_link``: the link of one copy, asked on every click; never another business's copy.
"""

import datetime as dt
import urllib.parse
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from live.context import OperationContext, Scope
from live.errors import NotFound, OperationError, PermissionDenied
from live.operations import get

from base.models import Membership
from base.permissions import permissions_for
from base.tenancy import connections, names
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3, no_dumps_bucket  # noqa: F401
from base.tests.test_internal import signed
from control.models import Hub, HubDump

pytestmark = pytest.mark.django_db

HUB_ID = uuid.UUID("0199c4b0-0000-7000-8000-0000000000d1")
OTHER_ID = uuid.UUID("0199c4b0-0000-7000-8000-0000000000d2")
AT = dt.datetime(2026, 10, 31, 10, 15, tzinfo=dt.UTC)


def business(hub_id=HUB_ID, slug="acme", *, own=True, **fields) -> Hub:
    db_name = names.hub_db_name(connections.control_name(), hub_id) if own else ""
    fields.setdefault("ready_at", AT - dt.timedelta(days=30))
    return Hub.objects.create(id=hub_id, slug=slug, status=fields.pop("status", "ready"), db_name=db_name, **fields)


def copy(hub: Hub, kind: str, minutes: int, size: int = 100) -> HubDump:
    at = AT + dt.timedelta(minutes=minutes)
    return HubDump.objects.create(
        hub=hub, kind=kind, key=f"{hub.id.hex}/{at:%Y%m%dT%H%M%SZ}-{kind}.dump", bytes=size, created_at=at
    )


def dumps_of(hub_id) -> "object":
    return signed(Client(), "get", f"/internal/hubs/{hub_id}/dumps", b"", with_v2=True)


# ── GET /internal/hubs/{id}/dumps ────────────────────────────────────────────────────────────────────────────────


def test_the_saas_gets_the_copies_newest_first_each_with_a_link_of_15_minutes(dumps_bucket):
    hub = business()
    older = copy(hub, "reset", 0, size=10)
    newer = copy(hub, "offboarding", 5, size=20)
    copy(business(OTHER_ID, "other"), "reset", 9)

    answer = dumps_of(HUB_ID)

    assert answer.status_code == 200
    body = answer.json()
    assert body["available"] is True
    assert [(row["id"], row["kind"], row["created_at"], row["bytes"]) for row in body["dumps"]] == [
        (newer.key, "offboarding", "2026-10-31T10:20:00Z", 20),
        (older.key, "reset", "2026-10-31T10:15:00Z", 10),
    ]
    for row in body["dumps"]:
        link = urllib.parse.urlsplit(row["url"])
        assert link.scheme in {"http", "https"}
        assert link.path == f"/{dumps_bucket}/{row['id']}"
        assert urllib.parse.parse_qs(link.query)["X-Amz-Expires"] == ["900"]
        name = row["id"].rsplit("/", 1)[-1]
        assert urllib.parse.parse_qs(link.query)["response-content-disposition"] == [
            f'attachment; filename="erplora-acme-{name}"'
        ]


@pytest.mark.parametrize("status", ["cancelled", "archiving"])
def test_a_business_that_left_answers_200(dumps_bucket, status):
    hub = business(status=status, cancelled_at=AT)
    copy(hub, "offboarding", 1)

    answer = dumps_of(HUB_ID)

    assert answer.status_code == 200
    assert [row["kind"] for row in answer.json()["dumps"]] == ["offboarding"]


def test_without_copies_the_list_is_empty(dumps_bucket):
    business()

    assert dumps_of(HUB_ID).json() == {"available": True, "dumps": []}


@pytest.mark.parametrize(
    "fields",
    [{"own": False}, {"status": "cancelled", "ready_at": None}],
    ids=["shares-controls-database", "left-before-its-database-was-made"],
)
def test_a_business_that_never_gets_a_copy_says_it(dumps_bucket, fields):
    business(**fields)

    assert dumps_of(HUB_ID).json() == {"available": False, "dumps": []}


def test_an_unknown_or_purged_business_is_404(dumps_bucket):
    assert dumps_of(HUB_ID).status_code == 404
    business(status="purged")
    assert dumps_of(HUB_ID).status_code == 404


def test_without_a_bucket_the_copies_cannot_be_linked(no_dumps_bucket):
    copy(business(), "reset", 0)

    answer = dumps_of(HUB_ID)

    assert answer.status_code == 503
    assert answer.json()["error"]["code"] == "base.dumps_unavailable"


def test_an_unsigned_call_is_refused():
    business()

    assert Client().get(f"/internal/hubs/{HUB_ID}/dumps", HTTP_HOST="hubs.localhost").status_code == 401


# ── Settings › Data: base.hub.dumps and base.hub.dump_link ──────────────────────────────────────────────────────


def person(slug: str, role=Membership.Role.OWNER) -> OperationContext:
    user = get_user_model().objects.create_user(username=f"{role}-{slug}", password="pw")
    Membership.objects.create(user=user, host=slug, role=role)
    scope = Scope("host", slug)
    return OperationContext(scope=scope, actor=user, permissions=permissions_for(user, scope), language="es")


def call(ctx, name, /, **data):
    op = get(name)
    return op(ctx, op.input(**data))


def test_who_runs_the_business_sees_its_copies_and_how_its_reset_went():
    hub = business()
    first = copy(hub, "reset", 0)
    Hub.objects.filter(pk=hub.pk).update(
        reset_sections={
            "apps": ["table"],
            "language": "es",
            "requested_by": "Olga",
            "state": "done",
            "error": "",
            "removed": [{"id": "table", "label": "Mesas", "removed": 12, "failed": 0, "problems": []}],
            "dump": str(first.pk),
            "finished_at": "2026-10-31T10:16:00+00:00",
        }
    )
    copy(business(OTHER_ID, "other"), "reset", 3)

    seen = call(person("acme"), "base.hub.dumps")

    assert seen.available is True
    assert [(row.id, row.kind, row.bytes, row.created_at) for row in seen.dumps] == [
        (first.pk, "reset", 100, AT)
    ]
    assert (seen.reset.state, seen.reset.requested_by, seen.reset.error) == ("done", "Olga", "")
    assert [(section.id, section.label) for section in seen.reset.sections] == [("table", "Mesas")]
    assert [(app.id, app.removed) for app in seen.reset.removed] == [("table", 12)]
    assert seen.reset.finished_at == AT + dt.timedelta(minutes=1)


def test_a_business_never_reset_has_no_reset_to_show():
    business()

    assert call(person("acme"), "base.hub.dumps").reset is None


def test_a_business_that_shares_its_database_has_no_copies():
    seen = call(person("a"), "base.hub.dumps")

    assert (seen.available, seen.reset, seen.dumps) == (False, None, [])


def test_the_link_of_a_copy_is_asked_on_each_click(dumps_bucket):
    made = copy(business(), "reset", 0)

    link = call(person("acme"), "base.hub.dump_link", id=made.pk)

    query = urllib.parse.parse_qs(urllib.parse.urlsplit(link.url).query)
    assert urllib.parse.urlsplit(link.url).path.endswith(made.key)
    assert query["X-Amz-Expires"] == ["900"]
    assert query["response-content-disposition"] == [f'attachment; filename="erplora-acme-{made.key.rsplit("/", 1)[-1]}"']
    signed_at = dt.datetime.strptime(query["X-Amz-Date"][0], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.UTC)
    assert link.expires_at == signed_at + dt.timedelta(minutes=15)


def test_another_businesss_copy_is_never_linked(dumps_bucket):
    business()
    theirs = copy(business(OTHER_ID, "other"), "reset", 0)

    with pytest.raises(NotFound):
        call(person("acme"), "base.hub.dump_link", id=theirs.pk)


def test_without_a_bucket_there_is_no_link_to_give(no_dumps_bucket):
    made = copy(business(), "reset", 0)

    with pytest.raises(OperationError) as refused:
        call(person("acme"), "base.hub.dump_link", id=made.pk)

    assert (refused.value.status, refused.value.code) == (503, "base.dumps_unavailable")


@pytest.mark.parametrize("name", ["base.hub.dumps", "base.hub.dump_link"])
def test_only_who_runs_the_business_reads_its_copies(dumps_bucket, name):
    made = copy(business(), "reset", 0)
    data = {"id": made.pk} if name == "base.hub.dump_link" else {}

    with pytest.raises(PermissionDenied):
        call(person("acme", Membership.Role.MANAGER), name, **data)
