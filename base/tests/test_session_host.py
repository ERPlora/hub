"""A session is a session of the host it was opened on (phase 2, S1; PLAN-DB §2 and §14.2; plan 2026-10-22, §2.3).

Sessions stay in control's database in this phase (plan, decision 3), so the session of hub B is a row hub A's host
could read too. The login notes the host it was opened on (a hub's slug, or the platform host's mark), and on any
other host that session is no session: anonymous, 401 on the API, the SaaS's login on a page. Nothing changes for a
browser: its cookie is its host's only. A session from before this rule, with no host noted, stays valid where it is
used until it expires.
"""

import pytest
from django.contrib.auth import get_user_model, login
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from base.middleware import PLATFORM_SESSION_HOST, SESSION_HOST_KEY
from base.models import Membership
from control.models import Hub

pytestmark = pytest.mark.django_db


def member_of(*slugs: str):
    user = get_user_model().objects.create_user(username="ana", password="pw")
    for slug in slugs:
        Membership.objects.create(user=user, host=slug, role=Membership.Role.ADMIN)
    return user


def session_opened_on(client, user, *, hub=None, platform_host=False) -> str:
    """Log ``user`` in as the Hub does, on ``hub``'s host (or the platform host), and give ``client`` its cookie."""
    request = RequestFactory().get("/auth/callback")
    request.session = SessionStore()
    if hub is not None:
        request.hub = hub
    request.platform_host = platform_host
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.save()
    client.cookies["sessionid"] = request.session.session_key
    return request.session.session_key


def items(client, host: str) -> int:
    return client.get("/api/demo/items", HTTP_HOST=host).status_code


def test_the_login_notes_the_host_it_was_opened_on(client):
    key = session_opened_on(client, member_of("a"), hub=Hub.objects.get(slug="a"))

    assert SessionStore(session_key=key)[SESSION_HOST_KEY] == "a"


def test_a_session_works_on_its_own_host(client):
    session_opened_on(client, member_of("a", "b"), hub=Hub.objects.get(slug="a"))

    assert items(client, "a.localhost") == 200


def test_a_hubs_session_is_no_session_on_another_hubs_host_even_for_one_of_its_members(client):
    session_opened_on(client, member_of("a", "b"), hub=Hub.objects.get(slug="b"))

    assert items(client, "a.localhost") == 401
    assert client.get("/api/me", HTTP_HOST="a.localhost").json()["user"] is None
    assert items(client, "b.localhost") == 200


def test_a_hubs_session_never_opens_the_admin(client):
    user = member_of("a")
    user.is_staff = user.is_superuser = True
    user.save()
    session_opened_on(client, user, hub=Hub.objects.get(slug="a"))

    page = client.get("/admin/", HTTP_HOST="hubs.localhost")

    assert page.status_code == 302  # anonymous there: to the SaaS admin's Hubs page, never the admin itself


def test_the_platform_hosts_session_is_no_session_on_a_hub(client):
    user = member_of("a")
    session_opened_on(client, user, platform_host=True)

    assert SessionStore(session_key=client.cookies["sessionid"].value)[SESSION_HOST_KEY] == PLATFORM_SESSION_HOST
    assert items(client, "a.localhost") == 401


def test_a_session_from_before_the_rule_stays_valid_where_it_is_used(client):
    client.force_login(member_of("a"))

    assert items(client, "a.localhost") == 200
