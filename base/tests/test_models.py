"""Membership: which role a user has on a host (phase 1 session, plan §4.4)."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from base.models import DemoCode, Hub, Membership

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


# The registry of hubs (docs/plans/2026-10-17-demo-hubs-fase-1.md, §1.1): one row per hub the Hub serves.


class TestHub:
    def test_a_new_hub_is_requested_and_no_demo_with_a_uuid7_key(self):
        hub = Hub.objects.create(slug="acme")
        assert (hub.status, hub.is_demo, hub.expires_at, hub.state, hub.state_version) == (
            "requested",
            False,
            None,
            {},
            0,
        )
        assert hub.pk.version == 7

    def test_the_statuses_are_the_registry_s(self):
        assert Hub.Status.values == ["requested", "ready", "failed", "cancelled", "expired", "purged"]

    def test_a_slug_names_one_hub(self):
        Hub.objects.create(slug="acme")
        with pytest.raises(IntegrityError):
            Hub.objects.create(slug="acme")

    @pytest.mark.parametrize("slug", ["acme", "demo-abcd1234", "x"])
    def test_the_slug_may_be_a_demo_s(self, slug, settings):
        settings.LIVE = {**settings.LIVE, "hub_slug_min_length": 1}
        Hub(slug=slug).full_clean()

    @pytest.mark.parametrize("slug", ["hub", "demo", "Acme", "-x-"])
    def test_the_slug_is_a_hub_s(self, slug):
        with pytest.raises(ValidationError) as caught:
            Hub(slug=slug).full_clean()
        assert "slug" in caught.value.error_dict

    def test_one_live_demo_per_browser_session(self):
        Hub.objects.create(slug="demo-00000001", is_demo=True, status="ready", demo_session_key="k" * 64)
        with pytest.raises(IntegrityError):
            Hub.objects.create(slug="demo-00000002", is_demo=True, status="ready", demo_session_key="k" * 64)

    def test_a_purged_demo_frees_its_session(self):
        Hub.objects.create(slug="demo-00000001", is_demo=True, status="purged", demo_session_key="k" * 64)
        Hub.objects.create(slug="demo-00000002", is_demo=True, status="ready", demo_session_key="k" * 64)

    def test_hubs_without_a_session_key_never_collide(self):
        Hub.objects.create(slug="demo-00000001", is_demo=True, status="ready")
        Hub.objects.create(slug="demo-00000002", is_demo=True, status="ready")

    def test_its_text_is_its_slug(self):
        assert str(Hub(slug="acme")) == "acme"


# The one-time codes into a demo (plan 2026-10-17, §1.1): kept by their sha256 only, several per demo.


class TestDemoCode:
    @pytest.fixture
    def demo(self):
        return Hub.objects.create(slug="demo-0000beef", is_demo=True, status="ready", demo_session_key="k" * 64)

    def test_a_code_is_kept_by_its_hash_with_a_uuid7_key_unused(self, demo):
        from django.utils import timezone

        code = DemoCode.objects.create(hub=demo, code_hash="h" * 64, language="es", expires_at=timezone.now())
        assert (code.used_at, code.language, code.pk.version) == (None, "es", 7)

    def test_one_hash_names_one_code(self, demo):
        from django.utils import timezone

        DemoCode.objects.create(hub=demo, code_hash="h" * 64, expires_at=timezone.now())
        with pytest.raises(IntegrityError):
            DemoCode.objects.create(hub=demo, code_hash="h" * 64, expires_at=timezone.now())

    def test_a_demo_has_several_codes_and_takes_them_with_it(self, demo):
        from django.utils import timezone

        for digit in "12":
            DemoCode.objects.create(hub=demo, code_hash=digit * 64, expires_at=timezone.now())
        assert demo.demo_codes.count() == 2
        demo.delete()
        assert not DemoCode.objects.exists()
