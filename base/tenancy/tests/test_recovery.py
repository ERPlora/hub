"""What a business lost, brought back from one of its separate copies (hub#1257, layer 2 of hub#1213; BASE-F114).

The staff asks it in the Hub admin (``control.copy.recover``: a ``CopyRecovery`` row naming the apps to bring back);
the worker does it (``base.tenancy.recovery.run_due``, in the moves' thread), one a pass, under the row's own lease:

1. the copy is read without making it a business: a direct connection of the migrator, read only, never a hub's alias
   (so nothing scheduled, the VeriFactu queue included, ever runs on it); for each app asked, its ``django_migrations``
   in the copy says first whether the app's read fits the copy's schema;
2. each app says what it gives back (``recoverable_from_copy`` on its ``LiveAppConfig``): its read of the copy, which
   of those records the business lacks, and the operation that creates each;
3. in the business (``use_hub``), each missing record is created by that operation, the one its screen uses: rows are
   never copied. What the operation refuses is noted with why, and the rest go on.

Real databases on the session's server, committed (``hubs.CopiedHubs``): the business's own and its copy, a clone of
it. Customers is the app that answers today.
"""

import datetime as dt
import uuid

import pytest
from django.apps import apps as django_apps
from django.db import connections
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs
from live.models import OutboxEvent
from live.operations import get as get_operation
from psycopg import sql

from base import services
from base.tenancy import connections as tenancy_connections
from base.tenancy import names, recovery
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from control.models import CopyRecovery, Hub, RestoredCopy

pytestmark = pytest.mark.usefixtures("no_test_fallback")

AT = dt.datetime(2026, 11, 12, 9, 0, tzinfo=dt.UTC)
THEN = AT - dt.timedelta(days=2)

ANA = {"name": "Ana López", "phone": "+34600111222", "email": "ana@example.com", "city": "Madrid"}
LUIS = {"name": "Luis Pérez", "phone": "+34600333444", "email": "luis@example.com", "notes": "Prefers mornings"}
MARTA = {"name": "Marta Ruiz", "phone": "+34600555666", "email": "marta@example.com"}


def _context(hub: Hub) -> OperationContext:
    return OperationContext(scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}), language="en")


def run_in(hub: Hub, operation: str, /, **data):
    """The ``operation`` run in ``hub`` as the platform runs it, its result."""
    op = get_operation(operation)
    with use_hub(hub):
        return op(_context(hub), op.input(**data))


def live_cards(hub: Hub) -> list[tuple]:
    """The business's live cards: name, phone, email and city, by name."""
    from apps.customer.models import Customer

    with use_hub(hub):
        return sorted(Customer.objects.live().values_list("name", "phone", "email", "city"))


def created_events(hub: Hub) -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name="customer.customer.created").count()


class Recoveries(hubs.CopiedHubs):
    """The rows and databases of one test: a business with its cards, and separate copies of it."""

    def business(self, every_app_on, *cards: dict) -> tuple[Hub, list[uuid.UUID]]:
        """A ready business on the settings' own server, every app on, with ``cards`` made by Customers' create."""
        hub_id = uuid.uuid7()
        hub = self.ready_hub(hub_id, self.database(hub_id))
        with use_hub(hub):
            every_app_on(hub.slug)
        ids = [run_in(hub, "customer.customer.create", **card).id for card in cards]
        return hub, ids

    def copy_of(self, hub: Hub, *, status: str = RestoredCopy.Status.MADE) -> RestoredCopy:
        """A separate copy of ``hub``'s database as it is now (a clone of it), made, as the worker leaves one."""
        control = tenancy_connections.control_name()
        copy_id = uuid.uuid7()
        name = names.copy_db_name(control, copy_id)
        # A database is only cloned with nobody on it: this thread's connection to the business goes first.
        tenancy_connections.close_hub_aliases(hub)
        with hubs._maintenance() as conn:
            conn.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    names.identifier(name, control=control), names.identifier(hub.db_name, control=control)
                )
            )
        return RestoredCopy.objects.create(
            id=copy_id,
            hub=hub,
            cluster=None,
            restore_point=THEN,
            db_name=name,
            status=status,
            made_at=AT - dt.timedelta(days=1),
            asked_by="root",
        )

    def ask(self, copy: RestoredCopy, *apps: str, **fields) -> CopyRecovery:
        """What ``control.copy.recover`` writes: the apps to bring back from ``copy``, asked by the staff."""
        values = {"copy": copy, "apps": list(apps or ["customer"]), "asked_by": "root", "language": "en"}
        return CopyRecovery.objects.create(**(values | fields))


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


def run(now: dt.datetime = AT, **kwargs) -> int:
    with use_control():
        return recovery.run_due(now, **kwargs)


def fresh(row: CopyRecovery) -> CopyRecovery:
    return CopyRecovery.objects.get(pk=row.pk)


def in_the_copy(copy: RestoredCopy, statement: str, params=()) -> list[tuple]:
    with hubs._maintenance(copy.db_name) as conn:
        cursor = conn.execute(statement, params)
        return cursor.fetchall() if cursor.description else []


CUSTOMERS = {"app": "customer", "created": 0, "not_created": 0, "reasons": [], "refused": ""}


class TestCustomersComeBack:
    def test_the_cards_the_business_lost_come_back_each_created_by_its_operation(self, recoveries, every_app_on):
        hub, (ana, luis, _marta) = recoveries.business(every_app_on, ANA, LUIS, MARTA)
        copy = recoveries.copy_of(hub)
        # Lost since the copy: Ana deleted from her card, Luis's row gone altogether.
        run_in(hub, "customer.customer.delete", id=ana)
        with use_hub(hub):
            from apps.customer.models import Customer

            Customer.objects.filter(pk=luis).delete()
        asked = recoveries.ask(copy)
        before = created_events(hub)

        assert run() == 1

        assert live_cards(hub) == [
            ("Ana López", "+34600111222", "ana@example.com", "Madrid"),
            ("Luis Pérez", "+34600333444", "luis@example.com", ""),
            ("Marta Ruiz", "+34600555666", "marta@example.com", ""),
        ]
        # Through Customers' create, never a copied row: new cards, each with its event.
        with use_hub(hub):
            from apps.customer.models import Customer

            back = Customer.objects.live().filter(name__in=["Ana López", "Luis Pérez"])
            assert not {card.pk for card in back} & {ana, luis}
            assert Customer.objects.get(name="Luis Pérez", deleted_at__isnull=True).notes == "Prefers mornings"
        assert created_events(hub) == before + 2
        done = fresh(asked)
        assert (done.status, done.done_at, done.last_error, done.lease_owner) == ("done", AT, "", "")
        assert done.results == [CUSTOMERS | {"created": 2}]

    def test_asked_again_nothing_is_made_twice(self, recoveries, every_app_on):
        hub, (ana, _luis) = recoveries.business(every_app_on, ANA, LUIS)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        recoveries.ask(copy)
        run()
        again = recoveries.ask(copy)

        assert run() == 1

        assert [card[0] for card in live_cards(hub)] == ["Ana López", "Luis Pérez"]
        assert fresh(again).results == [CUSTOMERS]

    def test_a_card_whose_personal_data_was_erased_or_merged_into_another_never_comes_back(
        self, recoveries, every_app_on
    ):
        hub, (ana, luis, marta) = recoveries.business(every_app_on, ANA, LUIS, MARTA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.erase", id=ana, reason="Asked under GDPR")
        run_in(hub, "customer.customer.merge", id=marta, absorbed_id=luis)
        recoveries.ask(copy)

        assert run() == 1

        assert [card[0] for card in live_cards(hub)] == ["Marta Ruiz"]

    def test_a_card_the_business_made_again_by_hand_is_not_made_once_more(self, recoveries, every_app_on):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        run_in(hub, "customer.customer.create", **ANA)
        asked = recoveries.ask(copy)

        run()

        assert [card[0] for card in live_cards(hub)] == ["Ana López"]
        assert fresh(asked).results == [CUSTOMERS]

    def test_a_card_its_operation_refuses_is_counted_with_why_and_the_others_come_back(self, recoveries, every_app_on):
        hub, (ana, luis) = recoveries.business(every_app_on, ANA, LUIS)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        run_in(hub, "customer.customer.delete", id=luis)
        # In the copy, a phone today's rules do not take.
        in_the_copy(copy, "UPDATE customer_customer SET phone = %s WHERE id = %s", ["12", luis])
        asked = recoveries.ask(copy)

        run()

        assert [card[0] for card in live_cards(hub)] == ["Ana López"]
        [customers] = fresh(asked).results
        assert (customers["created"], customers["not_created"], customers["refused"]) == (1, 1, "")
        [why] = customers["reasons"]
        assert why["id"] == str(luis)
        assert why["reason"].startswith("customer.phone_invalid: ")

    def test_an_app_the_business_turned_off_is_refused_with_why_and_nothing_is_made(self, recoveries, every_app_on):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        with use_hub(hub):
            from base import activation
            from base.models import AppActivation

            AppActivation.objects.filter(host=hub.slug, app="customer").update(state="off")
            activation.forget(hub.slug)
        asked = recoveries.ask(copy)

        run()

        assert live_cards(hub) == []
        [customers] = fresh(asked).results
        assert customers["created"] == 0
        assert customers["refused"].startswith("app_inactive: ")
        assert fresh(asked).status == "done"


class TestTheCopyIsOnlyRead:
    def test_no_alias_reaches_the_copy_and_nothing_in_it_changes(self, recoveries, every_app_on):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        then = in_the_copy(copy, "SELECT id, name, deleted_at FROM customer_customer ORDER BY id")
        recoveries.ask(copy)

        run()

        assert not [alias for alias, found in connections.settings.items() if found.get("NAME") == copy.db_name]
        assert in_the_copy(copy, "SELECT id, name, deleted_at FROM customer_customer ORDER BY id") == then
        with pytest.raises(names.InvalidDatabaseName):
            tenancy_connections.register_hub_alias(type("Copy", (), {"id": uuid.uuid7(), "db_name": copy.db_name})())

    def test_a_read_that_tries_to_write_in_the_copy_is_refused_there(self, recoveries, every_app_on, monkeypatch):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        customers = django_apps.get_app_config("customer")
        [declared] = customers.recoverable_from_copy()

        def writes(conn):
            conn.execute("DELETE FROM customer_customer")
            return declared.read(conn)

        monkeypatch.setattr(
            type(customers), "recoverable_from_copy", lambda self: [type(declared)(**(vars(declared) | {"read": writes}))]
        )
        asked = recoveries.ask(copy)

        run()

        failed = fresh(asked)
        assert failed.status == "failed"
        assert failed.last_error.startswith("recover_copy_unreadable: ")
        assert "read-only" in failed.last_error
        assert in_the_copy(copy, "SELECT count(*) FROM customer_customer") == [(1,)]
        assert live_cards(hub) == []

    def test_a_copy_that_is_gone_fails_with_why(self, recoveries, every_app_on):
        hub, _ids = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        with hubs._maintenance() as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(copy.db_name)))
        asked = recoveries.ask(copy)

        assert run() == 1

        failed = fresh(asked)
        assert (failed.status, failed.results) == ("failed", [])
        assert failed.last_error.startswith("recover_copy_unreadable: ")


class TestTheCopysSchema:
    """Before an app's records are read in the copy, its ``django_migrations`` there says whether its read fits."""

    def lost_ana(self, recoveries, every_app_on) -> tuple[Hub, RestoredCopy]:
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        return hub, copy

    def refused(self, recoveries, copy: RestoredCopy) -> str:
        asked = recoveries.ask(copy)
        run()
        done = fresh(asked)
        assert done.status == "done"
        [customers] = done.results
        assert (customers["created"], customers["not_created"]) == (0, 0)
        return customers["refused"]

    def test_a_copy_without_the_migration_the_read_needs_is_refused(self, recoveries, every_app_on):
        hub, copy = self.lost_ana(recoveries, every_app_on)
        [declared] = django_apps.get_app_config("customer").recoverable_from_copy()
        in_the_copy(copy, "DELETE FROM django_migrations WHERE app = 'customer' AND name = %s", [declared.reads_since])

        assert self.refused(recoveries, copy).startswith("recover_copy_behind: ")
        assert live_cards(hub) == []

    def test_a_copy_with_a_migration_this_code_does_not_know_is_refused(self, recoveries, every_app_on):
        hub, copy = self.lost_ana(recoveries, every_app_on)
        in_the_copy(
            copy, "INSERT INTO django_migrations (app, name, applied) VALUES ('customer', '9999_from_the_future', now())"
        )

        assert self.refused(recoveries, copy).startswith("recover_copy_ahead: ")
        assert live_cards(hub) == []

    def test_an_app_the_copy_never_had_gives_nothing_back(self, recoveries, every_app_on):
        hub, copy = self.lost_ana(recoveries, every_app_on)
        in_the_copy(copy, "DELETE FROM django_migrations WHERE app = 'customer'")

        assert self.refused(recoveries, copy).startswith("recover_not_in_copy: ")
        assert live_cards(hub) == []


class TestTheLease:
    def test_a_recovery_another_worker_holds_is_left_to_it(self, recoveries, every_app_on):
        hub, _ids = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        held = recoveries.ask(copy, lease_owner="other:1", lease_until=AT + dt.timedelta(minutes=5))

        assert run() == 0

        assert fresh(held).status == "asked"

    def test_a_worker_that_lost_its_lease_creates_no_more_and_writes_nothing(
        self, recoveries, every_app_on, monkeypatch
    ):
        hub, (ana, luis) = recoveries.business(every_app_on, ANA, LUIS)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        run_in(hub, "customer.customer.delete", id=luis)
        asked = recoveries.ask(copy)
        op = get_operation("customer.customer.create")
        real = op.fn

        def then_taken(ctx, data):
            made = real(ctx, data)
            with use_control():
                CopyRecovery.objects.filter(pk=asked.pk).update(lease_owner="other:1")
            return made

        monkeypatch.setattr(op, "fn", then_taken)

        run()

        assert len(live_cards(hub)) == 1
        taken = fresh(asked)
        assert (taken.status, taken.results, taken.lease_owner) == ("asked", [], "other:1")

    def test_a_business_being_moved_waits_for_it_with_nothing_done(self, recoveries, every_app_on):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        Hub.objects.filter(pk=hub.pk).update(moving_to=recoveries.cluster("elsewhere"))
        asked = recoveries.ask(copy)

        assert run() == 0

        left = fresh(asked)
        assert (left.status, left.lease_owner, left.results) == ("asked", "", [])
        assert live_cards(hub) == []


def test_only_customers_answer_and_no_app_whose_records_reach_the_tax_authority_ever_does():
    answering = {config.label for config in all_live_app_configs() if hasattr(config, recovery.HOOK)}
    fiscal = {config.label for config in all_live_app_configs() if hasattr(config, "fiscal_record_states")}

    assert answering == {"customer"}
    assert not answering & fiscal
    assert set(recovery.recoverable_apps()) == answering


def test_each_declaration_names_a_migration_of_its_app_and_an_operation_of_its_app():
    from base.tenancy import migrator

    code = migrator.code_migrations()
    for label, declared in recovery.recoverable_apps().items():
        for one in declared:
            assert (label, one.reads_since) in code.nodes
            op = get_operation(one.create)
            assert (op.app_label, op.kind) == (label, "command")


def test_the_lease_is_the_moves():
    from base.tenancy import move

    assert recovery.LEASE == move.LEASE
    assert services.LEASE_OWNER
