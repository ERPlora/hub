"""A business's web address changes (erplora.com's ``PUT /internal/hubs/{id}`` with another slug; HUBS-F16 of the SaaS).

It opens at the new address as it was: the same apps, the same people with their roles, the same figures and the same
events that failed. What was opened at the address it leaves ends there, and whoever takes that address next finds
nothing of it. The businesses are ``hub_a`` and ``hub_b``, each on a database of its own.
"""

import datetime as dt

import pytest
from django.db import IntegrityError, OperationalError
from django.utils import timezone
from live.context import OperationContext, Scope, system_context
from live.models import OutboxEvent
from live.operations import get

from apps.flow.queries import dry_run
from base import activation, queries
from base.models import Hub, Membership
from base.models.access import Credential
from base.models.activation import AppActivation
from base.models.relay import EventDelivery
from base.models.sessions import SessionOwner
from base.permissions import access_for
from base.registry import REGISTRY_SCOPE
from base.services import hub_registry, usage
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HUB_DB, HUB_DB_COMMITTED, A, B
from base.tenancy.tests.concurrency import meanwhile, plan_with_room
from base.tests.test_internal import code, signed
from base.tests.test_session_revoke import ANA, OLGA, REVOKE, alive, login
from control.models.usage import HubVisit

#: Room for two sessions of business A at once.
__all__ = ["plan_with_room"]

pytestmark = HUB_DB

#: Addresses no business of the tests has.
C = Scope("host", "tenant-c")
D = Scope("host", "tenant-d")
#: A business erplora.com registers for the first time.
NEW = "0199c4b0-0000-7000-8000-0000000000c1"
#: An app every template carries that nothing vetoes and no other app of the tests needs.
APP = "task"


def control_gone(*args, **kwargs):
    raise OperationalError("the connection is gone")


@pytest.fixture
def register(client, django_capture_on_commit_callbacks):
    """``register(hub_id, slug)``: erplora.com registers the business at that address, as after every change."""

    client.raise_request_exception = False

    def put(hub_id, slug, **changes):
        business = {"name": "A", "country": "ES", "timezone": "Europe/Madrid", "language": "es", "vertical": None}
        with django_capture_on_commit_callbacks(execute=True):
            return signed(client, "put", f"/internal/hubs/{hub_id}", {**business, "slug": slug, **changes})

    return put


@pytest.fixture
def change_address(register):
    """``change_address(hub, scope)``: the business's row at its new address."""

    def change(hub, scope):
        answer = register(hub.pk, scope.key)
        assert answer.status_code == 200, answer.content
        return Hub.objects.get(pk=hub.pk)

    return change


def run(name, scope, **data):
    op = get(name)
    owner = OperationContext(scope=scope, actor="ana", permissions=frozenset({"*"}), language="en")
    return op(owner, op.input.model_validate(data))


def apps_of(hub) -> dict[str, activation.Activation]:
    with use_hub(hub):
        return activation.states_of(Scope("host", hub.slug))


def off_in(hub) -> frozenset[str]:
    with use_hub(hub):
        return activation.off_apps(Scope("host", hub.slug))


def switch(hub, way: str, app: str = APP) -> None:
    with use_hub(hub):
        run(f"base.app.{way}", Scope("host", hub.slug), app=app)
    activation.forget(hub.slug)


def settle(hub, **how) -> None:
    """The worker's step after making the tables of ``APP`` in ``hub``, as the platform."""
    op = get("base.app.activation_settle")
    worker = OperationContext(scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}), language="en")
    op(worker, op.input.model_validate({"apps": [APP], **how}))


def session_of(saas_id: str, hub) -> dict:
    """What the Hub opens with at ``hub``'s address for a person who enters there as its owner."""
    login(saas_id, hub, role="hub_owner")
    user = Membership.objects.get(user__username=f"saas:{saas_id}", host=hub.slug).user
    scope = Scope("host", hub.slug)
    with use_hub(hub):
        op = get("base.session.me")
        ctx = OperationContext(scope=scope, actor=user, permissions=access_for(user, scope), language="en")
        me = op(ctx, op.input()).model_dump(mode="json")
    return {key: me[key] for key in ("menu", "apps", "permissions", "locked")}


# ── Its apps ─────────────────────────────────────────────────────────────────────────────────────────────────────


class TestItsApps:
    def test_it_opens_at_the_new_address_with_the_apps_it_had_on(self, hub_a, change_address):
        switch(hub_a, "disable")
        before = apps_of(hub_a)
        assert off_in(hub_a) == {APP}

        here = change_address(hub_a, C)

        assert here.slug == C.key
        assert off_in(here) == {APP}
        assert apps_of(here) == before

    def test_whoever_enters_there_finds_the_same_menu(self, hub_a, change_address):
        before = session_of(ANA, hub_a)
        assert before["menu"]

        here = change_address(hub_a, C)

        assert session_of(ANA, here) == before

    def test_an_app_turned_off_or_on_at_the_new_address_is_the_one_it_had(self, hub_a, change_address):
        here = change_address(hub_a, C)

        switch(here, "disable")
        assert off_in(here) == {APP}
        switch(here, "enable")
        assert off_in(here) == frozenset()

    def test_two_changes_in_a_row_keep_what_it_turned_off_in_between(self, hub_a, change_address):
        second = change_address(hub_a, C)
        switch(second, "disable")

        third = change_address(second, D)

        assert off_in(third) == {APP}

    def test_back_at_its_former_address_it_keeps_what_it_turned_off_meanwhile(self, hub_a, change_address):
        assert off_in(hub_a) == frozenset()  # kept in the cache under the address it leaves
        elsewhere = change_address(hub_a, C)
        switch(elsewhere, "disable")

        back = change_address(elsewhere, A)

        assert off_in(back) == {APP}

    def test_an_app_waiting_for_its_tables_still_waits_at_the_new_address(self, hub_a, change_address):
        with use_hub(hub_a):
            AppActivation.objects.filter(app=APP).update(state=activation.CREATING, target="0001_initial")

        here = change_address(hub_a, C)

        with use_hub(here):
            assert queries.apps.activations_due(here.slug, timezone.now()) == {APP: "0001_initial"}
            assert queries.apps.activation_next_at(here.slug) is not None
            settle(here, outcome="created")
        assert off_in(here) == frozenset()

    def test_an_app_that_could_not_go_on_keeps_why_and_when_it_is_tried_again(self, hub_a, change_address):
        at = timezone.now() + dt.timedelta(minutes=5)
        with use_hub(hub_a):
            AppActivation.objects.filter(app=APP).update(
                state=activation.FAILED, attempts=2, last_error="schema_failed: boom", next_attempt_at=at
            )

        here = change_address(hub_a, C)

        with use_hub(here):
            row = AppActivation.objects.get(host=here.slug, app=APP)
        assert (row.state, row.attempts, row.last_error, row.next_attempt_at) == (
            activation.FAILED,
            2,
            "schema_failed: boom",
            at,
        )

    def test_what_another_business_left_in_its_database_is_none_of_its_apps(self, hub_a, change_address):
        """A business whose database was made from the one they shared has the rows of the others in it."""
        with use_hub(hub_a):
            for scope, state in ((C, activation.OFF), (B, activation.OFF)):
                AppActivation.objects.create(host=scope.key, app=APP, state=state, chosen=False)

        assert off_in(change_address(hub_a, C)) == frozenset()

        with use_hub(hub_a):
            assert AppActivation.objects.get(host=B.key, app=APP).state == activation.OFF

    def test_one_the_code_of_before_moved_without_its_apps_finds_them_where_they_were(self, hub_a, change_address):
        Hub.objects.filter(pk=hub_a.pk).update(slug=C.key)
        moved = Hub.objects.get(pk=hub_a.pk)
        assert off_in(moved) == frozenset(activation.module_graph())

        assert off_in(change_address(moved, A)) == frozenset()

    def test_a_change_that_is_undone_leaves_it_open_where_it_was(self, hub_a, register, monkeypatch):
        """Control and the business's database have no transaction in common: its apps are written down at the new
        address before control says it has it, and stay at the one it has until then."""
        switch(hub_a, "disable")
        monkeypatch.setattr(hub_registry, "record_event", control_gone)
        assert register(hub_a.pk, C.key).status_code == 503
        monkeypatch.undo()

        here = Hub.objects.get(pk=hub_a.pk)
        assert (here.slug, off_in(here)) == (A.key, {APP})

        switch(here, "enable")
        assert register(hub_a.pk, C.key).status_code == 200
        assert off_in(Hub.objects.get(pk=hub_a.pk)) == frozenset()

    def test_a_business_whose_database_cannot_be_reached_keeps_its_address(self, client, hub_a, register, monkeypatch):
        session = login(ANA, hub_a, role="hub_owner")
        with monkeypatch.context() as away:
            away.setattr(AppActivation.objects, "bulk_create", control_gone)
            assert register(hub_a.pk, C.key).status_code == 503

        assert Hub.objects.get(pk=hub_a.pk).slug == A.key
        assert signed_in(client, A.key, session)

    def test_one_whose_database_is_still_to_be_made_is_not_entered(self, register):
        assert register(NEW, C.key).status_code == 202

        assert register(NEW, D.key).status_code == 202

        assert Hub.objects.get(pk=NEW).slug == D.key

    def test_a_new_business_at_the_address_it_left_is_born_with_its_own(self, hub_a, hub_b, change_address):
        switch(hub_a, "disable")
        assert off_in(hub_a) == {APP}  # kept in the cache under the address it leaves
        change_address(change_address(hub_a, C), D)
        with use_hub(hub_b):
            AppActivation.objects.all().delete()
            AppActivation.objects.create(host=C.key, app=APP, state=activation.ON, chosen=True)
        Hub.objects.filter(pk=hub_b.pk).update(slug=A.key, country="ES")
        new = Hub.objects.get(pk=hub_b.pk)

        with use_hub(new):
            born = hub_registry.turn_on_born_apps(new)

        assert "tax" in born
        assert off_in(new) == frozenset(activation.module_graph()) - set(born)

    def test_another_business_at_the_address_it_left_has_its_own(self, hub_a, hub_b, change_address):
        switch(hub_a, "disable")
        switch(hub_b, "disable", "attendance")
        gone = change_address(change_address(hub_a, C), D)

        taker = change_address(hub_b, A)

        assert off_in(taker) == {"attendance"}
        assert off_in(gone) == {APP}

    def test_what_the_address_s_former_business_kept_in_the_cache_is_not_the_next_one_s(
        self, hub_a, hub_b, change_address
    ):
        switch(hub_a, "disable")
        assert off_in(hub_a) == {APP}  # kept under the address it leaves
        change_address(change_address(hub_a, C), D)

        assert off_in(change_address(hub_b, A)) == frozenset()




@HUB_DB_COMMITTED
@pytest.mark.usefixtures("plan_with_room")
def test_an_app_being_turned_off_as_the_address_changes_is_off_at_the_new_one(hub_a):
    registered = get("base.hub.register")
    asked = registered.input.model_validate(
        {"id": hub_a.pk, "slug": C.key, "name": "A", "country": "ES", "timezone": "Europe/Madrid", "language": "es", "vertical": None}
    )
    written = 'UPDATE "base_appactivation"'

    with (
        use_hub(hub_a),
        meanwhile(
            lambda sql: sql.lstrip().startswith(written),
            lambda: registered(system_context(REGISTRY_SCOPE), asked),
        ) as outcome,
    ):
        run("base.app.disable", A, app=APP)

    assert not isinstance(outcome[0], Exception), outcome[0]
    assert off_in(Hub.objects.get(pk=hub_a.pk)) == {APP}


# ── Its people ───────────────────────────────────────────────────────────────────────────────────────────────────


def entered(hub) -> dict[str, str]:
    """The people of ``hub`` who already entered it, with their role, as its Employees screen reads them."""
    with use_hub(hub):
        return {person["id"]: person["role"] for person in queries.people.people_of(hub.slug) if person["entered"]}


class TestItsPeople:
    def test_its_people_are_the_same_with_their_roles(self, hub_a, change_address):
        login(ANA, hub_a, role="hub_owner")
        login(OLGA, hub_a, role="hub_manager")
        before = entered(hub_a)
        assert before == {f"saas:{ANA}": "hub_owner", f"saas:{OLGA}": "hub_manager"}

        here = change_address(hub_a, C)

        assert entered(here) == before

    def test_who_has_a_pin_still_enters_with_it(self, hub_a, change_address):
        login(ANA, hub_a)
        with use_hub(hub_a):
            Credential.objects.create(username=f"saas:{ANA}", pin_hash="a-hash")

        here = change_address(hub_a, C)

        with use_hub(here):
            assert [user.get_username() for _, user in queries.access.pin_people(here.slug)] == [f"saas:{ANA}"]

    def test_the_next_photo_still_decides_who_they_are(self, client, hub_a, change_address):
        login(ANA, hub_a, role="hub_owner")
        login(OLGA, hub_a, role="hub_employee")
        here = change_address(hub_a, C)
        photo = {"hub_id": str(here.pk), "slug": here.slug, "version": 1}
        members = [{"user_id": ANA, "email": "a@example.com", "name": "Ana", "role": "hub_admin"}]

        answer = signed(client, "put", f"/internal/hubs/{here.pk}/state", {**photo, "members": members})

        assert answer.json() == {"applied": True, "version": 1}
        assert entered(here) == {f"saas:{ANA}": "hub_admin"}

    def test_nobody_of_the_business_that_left_an_address_is_in_the_one_that_takes_it(
        self, hub_a, hub_b, change_address
    ):
        login(ANA, hub_a, role="hub_owner")
        login(OLGA, hub_b, role="hub_owner")
        gone = change_address(change_address(hub_a, C), D)

        taker = change_address(hub_b, A)

        assert entered(taker) == {f"saas:{OLGA}": "hub_owner"}
        assert entered(gone) == {f"saas:{ANA}": "hub_owner"}

    def test_who_was_left_at_an_address_by_another_business_is_in_none(self, hub_a, hub_b, change_address):
        """The code of before left the people of a business that moved at the address it had."""
        login(ANA, hub_a, role="hub_owner")
        Hub.objects.filter(pk=hub_a.pk).update(slug=D.key)
        login(OLGA, hub_b, role="hub_owner")

        assert entered(change_address(hub_b, A)) == {f"saas:{OLGA}": "hub_owner"}

    def test_who_was_left_at_an_address_is_in_no_new_business_either(self, client, hub_a, register):
        session = login(ANA, hub_a, role="hub_owner")
        Hub.objects.filter(pk=hub_a.pk).update(slug=D.key)
        HubVisit.objects.create(host=A.key, saas_user_id=OLGA, day=dt.date(2026, 3, 10))

        assert register(NEW, A.key).status_code == 202

        assert not alive(session)
        assert not Membership.objects.filter(host=A.key).exists()
        assert not HubVisit.objects.filter(host=A.key).exists()

    def test_a_person_of_two_businesses_keeps_one_role_in_each(self, hub_a, hub_b, change_address):
        login(ANA, hub_a, role="hub_owner")
        login(ANA, hub_b, role="hub_employee")
        gone = change_address(change_address(hub_a, C), D)

        taker = change_address(hub_b, A)

        assert (entered(gone), entered(taker)) == ({f"saas:{ANA}": "hub_owner"}, {f"saas:{ANA}": "hub_employee"})

    def test_who_was_left_at_the_address_it_comes_back_to_has_the_role_they_have_now(self, hub_a, change_address):
        """The code of before left them there with the role they had, and their entry at the next one made another."""
        login(ANA, hub_a, role="hub_employee")
        Hub.objects.filter(pk=hub_a.pk).update(slug=C.key)
        elsewhere = Hub.objects.get(pk=hub_a.pk)
        login(ANA, elsewhere, role="hub_owner")

        assert entered(change_address(elsewhere, A)) == {f"saas:{ANA}": "hub_owner"}


# ── The sessions opened at the address it leaves ─────────────────────────────────────────────────────────────────


def signed_in(client, slug: str, session_key: str) -> bool:
    """Whether a browser with that session is in at that address."""
    client.cookies["sessionid"] = session_key
    return client.get("/api/me", HTTP_HOST=f"{slug}.localhost").json()["user"] is not None


class TestTheSessionsItHad:
    def test_they_end_and_the_tabs_open_there_hear_it(self, hub_a, change_address, monkeypatch):
        from base.services import sessions

        woken = []
        monkeypatch.setattr(sessions, "_wake_open_apps", woken.append)
        session = login(ANA, hub_a)

        change_address(hub_a, C)

        assert not alive(session)
        assert woken == [A.key]

    def test_one_of_a_person_of_both_businesses_is_no_session_of_the_one_that_takes_the_address(
        self, client, hub_a, hub_b, change_address
    ):
        session = login(ANA, hub_a, role="hub_owner")
        login(ANA, hub_b, role="hub_employee")
        change_address(change_address(hub_a, C), D)
        change_address(hub_b, A)

        assert not signed_in(client, A.key, session)

    def test_one_left_by_the_code_of_before_is_no_session_of_the_one_that_takes_the_address(
        self, client, hub_a, hub_b, change_address
    ):
        session = login(ANA, hub_a, role="hub_owner")
        Hub.objects.filter(pk=hub_a.pk).update(slug=D.key)
        change_address(hub_b, A)

        assert not signed_in(client, A.key, session)

    def test_one_the_business_ended_meanwhile_does_not_come_back_with_its_former_address(
        self, client, hub_a, change_address
    ):
        session = login(ANA, hub_a, role="hub_owner")
        elsewhere = change_address(hub_a, C)
        signed(client, "post", REVOKE, {"user_id": ANA, "hub_id": str(hub_a.pk)})
        change_address(elsewhere, A)

        assert not signed_in(client, A.key, session)

    def test_whoever_enters_at_the_new_address_is_in(self, client, hub_a, change_address):
        login(ANA, hub_a, role="hub_owner")
        here = change_address(hub_a, C)

        session = login(ANA, here, role="hub_owner")

        assert signed_in(client, C.key, session)
        assert SessionOwner.objects.get().host == C.key

    def test_those_of_another_business_and_of_its_people_there_go_on(self, client, hub_a, hub_b, change_address):
        login(ANA, hub_a)
        there = login(ANA, hub_b)

        change_address(hub_a, C)

        assert signed_in(client, B.key, there)

    def test_a_change_that_keeps_the_address_ends_none(self, client, hub_a, register):
        session = login(ANA, hub_a, role="hub_owner")

        assert register(hub_a.pk, A.key, name="Another name").status_code == 200

        assert signed_in(client, A.key, session)
        assert entered(hub_a) == {f"saas:{ANA}": "hub_owner"}

    def test_an_address_another_business_has_changes_nothing(self, client, hub_a, hub_b, register):
        session = login(ANA, hub_a, role="hub_owner")

        answer = register(hub_a.pk, B.key)

        assert (answer.status_code, code(answer)) == (409, "base.slug_taken")
        assert signed_in(client, A.key, session)
        assert entered(hub_a) == {f"saas:{ANA}": "hub_owner"}

    def test_an_address_another_business_takes_at_the_same_time_changes_nothing(
        self, client, hub_a, hub_b, register, monkeypatch
    ):
        session = login(ANA, hub_a, role="hub_owner")
        monkeypatch.setattr(Hub, "save", taken_meanwhile)

        answer = register(hub_a.pk, C.key)

        assert (answer.status_code, code(answer)) == (409, "base.slug_taken")
        assert signed_in(client, A.key, session)
        assert entered(hub_a) == {f"saas:{ANA}": "hub_owner"}


def taken_meanwhile(hub, **kwargs):
    raise IntegrityError("another business took it between the check and the write")


# ── Who came in ──────────────────────────────────────────────────────────────────────────────────────────────────


class TestWhoCameIn:
    DAY = dt.date(2026, 3, 10)

    def visit(self, host: str, person: str, day: dt.date) -> None:
        HubVisit.objects.create(host=host, saas_user_id=person, day=day)

    def test_the_people_of_the_day_and_of_the_month_are_the_same(self, hub_a, change_address):
        self.visit(A.key, ANA, self.DAY)
        self.visit(A.key, OLGA, self.DAY - dt.timedelta(days=9))

        here = change_address(hub_a, C)
        self.visit(C.key, OLGA, self.DAY)

        assert usage.active_people(here.slug, self.DAY, 30) == (2, 2)

    def test_another_business_at_the_address_it_left_counts_its_own(self, hub_a, hub_b, change_address):
        self.visit(A.key, ANA, self.DAY)
        self.visit(B.key, OLGA, self.DAY)
        gone = change_address(change_address(hub_a, C), D)

        taker = change_address(hub_b, A)

        assert usage.active_people(taker.slug, self.DAY, 30) == (1, 1)
        assert usage.active_people(gone.slug, self.DAY, 30) == (1, 1)

    def test_what_was_left_at_the_address_it_takes_is_no_visit_of_its_own(self, hub_a, change_address):
        self.visit(A.key, ANA, self.DAY)
        self.visit(C.key, ANA, self.DAY)
        self.visit(C.key, OLGA, self.DAY)

        here = change_address(hub_a, C)

        assert usage.active_people(here.slug, self.DAY, 30) == (1, 1)


# ── Its events ───────────────────────────────────────────────────────────────────────────────────────────────────


def failed_event(scope: Scope = A) -> EventDelivery:
    """A delivery the relay gave up on, recorded at that address in the business at work."""
    event = OutboxEvent.objects.create(
        scope_kind=scope.kind, scope_key=scope.key, name="sale.sale.completed", delivered_at=timezone.now()
    )
    return EventDelivery.objects.create(
        event=event,
        app_label="invoice",
        status=EventDelivery.Status.DEAD,
        attempts=8,
        last_error="Conflict: Set up the issuer first.",
        next_attempt_at=timezone.now(),
    )


class TestItsEvents:
    @pytest.fixture
    def failed(self, hub_a) -> EventDelivery:
        with use_hub(hub_a):
            return failed_event()

    def test_the_failed_ones_are_listed_counted_and_read(self, hub_a, failed, change_address):
        here = change_address(hub_a, C)

        with use_hub(here):
            listed = run("base.failed_event.list", C)
            assert ([item.id for item in listed.items], listed.total) == ([failed.pk], 1)
            assert run("base.failed_event.detail", C, id=failed.pk).id == failed.pk
            assert [entry.id for entry in run("base.event.list", C).entries] == [failed.event_id]
            bell = {counter.key: counter for counter in run("base.bell.counters", C).counters}
            assert "base.failed_events" in bell

    @pytest.mark.parametrize(
        ("command", "status"),
        [("retry", EventDelivery.Status.PENDING), ("discard", EventDelivery.Status.DISCARDED)],
    )
    def test_a_failed_one_is_sent_again_or_discarded(self, hub_a, failed, change_address, command, status):
        here = change_address(hub_a, C)

        with use_hub(here):
            run(f"base.failed_event.{command}", C, id=failed.pk)
            failed.refresh_from_db()
        assert failed.status == status

    def test_the_failed_ones_are_sent_again_at_once(self, hub_a, failed, change_address):
        here = change_address(hub_a, C)

        with use_hub(here):
            assert run("base.failed_event.retry_all", C).count == 1
            failed.refresh_from_db()
        assert failed.status == EventDelivery.Status.PENDING

    def test_another_business_at_the_address_it_left_has_none_of_them(self, hub_a, hub_b, failed, change_address):
        change_address(change_address(hub_a, C), D)
        taker = change_address(hub_b, A)

        with use_hub(taker):
            assert run("base.failed_event.list", A).total == 0
            assert run("base.event.list", A).entries == []

    def test_an_event_of_no_business_is_none_of_its_own(self, hub_a):
        with use_hub(hub_a):
            failed_event(REGISTRY_SCOPE)

            assert run("base.failed_event.list", A).total == 0
            assert run("base.failed_event.retry_all", A).count == 0
            assert run("base.event.list", A).entries == []

    def test_a_flow_is_tried_with_what_last_happened_wherever_it_was(self, hub_a, failed, change_address):
        here = change_address(hub_a, C)
        ctx = OperationContext(scope=C, actor="ana", permissions=frozenset({"*"}), language="en")

        with use_hub(here):
            assert dry_run.sample_of(ctx, "sale.sale.completed")["found"] is True


# ── The photo ────────────────────────────────────────────────────────────────────────────────────────────────────


class TestThePhoto:
    def put(self, client, hub, version: int) -> dict:
        photo = {"hub_id": str(hub.pk), "slug": hub.slug, "version": version}
        return signed(client, "put", f"/internal/hubs/{hub.pk}/state", photo).json()

    def test_its_version_goes_on_from_the_one_kept(self, client, hub_a, change_address):
        assert self.put(client, hub_a, 5) == {"applied": True, "version": 5}

        here = change_address(hub_a, C)

        assert self.put(client, here, 4) == {"applied": False, "version": 5}
        assert self.put(client, here, 5) == {"applied": False, "version": 5}
        assert self.put(client, here, 6) == {"applied": True, "version": 6}

    def test_one_of_the_address_it_left_that_comes_late_is_still_its_own(self, client, hub_a, change_address):
        """The photo is the business's, by its id, whatever address it names."""
        change_address(hub_a, C)

        assert self.put(client, hub_a, 1) == {"applied": True, "version": 1}
