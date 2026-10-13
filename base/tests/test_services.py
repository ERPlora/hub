"""base.services: the person the SaaS vouched for gets a Hub session (a customer's, or the staff's admin one)."""

import dataclasses

import pytest
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.contrib.sessions.middleware import SessionMiddleware

from base.auth import RedeemedUser
from base.models import Membership
from base.services import (
    SAAS_USER_ID_SESSION_KEY,
    SUPPORT_GROUP,
    InactiveUser,
    open_admin_session_from_saas,
    open_session_from_saas,
)

pytestmark = pytest.mark.django_db

ANA = RedeemedUser(user_id="42", email="ana@example.com", name="Ana", locale="es", role="hub_manager")


@pytest.fixture
def request_(rf):
    request = rf.post("/auth/callback", HTTP_HOST="a.localhost:8000")
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request.user = AnonymousUser()
    return request


def memberships() -> set[tuple[str, str, str]]:
    return set(Membership.objects.values_list("user__username", "host", "role"))


def test_first_entry_creates_the_user_its_role_and_the_session(request_):
    before = request_.session.session_key
    user = open_session_from_saas(request_, ANA, "a")
    assert (user.username, user.email, user.first_name) == ("saas:42", "ana@example.com", "Ana")
    assert not user.has_usable_password()
    assert memberships() == {("saas:42", "a", "hub_manager")}
    assert request_.user == user
    assert request_.session[SESSION_KEY] == str(user.pk)
    assert request_.session[SAAS_USER_ID_SESSION_KEY] == "42"
    assert request_.session.session_key != before  # no session fixation


def test_next_entry_reuses_the_user_and_follows_the_saas(request_):
    first = open_session_from_saas(request_, ANA, "a")
    again = RedeemedUser(user_id="42", email="ana@new.example.com", name="Ana María", locale="en", role="hub_admin")
    second = open_session_from_saas(request_, again, "a")
    assert second.pk == first.pk
    assert (second.email, second.first_name) == ("ana@new.example.com", "Ana María")
    assert get_user_model().objects.count() == 1
    assert memberships() == {("saas:42", "a", "hub_admin")}


def test_each_hub_keeps_its_own_role(request_):
    open_session_from_saas(request_, ANA, "a")
    open_session_from_saas(request_, RedeemedUser("42", "ana@example.com", "Ana", "es", "hub_employee"), "b")
    assert memberships() == {("saas:42", "a", "hub_manager"), ("saas:42", "b", "hub_employee")}


def test_one_person_owns_a_and_works_in_b_and_each_entry_keeps_the_other_role(request_):
    owner_in_a = RedeemedUser("42", "ana@example.com", "Ana", "es", "hub_owner")
    employee_in_b = RedeemedUser("42", "ana@example.com", "Ana", "es", "hub_employee")
    open_session_from_saas(request_, owner_in_a, "a")
    open_session_from_saas(request_, employee_in_b, "b")
    open_session_from_saas(request_, owner_in_a, "a")
    assert memberships() == {("saas:42", "a", "hub_owner"), ("saas:42", "b", "hub_employee")}


def test_a_long_name_fits_the_user(request_):
    user = open_session_from_saas(request_, RedeemedUser("42", "ana@example.com", "A" * 300, "es", "hub_employee"), "a")
    assert user.first_name == "A" * 150


def test_a_user_deactivated_on_the_hub_gets_no_session(request_):
    get_user_model().objects.create_user("saas:42", is_active=False)
    with pytest.raises(InactiveUser):
        open_session_from_saas(request_, ANA, "a")
    assert SESSION_KEY not in request_.session
    assert not request_.user.is_authenticated
    assert memberships() == set()


def test_the_local_copy_of_a_customer_is_never_staff(request_):
    owner = RedeemedUser("42", "ana@example.com", "Ana", "es", "hub_owner")
    user = open_session_from_saas(request_, owner, "a")
    user.refresh_from_db()
    assert (user.is_staff, user.is_superuser) == (False, False)


def test_a_local_copy_raised_to_staff_is_lowered_on_its_next_entry(request_):
    # The Hub's /admin/ belongs to the platform's staff, never to a customer of the SaaS.
    get_user_model().objects.create_user("saas:42", is_staff=True, is_superuser=True)
    user = open_session_from_saas(request_, ANA, "a")
    user.refresh_from_db()
    assert (user.is_staff, user.is_superuser) == (False, False)


# The staff's jump to the Hub admin (audience hub-admin, round 13, PLAN §18.1).
ROOT = RedeemedUser(user_id="7", email="root@erplora.com", name="Root", locale="en", role="platform_admin")
HELP = RedeemedUser(user_id="8", email="help@erplora.com", name="Help", locale="es", role="platform_support")


class TestOpenAdminSession:
    def test_a_platform_admin_is_staff_and_superuser_with_a_new_session(self, request_):
        before = request_.session.session_key
        user = open_admin_session_from_saas(request_, ROOT)
        user.refresh_from_db()
        assert (user.username, user.email, user.first_name) == ("saas-staff:7", "root@erplora.com", "Root")
        assert (user.is_staff, user.is_superuser) == (True, True)
        assert not user.has_usable_password()
        assert request_.user == user
        assert request_.session[SESSION_KEY] == str(user.pk)
        assert request_.session[SAAS_USER_ID_SESSION_KEY] == "7"
        assert request_.session.session_key != before  # no session fixation
        # A platform role is no customer's: no Membership on any hub.
        assert memberships() == set()

    def test_platform_support_is_read_only_staff(self, request_):
        user = open_admin_session_from_saas(request_, HELP)
        user.refresh_from_db()
        assert (user.is_staff, user.is_superuser) == (True, False)
        assert list(user.groups.values_list("name", flat=True)) == [SUPPORT_GROUP]
        codenames = set(Group.objects.get(name=SUPPORT_GROUP).permissions.values_list("codename", flat=True))
        assert codenames == set(Permission.objects.filter(codename__startswith="view_").values_list("codename", flat=True))
        assert user.has_perm("base.view_membership")
        assert not user.has_perm("base.change_membership")
        assert not user.has_perm("auth.add_user")

    def test_the_support_group_stays_read_only(self, request_):
        # A permission added to the group by hand goes away on the next entry of a support member.
        group = Group.objects.create(name=SUPPORT_GROUP)
        group.permissions.add(Permission.objects.get(codename="delete_membership"))
        open_admin_session_from_saas(request_, HELP)
        assert not Group.objects.get(name=SUPPORT_GROUP).permissions.exclude(codename__startswith="view_").exists()

    def test_the_role_follows_the_saas_on_each_entry(self, request_):
        open_admin_session_from_saas(request_, ROOT)
        demoted = RedeemedUser("7", "root@new.erplora.com", "Root B", "en", "platform_support")
        user = open_admin_session_from_saas(request_, demoted)
        user.refresh_from_db()
        assert (user.email, user.first_name, user.is_staff, user.is_superuser) == ("root@new.erplora.com", "Root B", True, False)
        assert user.groups.filter(name=SUPPORT_GROUP).exists()
        promoted = open_admin_session_from_saas(request_, ROOT)
        promoted.refresh_from_db()
        assert (promoted.is_superuser, promoted.groups.exists()) == (True, False)
        assert get_user_model().objects.count() == 1

    def test_a_user_deactivated_on_the_hub_gets_no_admin_session(self, request_):
        get_user_model().objects.create_user("saas-staff:7", is_active=False)
        with pytest.raises(InactiveUser):
            open_admin_session_from_saas(request_, ROOT)
        assert SESSION_KEY not in request_.session
        user = get_user_model().objects.get()
        assert (user.is_staff, user.is_superuser) == (False, False)

    @pytest.mark.parametrize("role", ["hub_owner", "hub_admin", "superuser", ""])
    def test_only_a_platform_role_opens_it(self, request_, role):
        # base.auth already refuses these; the service never trusts its caller with staff.
        with pytest.raises(ValueError, match="platform"):
            open_admin_session_from_saas(request_, RedeemedUser("7", "x@example.com", "X", "en", role))
        assert not get_user_model().objects.exists()


# One SaaS account at both doors (Ioan: platform_admin and owner of his hubs). The customer copy
# ``saas:<id>`` and the staff copy ``saas-staff:<id>`` are two users: an entry by one door never
# lowers the staff copy (a 403 in the Hub admin) nor raises the customer copy (a superuser on a hub).
OWNER_OF_A = RedeemedUser(user_id="7", email="root@erplora.com", name="Root", locale="en", role="hub_owner")
CUSTOMER_COPY, STAFF_COPY = "saas:7", "saas-staff:7"


def local_users() -> dict[str, tuple[bool, bool, list[str]]]:
    """``username → (is_staff, is_superuser, group names)`` of every local user."""
    return {
        user.username: (user.is_staff, user.is_superuser, sorted(user.groups.values_list("name", flat=True)))
        for user in get_user_model().objects.all()
    }


@pytest.mark.parametrize(
    ("staff", "staff_copy"),
    [
        (ROOT, (True, True, [])),
        (dataclasses.replace(ROOT, role="platform_support"), (True, False, [SUPPORT_GROUP])),
    ],
    ids=["platform_admin", "platform_support"],
)
@pytest.mark.parametrize("staff_first", [False, True], ids=["customer_first", "staff_first"])
def test_one_account_at_both_doors_has_a_separate_local_user_at_each(request_, staff, staff_copy, staff_first):
    expected = {CUSTOMER_COPY: (False, False, []), STAFF_COPY: staff_copy}
    doors = [
        (CUSTOMER_COPY, lambda: open_session_from_saas(request_, OWNER_OF_A, "a")),
        (STAFF_COPY, lambda: open_admin_session_from_saas(request_, staff)),
    ]
    if staff_first:
        doors.reverse()
    for username, enter in doors * 2:
        user = enter()
        # After every entry, each copy that exists says only what its own door says.
        assert local_users().items() <= expected.items()
        assert (user.username, request_.user) == (username, user)
    assert local_users() == expected
    # The staff copy is no customer: the hub role stays on the customer copy only.
    assert memberships() == {(CUSTOMER_COPY, "a", "hub_owner")}
