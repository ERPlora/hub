"""The context builder of hub-next phase 1: scope = first label of the Host, permissions by Membership."""

import dataclasses

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import RequestFactory
from live.context import OperationContext, Scope, get_builder

from base.models import Membership
from base.operations import HostScopeResolver, HubContextBuilder, is_demo_hub, is_platform_host


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


# ── HUB_BASE_DOMAIN: a hub is one label on the base domain (plan 2026-10-14-entorno-pre, H-2) ──
# prod (erplora.com) and pre (pre.erplora.com) share one ALB, whose wildcard *.erplora.com also matches
# x.pre.erplora.com: the Hub of one environment never serves a host of the other.


@pytest.fixture
def base_domain(settings):
    """Production's slugs (3 letters at least) under the given base domain; any Host gets past
    ``ALLOWED_HOSTS``, which is not what these tests are about."""
    settings.LIVE = {**settings.LIVE, "hub_slug_min_length": 3}
    settings.ALLOWED_HOSTS = ["*"]

    def use(domain: str) -> None:
        settings.HUB_BASE_DOMAIN = domain

    return use


@pytest.mark.parametrize(
    ("domain", "host", "key"),
    [
        ("erplora.com", "acme.erplora.com", "acme"),
        ("erplora.com", "ACME.Erplora.com:443", "acme"),
        ("pre.erplora.com", "acme.pre.erplora.com", "acme"),
        ("localhost", "acme.localhost:8000", "acme"),
    ],
)
def test_with_a_base_domain_the_hub_is_the_label_on_it(base_domain, domain, host, key):
    base_domain(domain)
    assert HostScopeResolver().resolve(request_for(host)) == Scope("host", key)


@pytest.mark.parametrize(
    ("domain", "host"),
    [
        # pre's hosts on prod's Hub, and prod's on pre's.
        ("erplora.com", "acme.pre.erplora.com"),
        ("erplora.com", "hubs.pre.erplora.com"),
        ("pre.erplora.com", "acme.erplora.com"),
        # The base domain itself, a look-alike and another domain.
        ("erplora.com", "erplora.com"),
        ("pre.erplora.com", "pre.erplora.com"),
        ("erplora.com", "acmeerplora.com"),
        ("erplora.com", "acme.erplora.com.example.org"),
        ("erplora.com", "acme.example.org"),
        ("erplora.com", "acme.localhost:8000"),
        # The private name answers only /readyz (and, later, /internal): no hub there.
        ("erplora.com", "hub.erplora.internal"),
    ],
)
def test_with_a_base_domain_a_host_of_another_domain_is_no_hub(base_domain, domain, host):
    base_domain(domain)
    with pytest.raises(Http404):
        HostScopeResolver().resolve(request_for(host))


def test_pre_is_reserved_for_the_pre_environment(base_domain):
    # pre.erplora.com is pre's SaaS: no customer may take the slug pre (live.slugs).
    base_domain("erplora.com")
    with pytest.raises(Http404):
        HostScopeResolver().resolve(request_for("pre.erplora.com"))


@pytest.mark.parametrize(
    ("domain", "host", "expected"),
    [
        ("erplora.com", "hubs.erplora.com", True),
        ("erplora.com", "HUBS.erplora.com:443", True),
        ("pre.erplora.com", "hubs.pre.erplora.com", True),
        ("localhost", "hubs.localhost:8000", True),
        ("erplora.com", "hubs.pre.erplora.com", False),
        ("pre.erplora.com", "hubs.erplora.com", False),
        ("erplora.com", "hubs.localhost:8000", False),
        ("erplora.com", "hubs.erplora.com.example.org", False),
        ("erplora.com", "hubs.example.org", False),
        ("erplora.com", "erplora.com", False),
    ],
)
def test_the_platform_host_is_hubs_of_the_base_domain_only(base_domain, domain, host, expected):
    base_domain(domain)
    assert is_platform_host(request_for(host)) is expected


def test_without_a_base_domain_the_hub_is_the_first_label_anywhere(base_domain):
    # HUB_BASE_DOMAIN="": the behaviour before 2026-10-14.
    base_domain("")
    assert HostScopeResolver().resolve(request_for("acme.pre.erplora.com")) == Scope("host", "acme")
    assert is_platform_host(request_for("hubs.pre.erplora.com"))


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


def test_phase_one_has_no_demo_hubs():
    # A demo (PLAN-SAAS §3.5) is an ephemeral hub the Hub creates with ``is_demo`` in its control registry
    # (phase 2, block 7). Phase 1 has neither the registry nor demos: no hub is one. Apps ask here, never there.
    assert is_demo_hub(Scope("host", "a")) is False
    assert is_demo_hub(Scope("host", "demo")) is False
