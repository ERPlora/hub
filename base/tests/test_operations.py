"""The context builder of hub-next phase 1: scope = first label of the Host, permissions by Membership."""

import dataclasses

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import RequestFactory
from live.context import OperationContext, Scope, get_builder

from base.models import Membership
from base.operations import HostScopeResolver, HubContextBuilder, is_platform_host


def request_for(host: str, user=None, language: str = "en"):
    request = RequestFactory().get("/", HTTP_HOST=host)
    request.user = user if user is not None else AnonymousUser()
    request.LANGUAGE_CODE = language
    return request


@pytest.mark.parametrize(
    ("host", "key"),
    [("a.localhost:8000", "a"), ("b.localhost", "b"), ("B.localhost:8000", "b"), ("acme-2.localhost", "acme-2")],
)
def test_scope_is_the_first_label_of_the_host(host, key):
    assert HostScopeResolver().resolve(request_for(host)) == Scope("host", key)


@pytest.mark.parametrize(
    "host",
    [
        # Reserved names (live.slugs): hubs is the Hub admin's host (no hub scope), the rest are blocked.
        "hubs.localhost:8000",
        "hub.localhost:8000",
        "www.localhost",
        "WWW.localhost:8000",
        "api.localhost",
        # The bare host and an IP are no hub.
        "localhost:8000",
        "127.0.0.1:8000",
        # Invalid slugs.
        "-a.localhost",
        "a-.localhost",
        "ab.localhost",
        "xn--bcher-kva.localhost",
    ],
)
def test_a_host_that_is_no_hub_is_not_found(host):
    with pytest.raises(Http404):
        HostScopeResolver().resolve(request_for(host))


@pytest.mark.parametrize("host", ["hubs.localhost:8000", "HUBS.localhost", "hubs.localhost"])
def test_the_platform_host_is_the_first_label_hubs(host):
    assert is_platform_host(request_for(host))


@pytest.mark.parametrize(
    "host", ["a.localhost:8000", "hub.localhost:8000", "www.localhost", "localhost:8000", "127.0.0.1:8000", "hubsx.localhost"]
)
def test_any_other_host_is_not_the_platform_host(host):
    assert not is_platform_host(request_for(host))


def test_the_platform_host_follows_the_setting(settings):
    settings.PLATFORM_HOST_LABEL = "staff"
    assert is_platform_host(request_for("staff.localhost"))
    assert not is_platform_host(request_for("hubs.localhost"))


def test_production_enforces_three_letters(settings):
    settings.LIVE = {**settings.LIVE, "hub_slug_min_length": 3}
    assert HostScopeResolver().resolve(request_for("acme.localhost")) == Scope("host", "acme")
    with pytest.raises(Http404):
        HostScopeResolver().resolve(request_for("a.localhost:8000"))


def test_the_builder_has_no_context_for_a_host_that_is_no_hub():
    with pytest.raises(Http404):
        HubContextBuilder().from_request(request_for("www.localhost"))


def test_settings_point_at_this_builder():
    assert isinstance(get_builder(), HubContextBuilder)


def test_anonymous_request():
    request = request_for("a.localhost:8000", language="es")
    ctx = HubContextBuilder().from_request(request)
    assert ctx == OperationContext(
        scope=Scope("host", "a"), actor=None, permissions=frozenset(), language="es", request=request
    )


@pytest.mark.django_db
def test_authenticated_request_gets_its_role_on_that_host(make_user):
    user = make_user(host="a", role="hub_employee")
    ctx_a = HubContextBuilder().from_request(request_for("a.localhost:8000", user))
    # demo is the reference app; the other modules' grants are pinned by their own tests.
    assert {permission for permission in ctx_a.permissions if permission.startswith("demo.")} == {"demo.view"}
    ctx_b = HubContextBuilder().from_request(request_for("b.localhost:8000", user))
    assert ctx_b.actor == user
    assert ctx_b.permissions == frozenset()


@pytest.mark.django_db
def test_superuser_request(superuser):
    assert HubContextBuilder().from_request(request_for("a.localhost", superuser)).permissions == {"*"}


@pytest.mark.django_db
def test_refresh_sees_a_revoked_membership(make_user):
    user = make_user(host="a", role="hub_admin")
    builder = HubContextBuilder()
    ctx = builder.from_request(request_for("a.localhost", user, language="es"))
    assert ctx.has("demo.manage")

    Membership.objects.filter(user=user).delete()
    refreshed = builder.refresh(ctx)

    assert refreshed.permissions == frozenset()
    assert dataclasses.replace(refreshed, permissions=ctx.permissions) == ctx


@pytest.mark.django_db
def test_refresh_sees_a_role_change(make_user):
    user = make_user(host="a", role="hub_employee")
    builder = HubContextBuilder()
    ctx = builder.from_request(request_for("a.localhost", user))
    Membership.objects.filter(user=user).update(role="hub_manager")
    assert builder.refresh(ctx).has("demo.manage")


@pytest.mark.django_db
def test_refresh_rereads_the_user_itself(superuser):
    builder = HubContextBuilder()
    ctx = builder.from_request(request_for("a.localhost", superuser))
    superuser.__class__.objects.filter(pk=superuser.pk).update(is_superuser=False)
    assert builder.refresh(ctx).permissions == frozenset()


@pytest.mark.django_db
def test_refresh_of_a_deactivated_user(make_user):
    user = make_user(host="a", role="hub_admin")
    builder = HubContextBuilder()
    ctx = builder.from_request(request_for("a.localhost", user))
    user.__class__.objects.filter(pk=user.pk).update(is_active=False)
    assert builder.refresh(ctx).permissions == frozenset()


def test_refresh_of_an_anonymous_context():
    builder = HubContextBuilder()
    ctx = builder.from_request(request_for("a.localhost"))
    assert builder.refresh(ctx) == ctx
