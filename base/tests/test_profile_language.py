"""The language a person chose in «My profile» (BASE-F64) is the one every device they are signed in on speaks, also
one whose session was opened before the choice and whose language cookie still says the one from before: at once
(the next request) and after reloading. Without a choice of their own, the cookie their way in left stands.
"""

import pytest
from django.conf import settings
from django.test import Client

from base.models import Membership
from base.tenancy.tests.business import HUB_DB, A, B, in_business_a
from base.tests.test_api_assistant import HOST, post

__all__ = ["in_business_a"]

pytestmark = HUB_DB

COOKIE = settings.LANGUAGE_COOKIE_NAME


@pytest.fixture
def ana(client, make_user):
    user = make_user("ana", host=A.key, role="hub_manager")
    client.force_login(user)
    return user


def another_device(user, language: str) -> Client:
    """Another browser of ``user``, its session opened before the choice and its cookie in ``language``."""
    device = Client()
    device.force_login(user)
    device.cookies[COOKIE] = language
    return device


def chose(client, language: str) -> None:
    response = post(client, "/me/preferences", {"language": language})
    assert response.status_code == 200, response.content


def session_language(client, host: str = A.key) -> str:
    response = client.get("/api/me", HTTP_HOST=f"{host}.localhost")
    assert response.status_code == 200, response.content
    return response.json()["language"]


@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize("before, chosen", [("en", "es"), ("es", "en")])
def test_a_language_chosen_on_one_device_is_the_one_every_open_device_speaks(client, ana, before, chosen):
    client.cookies[COOKIE] = before
    tablet = another_device(ana, before)
    assert session_language(tablet) == before
    chose(client, chosen)
    assert session_language(tablet) == chosen
    page = tablet.get("/", **HOST, HTTP_ACCEPT="text/html")
    assert page.status_code == 200
    assert f'<html lang="{chosen}"' in page.content.decode()
    # The language every text the server writes in this request comes in, also an error's.
    assert page["Content-Language"] == chosen
    assert COOKIE not in page.cookies


def test_the_language_chosen_in_one_business_leaves_the_person_s_other_business_as_it_was(client, ana, hub_b):
    Membership.objects.create(user=ana, host=B.key, role="hub_manager")
    chose(client, "es")
    assert session_language(another_device(ana, "en"), B.key) == "en"
    assert session_language(another_device(ana, "en")) == "es"


@pytest.mark.parametrize("spoken", ["es", "en"])
def test_without_a_choice_of_their_own_each_device_speaks_its_cookie(client, ana, spoken):
    chose(client, "")
    assert session_language(another_device(ana, spoken)) == spoken


def test_without_a_session_the_browser_s_language_stands(client, ana):
    chose(client, "es")
    visitor = Client()
    visitor.cookies[COOKIE] = "en"
    page = visitor.get("/settings", **HOST, HTTP_ACCEPT="text/html")
    assert '<html lang="en">' in page.content.decode()
