"""BASE-G56: entering by passing a badge on a shared device of the hub (the same identity as the PIN, never a new one).

A card reader types the card's number; the Hub keeps only a keyed digest of it (``base.access.badge_digest``, with the
hub's key, made once and kept). The brakes are the PIN's: wrong cards count against that card and against the address.
"""

import json

import pytest
from django.utils import timezone

from base import access, services
from base.models import AccessSettings, Credential, Membership, SessionOwner, TrustedDevice

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"


def a_device(client, mode=access.SHARED) -> TrustedDevice:
    token = access.new_device_token()
    device = TrustedDevice.objects.create(token_digest=access.token_digest(token), mode=mode, last_entry_at=timezone.now())
    client.cookies[access.DEVICE_COOKIE] = token
    return device


def with_badge(user, card: str) -> Credential:
    digest = access.badge_digest(access.clean_badge(card), key=services.badge_key())
    return Credential.objects.create(username=user.username, badge_digest=digest, badge_set_at=timezone.now())


def badge(client, card, next_path="/sale/pos"):
    body = json.dumps({"badge": card, "next": next_path})
    return client.post("/auth/badge", body, content_type="application/json", HTTP_HOST=HOST)


def code(response):
    return response.json()["error"]["code"]


@pytest.fixture
def ana(make_user):
    return make_user("saas:1", host="a", role=Membership.Role.EMPLOYEE, first_name="Ana")


def test_the_hub_s_key_is_made_once_and_kept(db):
    first = services.badge_key()
    assert len(first) == 32 and services.badge_key() == first
    assert AccessSettings.objects.get().badge_key == first.hex()


def test_the_card_of_a_person_of_this_hub_opens_their_session(client, ana):
    device = a_device(client)
    with_badge(ana, "04a1b2c3")
    response = badge(client, " 04A1B2C3 ")
    assert (response.status_code, response.json()) == (200, {"next": "/sale/pos"})
    owner = SessionOwner.objects.get()
    assert (owner.saas_user_id, owner.device_id, owner.credential) == ("1", device.pk, "badge")


@pytest.mark.parametrize("how", ["unknown", "another_hubs", "deactivated", "not_a_badge"])
def test_a_card_that_opens_nothing_here_says_so_once(client, make_user, how):
    a_device(client)
    if how == "another_hubs":
        with_badge(make_user("saas:7", host="b"), "04A1B2C3")
    elif how == "deactivated":
        with_badge(make_user("saas:8", host="a", is_active=False), "04A1B2C3")
    response = badge(client, "x;" if how == "not_a_badge" else "04A1B2C3")
    assert (response.status_code, code(response)) == (401, "base.badge_unknown")
    assert "PIN" in response.json()["error"]["message"]


def test_five_wrong_tries_of_one_card_make_it_wait(client, ana):
    a_device(client)
    for _ in range(5):
        badge(client, "DEADBEEF")
    refused = badge(client, "DEADBEEF")
    assert (refused.status_code, code(refused)) == (429, "base.too_many_attempts")
    with_badge(ana, "04A1B2C3")
    assert badge(client, "04A1B2C3").status_code == 200


def test_a_browser_that_is_no_device_of_the_hub_cannot_use_a_badge(client, ana):
    with_badge(ana, "04A1B2C3")
    assert code(badge(client, "04A1B2C3")) == "base.device_not_trusted"


def test_the_badge_is_never_kept_in_clear(client, ana):
    with_badge(ana, "04A1B2C3")
    assert "04A1B2C3" not in Credential.objects.get().badge_digest
