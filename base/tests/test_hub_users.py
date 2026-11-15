"""The person of a business in its own database: ``base.HubUser``.

Control keeps the session's user (``auth.User``, the copy ``saas:<id>`` of an erplora.com account) and the role
(``Membership``); the hub's database keeps who signed what in it: a staff record, a task, a clock-in, a message. A key
between two databases does not exist, so the apps hang those from ``HubUser`` (``tests/test_guardrails.py``, «(h)»).

It is made, or brought up to date, at every entry to the hub (the code of erplora.com, a demo, a PIN or a badge), by
the first write of whoever has none yet (``acting_hub_user``) and from the SaaS's photo, which lists the people of
the business before they ever enter. Nobody is deleted: whoever leaves keeps their name on what they signed and is no
longer active. It lands in the business's own database and nowhere else.

The business is ``hub_a``, on a database of its own as every business is; ``B`` is another business.
"""

import importlib
import uuid

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext, Scope, system_context
from live.errors import NotFound, PermissionDenied
from live.operations import get

from base import queries, services
from base.api_keys import KeyCaller
from base.models import HubUser, Membership
from base.registry import REGISTRY_SCOPE
from base.schemas import HubStateIn, HubUserGetIn, SessionMeIn
from base.tenancy import inventory
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_auth_views import A, B, HOST, ON_HUB_A, callback

pytestmark = ON_HUB_A

ANA_ID = uuid.UUID("0199c4b0-0000-7000-8000-00000000a0a0")
OLGA_ID = uuid.UUID("0199c4b0-0000-7000-8000-00000000b0b0")
SYSTEM = system_context(REGISTRY_SCOPE)


def account_copy(saas_id, *, name: str = "Ana López", email: str = "ana@example.com", **fields):
    """The local copy of an erplora.com account, as the login makes it (``saas:<id>``, the name in ``first_name``)."""
    return get_user_model().objects.create_user(
        username=f"saas:{saas_id}", password="pw", first_name=name, email=email, **fields
    )


def as_person(user, host: str = A) -> OperationContext:
    return OperationContext(scope=Scope("host", host), actor=user, permissions=frozenset({"*"}))


def photo(version: int, *members, hub_id=hubs.HUB_A_ID, slug: str = A) -> HubStateIn:
    listed = [
        {"user_id": str(saas_id), "email": email, "name": name, "role": role}
        for saas_id, name, email, role in members
    ]
    body = {"hub_id": str(hub_id), "slug": slug, "version": version, "members": listed}
    return HubStateIn(id=hub_id, version=version, members=listed, photo=body)


class TestTheModel:
    def test_it_lives_in_the_hub_s_database_with_a_uuid7_key(self, hub_a):
        with use_hub(hub_a):
            person = HubUser.objects.create(username="saas:x")

        assert inventory.classify(HubUser) == inventory.HUB
        assert person._state.db == hubs.HUB_A_ALIAS
        assert person.pk.version == 7

    def test_it_is_known_by_its_name_else_its_email_else_its_username(self):
        assert HubUser(username="saas:1", name="Ana", email="ana@example.com").display_name == "Ana"
        assert HubUser(username="saas:1", email="ana@example.com").display_name == "ana@example.com"
        assert str(HubUser(username="demo:x")) == "demo:x"


class TestEnsure:
    def test_an_account_s_copy_becomes_its_hub_user_with_its_saas_id_name_and_email(self, hub_a):
        with use_hub(hub_a):
            person = services.ensure_hub_user(account_copy(ANA_ID))

        assert (person.username, person.account_id, person.name, person.email, person.is_active) == (
            f"saas:{ANA_ID}",
            ANA_ID,
            "Ana López",
            "ana@example.com",
            True,
        )

    def test_entering_again_brings_it_up_to_date_and_never_makes_a_second_one(self, hub_a):
        user = account_copy(ANA_ID)
        with use_hub(hub_a):
            first = services.ensure_hub_user(user)
        user.first_name, user.email, user.is_active = "Ana María", "ana.maria@example.com", False
        user.save()

        with use_hub(hub_a):
            again = services.ensure_hub_user(user)

            assert again.pk == first.pk and HubUser.objects.count() == 1
        assert (again.name, again.email, again.is_active) == ("Ana María", "ana.maria@example.com", False)

    def test_first_and_last_name_make_the_name(self, hub_a):
        user = get_user_model().objects.create_user(username="ana", first_name="Ana", last_name="López")

        with use_hub(hub_a):
            assert services.ensure_hub_user(user).name == "Ana López"

    @pytest.mark.parametrize("username", ["demo:acme", "saas:42", "ana"])
    def test_a_person_without_an_erplora_com_account_id_has_none(self, username, hub_a):
        # A demo's owner has no account; the SaaS's ids are UUIDs, so anything else names none.
        user = get_user_model().objects.create_user(username=username)

        with use_hub(hub_a):
            assert services.ensure_hub_user(user).account_id is None


class TestTheCaller:
    def test_acting_hub_user_is_the_caller_s_own_and_makes_it_if_missing(self, hub_a):
        user = account_copy(ANA_ID)

        with use_hub(hub_a):
            person = services.acting_hub_user(as_person(user))

            assert person == HubUser.objects.get(username=f"saas:{ANA_ID}")
            assert services.acting_hub_user(as_person(user)) == person

    @pytest.mark.parametrize("actor", ["system", None, "api key"])
    def test_the_platform_an_api_key_or_nobody_is_no_person(self, actor, hub_a):
        if actor == "api key":
            actor = KeyCaller(key_id=str(uuid.uuid4()), name="Till", prefix="erpk_live_x", permissions=frozenset({"*"}))
        ctx = OperationContext(scope=Scope("host", A), actor=actor, permissions=frozenset({"*"}))

        with use_hub(hub_a):
            assert services.acting_hub_user(ctx) is None
            assert queries.hub_user_of(ctx) is None
            assert not HubUser.objects.exists()

    def test_hub_user_of_only_reads(self, hub_a):
        user = account_copy(ANA_ID)

        with use_hub(hub_a):
            assert queries.hub_user_of(as_person(user)) is None
            assert not HubUser.objects.exists()
            made = services.ensure_hub_user(user)
            assert queries.hub_user_of(as_person(user)) == made

    def test_hub_user_of_is_the_caller_s_own_and_never_a_colleague_s(self, hub_a):
        ana, olga = account_copy(ANA_ID, name="Ana"), account_copy(OLGA_ID, name="Olga", email="olga@example.com")
        newcomer = account_copy(uuid.uuid7(), name="Eva", email="eva@example.com")
        with use_hub(hub_a):
            ana_s, olga_s = services.ensure_hub_user(ana), services.ensure_hub_user(olga)

            found = [queries.hub_user_of(as_person(user)) for user in (ana, olga, newcomer)]

        assert found == [ana_s, olga_s, None]
        assert [person._state.db for person in found[:2]] == [hubs.HUB_A_ALIAS] * 2


class TestTheWaysIn:
    def test_the_code_of_erplora_com_makes_the_hub_user(self, client, fake_saas, hub_a):
        fake_saas(
            body={"user_id": str(ANA_ID), "email": "ana@example.com", "name": "Ana", "locale": "es", "role": "hub_admin"}
        )

        callback(client, {"code": "c1", "next": "/"})

        with use_hub(hub_a):
            person = HubUser.objects.get(username=f"saas:{ANA_ID}")
        assert (person.account_id, person.name, person.email) == (ANA_ID, "Ana", "ana@example.com")

    def test_a_demo_entry_makes_its_owner_s(self, rf, hub_a):
        request = _with_session(rf.get("/"))

        with use_hub(hub_a):
            services.open_demo_session(request, hub_a)

            person = HubUser.objects.get(username=services.demo_username_for(hub_a.slug))
        assert (person.account_id, person.name) == (None, services.DEMO_USER_NAME)

    def test_a_pin_or_a_badge_brings_it_up_to_date(self, client, hub_a):
        from base.tests.test_access_pin import a_device, pin, with_pin

        user = account_copy(ANA_ID, name="Ana")
        Membership.objects.create(user=user, host=A, role=Membership.Role.EMPLOYEE)
        with use_hub(hub_a):
            services.ensure_hub_user(user)
            a_device(client)
            credential = with_pin(user, "4826")
        user.first_name = "Ana María"
        user.save()

        assert pin(client, credential.pk, "4826").status_code == 200
        with use_hub(hub_a):
            assert HubUser.objects.get(username=f"saas:{ANA_ID}").name == "Ana María"


def _with_session(request):
    from django.contrib.sessions.backends.db import SessionStore

    request.session = SessionStore()
    request.META["HTTP_HOST"] = HOST
    return request


class TestThePhoto:
    def test_it_makes_the_people_it_lists_before_they_ever_enter(self, hub_a):
        services.hub_state_apply(
            SYSTEM,
            photo(1, (ANA_ID, "Ana", "ana@example.com", "hub_employee"), (OLGA_ID, "Olga", "", "hub_owner")),
        )

        with use_hub(hub_a):
            people = {
                person.account_id: (person.username, person.name, person.email, person.is_active)
                for person in HubUser.objects.all()
            }
        assert people == {
            ANA_ID: (f"saas:{ANA_ID}", "Ana", "ana@example.com", True),
            OLGA_ID: (f"saas:{OLGA_ID}", "Olga", "", True),
        }

    def test_a_later_photo_brings_name_and_email_up_to_date_and_keeps_what_it_does_not_say(self, hub_a):
        services.hub_state_apply(SYSTEM, photo(1, (ANA_ID, "Ana", "ana@example.com", "hub_employee")))
        listed = photo(2, (ANA_ID, "Ana María", "ana@example.com", "hub_employee"))
        listed.members[0].email = None

        services.hub_state_apply(SYSTEM, listed)

        with use_hub(hub_a):
            person = HubUser.objects.get()
        assert (person.name, person.email) == ("Ana María", "ana@example.com")

    def test_whoever_is_no_longer_listed_keeps_their_name_but_is_no_longer_active(self, hub_a):
        for saas_id in (ANA_ID, OLGA_ID):
            Membership.objects.create(user=account_copy(saas_id, email=""), host=A, role="hub_employee")
        services.hub_state_apply(
            SYSTEM, photo(1, (ANA_ID, "Ana", "", "hub_employee"), (OLGA_ID, "Olga", "", "hub_owner"))
        )

        services.hub_state_apply(SYSTEM, photo(2, (OLGA_ID, "Olga", "", "hub_owner")))

        with use_hub(hub_a):
            assert dict(HubUser.objects.values_list("account_id", "is_active")) == {ANA_ID: False, OLGA_ID: True}
            assert HubUser.objects.get(account_id=ANA_ID).name == "Ana"

    def test_a_photo_without_members_changes_nobody(self, hub_a):
        services.hub_state_apply(SYSTEM, photo(1, (ANA_ID, "Ana", "", "hub_employee")))

        services.hub_state_apply(SYSTEM, HubStateIn(id=hub_a.id, version=2, photo={"version": 2}))

        with use_hub(hub_a):
            assert HubUser.objects.get().is_active


def test_in_a_hub_with_its_own_database_the_people_land_there_and_nowhere_else(hub_a, hub_b):
    services.hub_state_apply(SYSTEM, photo(1, (ANA_ID, "Ana", "", "hub_owner")))
    user = account_copy(OLGA_ID)
    Membership.objects.create(user=user, host=A, role="hub_employee")
    with use_hub(hub_a):
        services.ensure_hub_user(user)

    with use_hub(hub_a):
        assert set(HubUser.objects.values_list("account_id", flat=True)) == {ANA_ID, OLGA_ID}
    with use_hub(hub_b):
        assert not HubUser.objects.exists()


def test_a_person_who_leaves_a_hub_with_its_own_database_is_no_longer_active_there(hub_a):
    ana = account_copy(ANA_ID)
    Membership.objects.create(user=ana, host=A, role="hub_employee")
    # Still in another business: that one is not this hub's.
    Membership.objects.create(user=ana, host=B, role="hub_employee")
    services.hub_state_apply(SYSTEM, photo(1, (ANA_ID, "Ana", "", "hub_employee")))

    services.hub_state_apply(SYSTEM, photo(2))

    with use_hub(hub_a):
        assert not HubUser.objects.get(account_id=ANA_ID).is_active


class TestTheMigration:
    """``base/migrations/0020_hub_user`` only makes the table: a business's own database holds no control users nor
    roles to read, so its people come at their entry and from the SaaS's photo."""

    def test_it_only_makes_the_table(self):
        migration = importlib.import_module("base.migrations.0020_hub_user").Migration

        assert [operation.describe() for operation in migration.operations] == ["Create model HubUser"]


class TestTheReadThatNamesThem:
    """``base.hub_user.get``: a person of this business by their id, as the assistant's cards name whoever a write
    links (a staff record's user, a conversation's assignee) instead of by the id."""

    @staticmethod
    def read(ctx, person_id):
        return get("base.hub_user.get")(ctx, HubUserGetIn(id=person_id))

    def test_it_names_a_person_with_access_to_this_business(self, hub_a):
        ana = account_copy(ANA_ID, name="Ana López")
        Membership.objects.create(user=ana, host=A, role="hub_employee")
        with use_hub(hub_a):
            person = services.ensure_hub_user(ana)

        with use_hub(hub_a):
            answer = self.read(as_person(ana), person.pk)

        assert answer.model_dump() == {"id": person.pk, "name": "Ana López"}

    def test_someone_of_another_business_or_nobody_is_not_found(self, hub_a, hub_b):
        olga = account_copy(OLGA_ID, name="Olga")
        Membership.objects.create(user=olga, host=B, role="hub_owner")
        # Whoever once entered this business keeps their person in its database after leaving it.
        with use_hub(hub_a):
            left_here = services.ensure_hub_user(olga)
        with use_hub(hub_b):
            of_b = services.ensure_hub_user(olga)
        caller = account_copy(ANA_ID)
        Membership.objects.create(user=caller, host=A, role="hub_employee")

        for person_id in (left_here.pk, of_b.pk, uuid.uuid7()):
            with use_hub(hub_a), pytest.raises(NotFound):
                self.read(as_person(caller), person_id)

    def test_it_needs_a_person_of_the_hub(self, hub_a):
        with use_hub(hub_a), pytest.raises(PermissionDenied):
            self.read(OperationContext(scope=Scope("host", A), actor=None, permissions=frozenset()), uuid.uuid7())


class TestTheSession:
    """``base.session.me``: who the SPA is is the person of the business's database, whose id is the one every app's
    record names (a conversation's assignee, a task's creator), so a screen tells «mine» by it."""

    def me(self, user, hub):
        with use_hub(hub):
            return get("base.session.me")(as_person(user), SessionMeIn()).model_dump(mode="json")["user"]

    def test_its_id_is_the_person_s_of_the_business(self, hub_a):
        ana = account_copy(ANA_ID, name="Ana")
        with use_hub(hub_a):
            person = services.ensure_hub_user(ana)

        assert self.me(ana, hub_a)["id"] == str(person.pk)

    def test_without_a_person_yet_it_is_the_session_s_user(self, hub_a):
        ana = account_copy(ANA_ID, name="Ana")

        assert self.me(ana, hub_a)["id"] == str(ana.pk)
        with use_hub(hub_a):
            assert not HubUser.objects.exists(), "a read never makes a person"


def test_a_demo_entry_that_fails_leaves_no_person_in_the_hub_s_database(hub_a, rf, monkeypatch):
    # The owner's person is the hub's row: written in the hub's transaction (live.operations.atomic), next to
    # control's, so an entry that fails after it takes it back (tests/test_guardrails_atomic.py).
    def refused(*args, **kwargs):
        raise RuntimeError("the session could not be opened")

    monkeypatch.setattr(services, "login", refused)
    with use_hub(hub_a), pytest.raises(RuntimeError):
        services.open_demo_session(_with_session(rf.get("/")), hub_a)

    with use_hub(hub_a):
        assert not HubUser.objects.exists()
