"""Membership: which role a user has on a host (phase 1 session, plan §4.4)."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from base.models import Membership

pytestmark = pytest.mark.django_db


def test_key_is_a_uuid7(make_user):
    membership = Membership.objects.create(user=make_user(), host="a", role=Membership.Role.ADMIN)
    assert membership.pk.version == 7


def test_roles_are_the_customer_roles_with_the_hub_prefix():
    assert Membership.Role.values == ["hub_owner", "hub_admin", "hub_manager", "hub_employee"]


def test_one_membership_per_user_and_host(make_user):
    user = make_user(host="a", role="hub_admin")
    Membership.objects.create(user=user, host="b", role="hub_employee")
    with pytest.raises(IntegrityError):
        Membership.objects.create(user=user, host="a", role="hub_employee")


@pytest.mark.parametrize("host", ["a", "bar-1", "x" * 63])
def test_host_is_one_dns_label(make_user, host):
    Membership(user=make_user(), host=host, role="hub_admin").full_clean()


@pytest.mark.parametrize("host", ["a.localhost", "A", "-a", "a-", "", "x" * 64])
def test_host_rejects_anything_but_a_lowercase_label(make_user, host):
    with pytest.raises(ValidationError):
        Membership(user=make_user(), host=host, role="hub_admin").full_clean()


@pytest.mark.parametrize("role", ["owner", "admin", "manager", "employee", "superuser", "support"])
def test_role_must_be_a_prefixed_customer_role(make_user, role):
    with pytest.raises(ValidationError):
        Membership(user=make_user(), host="a", role=role).full_clean()


def test_str(make_user):
    # The UI shows the role's label, never its stored value with the prefix.
    membership = Membership(user=make_user("ana"), host="a", role="hub_manager")
    assert str(membership) == "ana @ a (Manager)"


def test_labels_are_translated_to_spanish():
    from django.utils import translation

    with translation.override("es"):
        assert [str(label) for label in Membership.Role.labels] == [
            "Propietario",
            "Administrador",
            "Encargado",
            "Empleado",
        ]
        assert str(Membership._meta.verbose_name_plural) == "membresías"
        assert str(Membership._meta.get_field("host").verbose_name) == "host"
