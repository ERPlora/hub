"""What only the owner of a business does, over HTTP as the screen asks it: reset the business (``base.hub.reset``),
see its copies (``base.hub.dumps``) and download one (``base.hub.dump_link``). An administrator runs the business but
does not own it: each of them answers 403 to them, as to a manager, and their session (``base.session.me``) does not
carry ``base.own_business``.
"""

import datetime as dt
import json

import pytest
from django.utils import timezone

from base.tenancy.tests.business import HOST, HUB_DB, A
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3
from control.models.dumps import HubDump

#: The S3 fixtures a downloaded copy needs, taken from where they live.
__all__ = ["aws_test_credentials", "dumps_bucket", "moto_s3"]
pytestmark = [HUB_DB, pytest.mark.usefixtures("hub_a")]

RESET = "/api/settings/data/reset"
DUMPS = "/api/settings/data/dumps"
LINK = "/api/settings/data/dumps/link"
#: What only the owner holds: a name the screen asks for (``session.can``), so it is spelled out here.
OWN_BUSINESS = "base.own_business"


@pytest.fixture
def signed_in(client, make_user):
    """Signs ``client`` in to business A as a new person with ``role``."""

    def sign_in(role: str):
        client.force_login(make_user(f"{role}-person", host=A.key, role=role))
        return client

    return sign_in


@pytest.fixture
def kept_copy(hub_a) -> HubDump:
    """A copy of business A's data made an hour ago, before a reset."""
    at = (timezone.now() - dt.timedelta(hours=1)).replace(microsecond=0)
    return HubDump.objects.create(
        hub=hub_a, kind="reset", key=f"{hub_a.id.hex}/{at:%Y%m%dT%H%M%SZ}-reset.dump", bytes=100, created_at=at
    )


def ask_reset(client):
    return client.post(RESET, json.dumps({"dry_run": True}), content_type="application/json", HTTP_HOST=HOST)


def refused(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


@pytest.mark.parametrize("role", ["hub_admin", "hub_manager"])
def test_only_the_owner_asks_for_a_reset(signed_in, role):
    assert refused(ask_reset(signed_in(role))) == (403, "permission_denied")


def test_the_owner_asks_for_a_reset(signed_in):
    answer = ask_reset(signed_in("hub_owner"))

    assert answer.status_code == 200, answer.content
    assert answer.json()["dry_run"] is True


@pytest.mark.parametrize("role", ["hub_admin", "hub_manager"])
def test_only_the_owner_sees_the_copies(signed_in, role):
    assert refused(signed_in(role).get(DUMPS, HTTP_HOST=HOST)) == (403, "permission_denied")


def test_the_owner_sees_the_copies(signed_in, kept_copy):
    answer = signed_in("hub_owner").get(DUMPS, HTTP_HOST=HOST)

    assert answer.status_code == 200, answer.content
    assert [row["id"] for row in answer.json()["dumps"]] == [str(kept_copy.pk)]


@pytest.mark.parametrize("role", ["hub_admin", "hub_manager"])
def test_only_the_owner_downloads_a_copy(signed_in, kept_copy, role):
    answer = signed_in(role).get(LINK, {"id": str(kept_copy.pk)}, HTTP_HOST=HOST)

    assert refused(answer) == (403, "permission_denied")


def test_the_owner_downloads_a_copy(signed_in, kept_copy, dumps_bucket):
    answer = signed_in("hub_owner").get(LINK, {"id": str(kept_copy.pk)}, HTTP_HOST=HOST)

    assert answer.status_code == 200, answer.content
    assert kept_copy.key in answer.json()["url"]


@pytest.mark.parametrize(("role", "owns"), [("hub_owner", True), ("hub_admin", False), ("hub_manager", False)])
def test_the_session_says_who_owns_the_business(signed_in, role, owns):
    me = signed_in(role).get("/api/me", HTTP_HOST=HOST).json()

    assert (OWN_BUSINESS in me["permissions"]) is owns
    # The administrator still runs the business.
    assert ("base.administer_hub" in me["permissions"]) is (role != "hub_manager")
