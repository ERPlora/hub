"""The person of a business in its own database: ``base.HubUser`` (tenancy W10; PLAN-HUB §3, PLAN-DB §2).

Control keeps the session's user (``auth.User``, the copy ``saas:<id>`` of an erplora.com account) and the role
(``Membership``); the hub's database keeps who signed what in it: a staff record, a task, a clock-in, a message. A key
between two databases does not exist, so the apps hang those from ``HubUser`` (``tests/test_guardrails.py``, «(g)»).

It is made, or brought up to date, at every entry to the hub (the code of erplora.com, a demo, a PIN or a badge), by
the first write of whoever has none yet (``acting_hub_user``) and from the SaaS's photo, which lists the people of
the business before they ever enter. Nobody is deleted: whoever leaves keeps their name on what they signed and is no
longer active. In a hub with its own database it lands there and nowhere else.
"""

import importlib
import uuid
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from live.context import OperationContext, Scope, system_context
from live.errors import NotFound, PermissionDenied
from live.operations import get

from base import queries, services
from base.api_keys import KeyCaller
from base.models import Hub, HubUser, Membership
from base.registry import REGISTRY_SCOPE
from base.schemas import HubStateIn, HubUserGetIn
from base.tenancy import inventory
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_auth_views import callback

pytestmark = pytest.mark.django_db

ANA_ID = uuid.UUID("0199c4b0-0000-7000-8000-00000000a0a0")
OLGA_ID = uuid.UUID("0199c4b0-0000-7000-8000-00000000b0b0")
HUB_ID = uuid.UUID("0199c4b0-0000-7000-8000-0000000000a1")
BETA_ID = uuid.UUID("0199c4b0-0000-7000-8000-0000000000a2")
SYSTEM = system_context(REGISTRY_SCOPE)


def account_copy(saas_id, *, name: str = "Ana López", email: str = "ana@example.com", **fields):
    """The local copy of an erplora.com account, as the login makes it (``saas:<id>``, the name in ``first_name``)."""
    return get_user_model().objects.create_user(
        username=f"saas:{saas_id}", password="pw", first_name=name, email=email, **fields
    )


def as_person(user, host: str = "a") -> OperationContext:
    return OperationContext(scope=Scope("host", host), actor=user, permissions=frozenset({"*"}))


def photo(version: int, *members, hub_id=HUB_ID, slug: str = "acme") -> HubStateIn:
    listed = [
        {"user_id": str(saas_id), "email": email, "name": name, "role": role}
        for saas_id, name, email, role in members
    ]
    body = {"hub_id": str(hub_id), "slug": slug, "version": version, "members": listed}
    return HubStateIn(id=hub_id, version=version, members=listed, photo=body)


class TestTheModel:
    def test_it_lives_in_the_hub_s_database_with_a_uuid7_key(self):
        person = HubUser.objects.create(username="saas:x")

        assert inventory.classify(HubUser) == inventory.HUB
        assert person.pk.version == 7

    def test_it_is_known_by_its_name_else_its_email_else_its_username(self):
        assert HubUser(username="saas:1", name="Ana", email="ana@example.com").display_name == "Ana"
        assert HubUser(username="saas:1", email="ana@example.com").display_name == "ana@example.com"
        assert str(HubUser(username="demo:x")) == "demo:x"


class TestEnsure:
    def test_an_account_s_copy_becomes_its_hub_user_with_its_saas_id_name_and_email(self):
        person = services.ensure_hub_user(account_copy(ANA_ID))

        assert (person.username, person.account_id, person.name, person.email, person.is_active) == (
            f"saas:{ANA_ID}",
            ANA_ID,
            "Ana López",
            "ana@example.com",
            True,
        )

    def test_entering_again_brings_it_up_to_date_and_never_makes_a_second_one(self):
        user = account_copy(ANA_ID)
        first = services.ensure_hub_user(user)
        user.first_name, user.email, user.is_active = "Ana María", "ana.maria@example.com", False
        user.save()

        again = services.ensure_hub_user(user)

        assert again.pk == first.pk and HubUser.objects.count() == 1
        assert (again.name, again.email, again.is_active) == ("Ana María", "ana.maria@example.com", False)

    def test_first_and_last_name_make_the_name(self):
        user = get_user_model().objects.create_user(username="ana", first_name="Ana", last_name="López")

        assert services.ensure_hub_user(user).name == "Ana López"

    @pytest.mark.parametrize("username", ["demo:acme", "saas:42", "ana"])
    def test_a_person_without_an_erplora_com_account_id_has_none(self, username):
        # A demo's owner has no account; the SaaS's ids are UUIDs, so anything else names none.
        user = get_user_model().objects.create_user(username=username)

        assert services.ensure_hub_user(user).account_id is None


class TestTheCaller:
    def test_acting_hub_user_is_the_caller_s_own_and_makes_it_if_missing(self):
        user = account_copy(ANA_ID)

        person = services.acting_hub_user(as_person(user))

        assert person == HubUser.objects.get(username=f"saas:{ANA_ID}")
        assert services.acting_hub_user(as_person(user)) == person

    @pytest.mark.parametrize("actor", ["system", None, "api key"])
    def test_the_platform_an_api_key_or_nobody_is_no_person(self, actor):
        if actor == "api key":
            actor = KeyCaller(key_id=str(uuid.uuid4()), name="Till", prefix="erpk_live_x", permissions=frozenset({"*"}))
        ctx = OperationContext(scope=Scope("host", "a"), actor=actor, permissions=frozenset({"*"}))

        assert services.acting_hub_user(ctx) is None
        assert queries.hub_user_of(ctx) is None
        assert not HubUser.objects.exists()

    def test_hub_user_of_only_reads(self):
        user = account_copy(ANA_ID)

        assert queries.hub_user_of(as_person(user)) is None
        assert not HubUser.objects.exists()
        made = services.ensure_hub_user(user)
        assert queries.hub_user_of(as_person(user)) == made


class TestTheWaysIn:
    def test_the_code_of_erplora_com_makes_the_hub_user(self, client, fake_saas):
        fake_saas(
            body={"user_id": str(ANA_ID), "email": "ana@example.com", "name": "Ana", "locale": "es", "role": "hub_admin"}
        )

        callback(client, {"code": "c1", "next": "/"})

        person = HubUser.objects.get(username=f"saas:{ANA_ID}")
        assert (person.account_id, person.name, person.email) == (ANA_ID, "Ana", "ana@example.com")

    def test_a_demo_entry_makes_its_owner_s(self, rf):
        hub = Hub.objects.create(id=uuid.uuid7(), slug="demo-x1", status="ready")
        request = _with_session(rf.get("/"))

        services.open_demo_session(request, hub)

        person = HubUser.objects.get(username=services.demo_username_for("demo-x1"))
        assert (person.account_id, person.name) == (None, services.DEMO_USER_NAME)

    def test_a_pin_or_a_badge_brings_it_up_to_date(self, client):
        from base.tests.test_access_pin import a_device, pin, with_pin

        user = account_copy(ANA_ID, name="Ana")
        Membership.objects.create(user=user, host="a", role=Membership.Role.EMPLOYEE)
        services.ensure_hub_user(user)
        user.first_name = "Ana María"
        user.save()
        a_device(client)
        credential = with_pin(user, "4826")

        assert pin(client, credential.pk, "4826").status_code == 200
        assert HubUser.objects.get(username=f"saas:{ANA_ID}").name == "Ana María"


def _with_session(request):
    from django.contrib.sessions.backends.db import SessionStore

    request.session = SessionStore()
    request.META["HTTP_HOST"] = "a.localhost"
    return request


class TestThePhoto:
    @pytest.fixture
    def acme(self):
        return Hub.objects.create(id=HUB_ID, slug="acme", status="ready")

    def test_it_makes_the_people_it_lists_before_they_ever_enter(self, acme):
        services.hub_state_apply(
            SYSTEM,
            photo(1, (ANA_ID, "Ana", "ana@example.com", "hub_employee"), (OLGA_ID, "Olga", "", "hub_owner")),
        )

        people = {person.account_id: (person.username, person.name, person.email, person.is_active) for person in HubUser.objects.all()}
        assert people == {
            ANA_ID: (f"saas:{ANA_ID}", "Ana", "ana@example.com", True),
            OLGA_ID: (f"saas:{OLGA_ID}", "Olga", "", True),
        }

    def test_a_later_photo_brings_name_and_email_up_to_date_and_keeps_what_it_does_not_say(self, acme):
        services.hub_state_apply(SYSTEM, photo(1, (ANA_ID, "Ana", "ana@example.com", "hub_employee")))
        listed = photo(2, (ANA_ID, "Ana María", "ana@example.com", "hub_employee"))
        listed.members[0].email = None

        services.hub_state_apply(SYSTEM, listed)

        person = HubUser.objects.get()
        assert (person.name, person.email) == ("Ana María", "ana@example.com")

    def test_whoever_is_no_longer_listed_keeps_their_name_but_is_no_longer_active(self, acme):
        for saas_id in (ANA_ID, OLGA_ID):
            Membership.objects.create(user=account_copy(saas_id, email=""), host="acme", role="hub_employee")
        services.hub_state_apply(
            SYSTEM, photo(1, (ANA_ID, "Ana", "", "hub_employee"), (OLGA_ID, "Olga", "", "hub_owner"))
        )

        services.hub_state_apply(SYSTEM, photo(2, (OLGA_ID, "Olga", "", "hub_owner")))

        assert dict(HubUser.objects.values_list("account_id", "is_active")) == {ANA_ID: False, OLGA_ID: True}
        assert HubUser.objects.get(account_id=ANA_ID).name == "Ana"

    def test_in_the_shared_database_someone_still_in_another_business_stays_active(self, acme):
        Hub.objects.create(id=BETA_ID, slug="beta", status="ready")
        ana = account_copy(ANA_ID)
        Membership.objects.create(user=ana, host="acme", role="hub_employee")
        Membership.objects.create(user=ana, host="beta", role="hub_employee")
        services.hub_state_apply(SYSTEM, photo(1, (ANA_ID, "Ana", "", "hub_employee")))

        services.hub_state_apply(SYSTEM, photo(2))

        assert HubUser.objects.get(account_id=ANA_ID).is_active

    def test_a_photo_without_members_changes_nobody(self, acme):
        services.hub_state_apply(SYSTEM, photo(1, (ANA_ID, "Ana", "", "hub_employee")))

        services.hub_state_apply(SYSTEM, HubStateIn(id=HUB_ID, version=2, photo={"version": 2}))

        assert HubUser.objects.get().is_active


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_in_a_hub_with_its_own_database_the_people_land_there_and_nowhere_else(hub_a, hub_b):
    services.hub_state_apply(SYSTEM, photo(1, (ANA_ID, "Ana", "", "hub_owner"), hub_id=hub_a.id, slug=hub_a.slug))
    user = account_copy(OLGA_ID)
    Membership.objects.create(user=user, host=hub_a.slug, role="hub_employee")
    with use_hub(hub_a):
        services.ensure_hub_user(user)

    with use_hub(hub_a):
        assert set(HubUser.objects.values_list("account_id", flat=True)) == {ANA_ID, OLGA_ID}
    with use_hub(hub_b):
        assert not HubUser.objects.exists()
    assert not HubUser.objects.exists(), "phase 1's shared database got a person of a hub with its own"


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_person_who_leaves_a_hub_with_its_own_database_is_no_longer_active_there(hub_a):
    ana = account_copy(ANA_ID)
    Membership.objects.create(user=ana, host=hub_a.slug, role="hub_employee")
    # Still in a business of the shared database: that one is not this hub's.
    Membership.objects.create(user=ana, host="a", role="hub_employee")
    services.hub_state_apply(SYSTEM, photo(1, (ANA_ID, "Ana", "", "hub_employee"), hub_id=hub_a.id, slug=hub_a.slug))

    services.hub_state_apply(SYSTEM, photo(2, hub_id=hub_a.id, slug=hub_a.slug))

    with use_hub(hub_a):
        assert not HubUser.objects.get(account_id=ANA_ID).is_active


class TestTheMigration:
    """``base/migrations/0020_hub_user``: whoever has a role in a business of the shared database gets their
    ``HubUser`` there; a hub's own database has no control users to read."""

    migration = importlib.import_module("base.migrations.0020_hub_user")

    def test_everyone_with_a_membership_gets_a_hub_user_once(self):
        ana, olga = account_copy(ANA_ID, name="Ana"), account_copy(OLGA_ID, name="Olga", email="olga@example.com")
        for host in ("a", "b"):
            Membership.objects.create(user=ana, host=host, role="hub_employee")
        Membership.objects.create(user=olga, host="a", role="hub_owner")
        get_user_model().objects.create_user(username="saas-staff:7")
        HubUser.objects.create(username=f"saas:{OLGA_ID}", account_id=OLGA_ID, name="Olga")

        self.migration.make_hub_users(django_apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))

        assert sorted(HubUser.objects.values_list("username", "account_id", "name", "email")) == [
            (f"saas:{ANA_ID}", ANA_ID, "Ana", "ana@example.com"),
            (f"saas:{OLGA_ID}", OLGA_ID, "Olga", ""),
        ]

    def test_a_hub_s_own_database_has_nobody_to_read(self, monkeypatch):
        account_copy(ANA_ID)
        monkeypatch.setattr(self.migration.router, "allow_migrate_model", lambda alias, model: False)

        self.migration.make_hub_users(django_apps, SimpleNamespace(connection=SimpleNamespace(alias="hub_x__ddl")))

        assert not HubUser.objects.exists()


class TestTheReadThatNamesThem:
    """``base.hub_user.get``: a person of this business by their id, as the assistant's cards name whoever a write
    links (a staff record's user, a conversation's assignee) instead of by the id."""

    read = staticmethod(lambda ctx, person_id: get("base.hub_user.get")(ctx, HubUserGetIn(id=person_id)))

    def test_it_names_a_person_with_access_to_this_business(self):
        ana = account_copy(ANA_ID, name="Ana López")
        Membership.objects.create(user=ana, host="a", role="hub_employee")
        person = services.ensure_hub_user(ana)

        answer = self.read(as_person(ana), person.pk)

        assert answer.model_dump() == {"id": person.pk, "name": "Ana López"}

    def test_someone_of_another_business_or_nobody_is_not_found(self):
        olga = account_copy(OLGA_ID, name="Olga")
        Membership.objects.create(user=olga, host="b", role="hub_owner")
        elsewhere = services.ensure_hub_user(olga)
        caller = account_copy(ANA_ID)
        Membership.objects.create(user=caller, host="a", role="hub_employee")

        for person_id in (elsewhere.pk, uuid.uuid7()):
            with pytest.raises(NotFound):
                self.read(as_person(caller), person_id)

    def test_it_needs_a_person_of_the_hub(self):
        with pytest.raises(PermissionDenied):
            self.read(OperationContext(scope=Scope("host", "a"), actor=None, permissions=frozenset()), uuid.uuid7())
