"""Guardrail of the permissions (W11, phase 2; ARCHITECTURE.md §4 «Un solo camino»; Ioan, 2026-10-31).

``live.operations.Operation`` checks ``ctx.has(op.permission)`` before it runs, and ``OperationContext.has(None)`` is
``True``: an ``@operation(..., permission=None)`` runs for anyone with a context on the business (any role, and on a
route with ``auth=None`` nobody at all). Forgetting ``permission=`` therefore opens an operation to every employee. Here
every operation of the Hub without one must be in :data:`OPEN_OPERATIONS`, closed and with its reason; what the list
names must still exist and still be open, so it never rots; and each kind of reason is held to what it promises (an open
command is the platform's alone, refused to a business's owner with every permission; what checks its permissions
itself refuses without them).

The second half pins that ERPlora's staff (``is_staff``/``is_superuser``: maintenance and support, in the Hub admin on
the platform host ``hubs.erplora.com/admin`` and nowhere else) is no customer: a business's ``admin``/``owner`` is a
role of its ``Membership``, never ``is_staff``. Already pinned elsewhere, not repeated here:

- the customer's door never makes nor leaves a staff or superuser copy: ``base/tests/test_services.py`` (
  ``test_the_local_copy_of_a_customer_is_never_staff``, ``test_a_local_copy_raised_to_staff_is_lowered_on_its_next_entry``,
  ``test_one_account_at_both_doors_has_a_separate_local_user_at_each``) and ``base/tests/test_auth_views.py``
  (``TestCallback::test_a_platform_role_never_opens_a_customer_session``);
- the admin is 404 off the platform host for an anonymous visitor and a superuser without a noted host:
  ``base/tests/test_middleware.py`` (``test_the_admin_is_not_found_outside_the_platform_host``).
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from live.context import OperationContext, Scope
from live.errors import PermissionDenied
from live.operations import registry

from base.auth import RedeemedUser
from base.models import Membership
from base.permissions import permissions_for
from base.registry import REGISTRY_SCOPE
from base.services import open_admin_session_from_saas, open_session_from_saas
from control.models import Hub

# ── Why an operation may have no permission ───────────────────────────────────────────────────────────────────────

#: The business's public website, read by its anonymous visitors (``auth=None``): nothing hidden leaves the Hub.
PUBLIC = "public website"
#: What the caller's own session says about itself, and nothing about anyone else.
OWN_SESSION = "own session"
#: The way in of a shared device of the business, shown before anyone is in.
DEVICE_DOOR = "device door"
#: The platform's alone (the SaaS through the signed ``/internal``, the worker, a ``manage.py`` command, the Hub
#: admin): the operation refuses anyone else itself (``base.registry.internal_only``).
PLATFORM = "platform"
#: It needs one of several permissions, which one operation cannot name: it checks them itself, first.
CHECKED_INSIDE = "checked inside"

#: Every operation of the Hub without a permission, with its reason: ``name → (kind, why)``. Closed on purpose: a new
#: one is either given its permission or added here with a reason a reviewer can weigh.
OPEN_OPERATIONS: dict[str, tuple[str, str]] = {
    "base.access.door": (
        DEVICE_DOOR,
        "The PIN pad of a trusted shared device, before anyone signs in (BASE-G55): names and initials of who may "
        "enter with a PIN there, never an email or an account; anyone else hears it with nobody in it.",
    ),
    "base.demo.code_create": (PLATFORM, "The SaaS asks for the one-time entry code of a demo (/internal)."),
    "base.demo.create": (PLATFORM, "The SaaS opens a demo (/internal)."),
    "base.demo.expire": (
        PLATFORM,
        "manage.py demo_expire, and the Hub admin's «Expire now» for the platform's admins (staff and superuser).",
    ),
    "base.demo.get": (PLATFORM, "manage.py demo_expire reads the demo's status once done."),
    "base.demo.purge": (PLATFORM, "The worker's reaper and manage.py demo_expire purge an ended demo."),
    "base.hub.by_slugs": (PLATFORM, "seed_local_hubs --check reads the registry's status of a and b."),
    "base.hub.cancel": (PLATFORM, "The SaaS cancels a business (/internal)."),
    "base.hub.dump_list": (
        PLATFORM,
        "The SaaS reads the copies of a business's data and their links of 15 minutes (/internal/hubs/{id}/dumps).",
    ),
    "base.hub.get": (PLATFORM, "The SaaS reads a registry row it never heard ready from (/internal)."),
    "base.hub.register": (PLATFORM, "The SaaS registers or renames a business (/internal)."),
    "base.hub.reset_apply": (
        PLATFORM,
        "The worker empties the sections of a reset whose copy it kept (base.worker), in the business's own database.",
    ),
    "base.hub.restore": (PLATFORM, "The SaaS restores a cancelled business (/internal)."),
    "base.hub.seed_local": (PLATFORM, "seed_local_hubs registers a and b, in local development only (DEBUG)."),
    "base.hub.state_apply": (PLATFORM, "The SaaS's photo of a business: plan, apps, members and roles (/internal)."),
    "base.hub_user.sync": (PLATFORM, "Inside the photo's own transaction: the people of the business's database."),
    "base.session.me": (
        OWN_SESSION,
        "The SPA's own session, read at start: an anonymous visitor gets no user and no permission (the login).",
    ),
    "base.session.revoke": (PLATFORM, "The SaaS ends an account's sessions (/internal, back-channel logout)."),
    "base.usage.list": (
        PLATFORM,
        "The SaaS's collect_hub_usage reads what each business used on a day, measured that night (/internal/usage).",
    ),
    "staff.account.list": (
        CHECKED_INSIDE,
        "staff.add_member or staff.change_member (the «Hub user» selector of the record's form, STAFF-F03).",
    ),
    "staff.member.current": (
        OWN_SESSION,
        "The caller's own staff record, its id and name only, never the pay: a cashier who does not see the team "
        "still sells as herself (SALE-F16).",
    ),
    "website.public.catalog": (PUBLIC, "The published website's catalogue, for its visitors."),
    "website.public.reviews": (PUBLIC, "The published website's reviews, for its visitors."),
    "website.public.site": (PUBLIC, "The published website, for its visitors."),
}

KINDS = frozenset({PUBLIC, OWN_SESSION, DEVICE_DOOR, PLATFORM, CHECKED_INSIDE})

HOW_TO_FIX = (
    "Give each the permission its callers must hold (`permission=\"<app>.<action>\"`, declared in the app's "
    "`permissions` and granted in its `role_permissions`). Only if anyone with a session on the business, or the "
    "public, may run it on purpose, add it to OPEN_OPERATIONS in tests/test_guardrails_permissions.py with its kind "
    "and its reason."
)


def open_in_the_registry() -> set[str]:
    return {name for name, op in registry.items() if op.permission is None}


def of_kind(kind: str) -> list[str]:
    return sorted(name for name, (listed_kind, _) in OPEN_OPERATIONS.items() if listed_kind == kind)


def test_every_operation_without_a_permission_is_listed_with_its_reason():
    unlisted = sorted(open_in_the_registry() - OPEN_OPERATIONS.keys())
    assert not unlisted, (
        f"These operations run for any employee of the business (or anyone, on a public route): {unlisted}. "
        + HOW_TO_FIX
    )


def test_the_list_names_only_operations_that_exist_and_are_still_open():
    gone = sorted(name for name in OPEN_OPERATIONS if name not in registry)
    closed = sorted(name for name in OPEN_OPERATIONS if name in registry and registry[name].permission is not None)
    assert not gone, f"OPEN_OPERATIONS names operations that no longer exist: {gone}. Take them out of the list."
    assert not closed, f"These operations have a permission now: {closed}. Take them out of OPEN_OPERATIONS."


def test_every_reason_says_its_kind_and_why():
    for name, (kind, why) in OPEN_OPERATIONS.items():
        assert kind in KINDS, f"{name}: {kind!r} is no kind of reason ({sorted(KINDS)})."
        assert why.strip(), f"{name}: say why it needs no permission."


def test_an_open_command_is_the_platform_s_alone():
    # Anyone may read what is theirs or public; nobody but the platform writes without a permission.
    writes = sorted(
        name
        for name, (kind, _) in OPEN_OPERATIONS.items()
        if name in registry and registry[name].kind != "query" and kind != PLATFORM
    )
    assert not writes, f"These commands would let any employee write: {writes}. " + HOW_TO_FIX


def an_owner_of_a() -> object:
    user = get_user_model().objects.create_user(username="saas:1")
    Membership.objects.create(user=user, host="a", role=Membership.Role.OWNER)
    return user


@pytest.mark.django_db
@pytest.mark.parametrize("name", of_kind(PLATFORM))
def test_the_platform_s_operations_refuse_a_business_s_owner_with_every_permission(name):
    # The worst case on a business's host: its owner, holding every permission there is.
    op = registry[name]
    ctx = OperationContext(scope=Scope("host", "a"), actor=an_owner_of_a(), permissions=frozenset({"*"}))
    with pytest.raises(PermissionDenied) as refused:
        op(ctx, op.input.model_construct())
    assert refused.value.code == "base.internal_only"


@pytest.mark.django_db
@pytest.mark.parametrize("name", of_kind(CHECKED_INSIDE))
def test_what_checks_its_permissions_itself_refuses_without_them(name):
    # The positive side (who holds one of them reads) is each app's own test (apps/staff/tests/test_queries.py,
    # test_accounts_for_whoever_adds_or_edits_records).
    op = registry[name]
    employee = get_user_model().objects.create_user(username="saas:2")
    Membership.objects.create(user=employee, host="a", role=Membership.Role.EMPLOYEE)
    ctx = OperationContext(scope=Scope("host", "a"), actor=employee, permissions=frozenset())
    with pytest.raises(PermissionDenied):
        op(ctx, op.input.model_construct())


# ── ERPlora's staff is no customer ────────────────────────────────────────────────────────────────────────────────

HUB_HOST = "a.localhost:8000"
PLATFORM_HOST = "hubs.localhost:8000"
A = Scope("host", "a")
#: One SaaS account (Ioan's): the platform's admin, and the owner of a business.
ROOT_AS_STAFF = RedeemedUser(user_id="7", email="root@erplora.com", name="Root", locale="en", role="platform_admin")
ROOT_AS_OWNER = RedeemedUser(user_id="7", email="root@erplora.com", name="Root", locale="en", role="hub_owner")


def door_request(host: str) -> object:
    """The callback's request on ``host``, with its session, as ``base.middleware`` leaves it."""
    request = RequestFactory().post("/auth/callback", HTTP_HOST=host)
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request.user = AnonymousUser()
    request.platform_host = host == PLATFORM_HOST
    if not request.platform_host:
        request.hub = Hub.objects.get(slug="a")
    return request


def with_the_session_of(client, request) -> None:
    request.session.save()
    client.cookies["sessionid"] = request.session.session_key


def staff_session(client) -> object:
    """``client`` with the staff's session of the Hub admin, opened on the platform host as the SaaS vouched."""
    request = door_request(PLATFORM_HOST)
    user = open_admin_session_from_saas(request, ROOT_AS_STAFF)
    with_the_session_of(client, request)
    return user


def customer_session(client) -> object:
    """``client`` with the owner's session of business ``a``, opened on its host as the SaaS vouched."""
    request = door_request(HUB_HOST)
    user = open_session_from_saas(request, ROOT_AS_OWNER, "a")
    with_the_session_of(client, request)
    return user


def me(client, host=HUB_HOST) -> dict:
    return client.get("/api/me", HTTP_HOST=host).json()


@pytest.mark.django_db
def test_a_staff_session_on_a_business_s_host_is_anonymous_and_never_holds_everything(client, settings):
    settings.SAAS_URL = "http://localhost:8001"
    staff = staff_session(client)
    assert (staff.is_staff, staff.is_superuser) == (True, True)
    assert client.get("/admin/", HTTP_HOST=PLATFORM_HOST).status_code == 200  # it is a session where it was opened

    assert client.get("/api/demo/items", HTTP_HOST=HUB_HOST).status_code == 401
    assert (me(client)["user"], me(client)["permissions"]) == (None, [])
    page = client.get("/demo/items", HTTP_HOST=HUB_HOST, HTTP_ACCEPT="text/html")
    assert (page.status_code, b'id="hub-jump"' in page.content) == (200, True)  # the jump to the SaaS's login


@pytest.mark.django_db
def test_on_a_business_s_host_a_superuser_holds_only_what_its_membership_there_gives():
    staff = get_user_model().objects.create_user("saas-staff:7", is_staff=True, is_superuser=True)
    assert permissions_for(staff, A) == frozenset()

    raised = get_user_model().objects.create_user("saas:7", is_staff=True, is_superuser=True)
    Membership.objects.create(user=raised, host="a", role=Membership.Role.EMPLOYEE)
    plain = get_user_model().objects.create_user("saas:8")
    Membership.objects.create(user=plain, host="a", role=Membership.Role.EMPLOYEE)
    assert permissions_for(raised, A) == permissions_for(plain, A)
    assert "*" not in permissions_for(raised, A)


@pytest.mark.django_db
def test_the_superuser_s_wildcard_is_the_platform_s_alone():
    staff = get_user_model().objects.create_user("saas-staff:7", is_staff=True, is_superuser=True)
    assert permissions_for(staff, REGISTRY_SCOPE) == {"*"}
    assert permissions_for(get_user_model().objects.create_user("saas:8"), REGISTRY_SCOPE) == frozenset()


@pytest.mark.django_db
def test_a_staff_session_from_before_the_host_rule_holds_nothing_on_a_business_s_host(client):
    # A session with no host noted (opened before S1's rule) stays valid where it is used until it expires: on a
    # business's host the staff copy is one more user without a Membership there.
    staff = get_user_model().objects.create_user("saas-staff:7", is_staff=True, is_superuser=True)
    client.force_login(staff)

    assert client.get("/api/demo/items", HTTP_HOST=HUB_HOST).status_code == 403
    assert me(client)["permissions"] == []


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/admin/", "/admin/base/membership/", "/admin/hub/a/"])
def test_the_admin_is_not_found_on_a_business_s_host_with_a_customer_s_or_the_staff_s_session(client, path):
    customer_session(client)
    assert client.get("/api/demo/items", HTTP_HOST=HUB_HOST).status_code == 200  # the owner's session works there
    for method in (client.get, client.post):
        response = method(path, HTTP_HOST=HUB_HOST)
        assert (response.status_code, response.has_header("Location")) == (404, False)

    staff_session(client)
    for method in (client.get, client.post):
        response = method(path, HTTP_HOST=HUB_HOST)
        assert (response.status_code, response.has_header("Location")) == (404, False)
