"""What a business lost, brought back from one of its separate copies (hub#1257, layer 2 of hub#1213; BASE-F114).

The staff asks it in the Hub admin (``control.copy.recover``: a ``CopyRecovery`` row naming the apps to bring back);
the worker does it (``base.tenancy.recovery.run_due``, in the moves' thread), one a pass, under the row's own lease:

1. the copy is read without making it a business: a direct connection of the migrator, read only, never a hub's alias
   (so nothing scheduled, the VeriFactu queue included, ever runs on it); for each app asked, its ``django_migrations``
   in the copy says first whether the app's read fits the copy's schema;
2. each app says what it gives back (``recoverable_from_copy`` on its ``LiveAppConfig``): its read of the copy, which
   of those records the business lacks, and the operation that creates each;
3. in the business (``use_hub``), each record it still holds deleted comes back the same, by the app's operation that
   undoes a deletion (with all that hangs from it, hub#1306), and each missing record is created by its create, the one
   its screen uses: rows are never copied. What the operation refuses is noted with why, and the rest go on.

Real databases on the session's server, committed (``hubs.CopiedHubs``): the business's own and its copy, a clone of
it. What every recovery does is tested here, with Customers; what Customers and Appointments bring back, in
``test_recovery_customers.py`` and ``test_recovery_appointments.py``; each other app that answers (Inventory,
hub#1282; Services, hub#1283) tests its own.
"""

import datetime as dt
import uuid

import pytest
from django.apps import apps as django_apps
from django.db import connections
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs
from live.operations import get as get_operation
from ninja import Schema
from psycopg import sql
from pydantic import ConfigDict

from base import recovery as base_recovery
from base.services import provisioning
from base.tenancy import connections as tenancy_connections
from base.tenancy import names, recovery
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from control.models import CopyRecovery, Hub, RestoredCopy

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


def gone(hub: Hub, *cards: uuid.UUID) -> None:
    """``cards``' rows gone altogether from ``hub`` (the Hub admin's «Delete»): what the business no longer has."""
    from apps.customer.models import Customer

    with use_hub(hub):
        Customer.objects.filter(pk__in=cards).delete()


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

    def all_lost(self, every_app_on, *cards: dict) -> tuple[Hub, CopyRecovery]:
        """A business that no longer has any of ``cards`` since its copy, and the recovery asked of that copy."""
        hub, ids = self.business(every_app_on, *cards)
        copy = self.copy_of(hub)
        gone(hub, *ids)
        return hub, self.ask(copy)

    def deleted_with_customers_off(self, every_app_on) -> tuple[Hub, CopyRecovery]:
        """A business that deleted Ana's card since its copy and then turned Customers off, and the recovery asked of
        that copy."""
        hub, (ana,) = self.business(every_app_on, ANA)
        copy = self.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        with use_hub(hub):
            from base import activation
            from base.models.activation import AppActivation

            AppActivation.objects.filter(host=hub.slug, app="customer").update(state="off")
            activation.forget(hub.slug)
        return hub, self.ask(copy)

    def ask(self, copy: RestoredCopy, *apps: str, **fields) -> CopyRecovery:
        """What ``control.copy.recover`` writes: the apps to bring back from ``copy``, asked by the staff."""
        values = {"copy": copy, "apps": list(apps or ["customer"]), "asked_by": "root", "language": "en"}
        return CopyRecovery.objects.create(**(values | fields))


def run(now: dt.datetime = AT, **kwargs) -> int:
    with use_control():
        return recovery.run_due(now, **kwargs)


def fresh(row: CopyRecovery) -> CopyRecovery:
    return CopyRecovery.objects.get(pk=row.pk)


def fields_held_since(label: str, model: str, migration: str) -> set[str]:
    """The fields ``model`` of the app ``label`` holds once ``migration`` is applied: what a read that names it as
    its ``reads_since`` may read of a copy."""
    return set(MigrationLoader(None).project_state((label, migration)).models[label, model].fields)


def in_the_copy(copy: RestoredCopy, statement: str, params=()) -> list[tuple]:
    with hubs._maintenance(copy.db_name) as conn:
        cursor = conn.execute(statement, params)
        return cursor.fetchall() if cursor.description else []


CUSTOMERS = {
    "app": "customer", "label": "Customers", "restored": 0, "created": 0, "not_created": 0, "reasons": [], "refused": ""
}


def test_only_the_actor_of_a_recovery_says_it_brought_something_back():
    """hub#1307: the mark is the recovery's own, never another of the platform's actors (the system, a run of an
    automation, the online booking, a person or an API key)."""
    asked = uuid.uuid7()

    assert base_recovery.actor_of(asked) == f"copy_recovery:{asked}"
    assert base_recovery.brought_back(base_recovery.actor_of(asked))
    others = ["system", "", f"flow_run:{asked}", "online booking", "root", "erpk_live_abc", f"x copy_recovery:{asked}"]
    assert [base_recovery.brought_back(actor) for actor in others] == [False] * len(others)


GROUPS = CUSTOMERS | {"label": "Groups"}


def groups_given_back_too(monkeypatch, missing=list) -> None:
    """Customers declares a second thing it gives back after its cards: the copy's group «VIP», made by
    ``customer.group.create`` when ``missing`` says the business lacks it."""
    from django.utils.translation import gettext_lazy

    from base.recovery import Recoverable

    declared = recovery.recoverable_apps

    def with_groups():
        answers = declared()
        groups = Recoverable(
            label=gettext_lazy("Groups"),
            reads_since="0001_initial",
            read=lambda conn: [{"id": str(uuid.uuid7()), "name": "VIP"}],
            missing=missing,
            create="customer.group.create",
        )
        return answers | {"customer": [*answers["customer"], groups]}

    monkeypatch.setattr(recovery, "recoverable_apps", with_groups)


def live_groups(hub: Hub) -> list[str]:
    with use_hub(hub):
        from apps.customer.models import CustomerGroup

        return list(CustomerGroup.objects.values_list("name", flat=True))


class TestEachThingAnAppGivesBack:
    """An app may declare several things it gives back (a category before what goes in it): each is counted apart,
    under its own name, so Recoveries says how each went."""

    def test_each_is_counted_apart_under_its_name_as_the_code_writes_it(self, recoveries, every_app_on, monkeypatch):
        groups_given_back_too(monkeypatch)
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        gone(hub, ana)
        # Asked by staff who read Spanish: the name is kept as the code writes it, and said in whoever reads it's.
        asked = recoveries.ask(copy, language="es")

        assert run() == 1

        assert fresh(asked).results == [CUSTOMERS | {"created": 1}, GROUPS | {"created": 1}]
        assert live_groups(hub) == ["VIP"]

    def test_what_an_app_reads_while_it_gives_back_knows_the_recovery_at_work_and_nothing_outside_one(
        self, recoveries, every_app_on, monkeypatch
    ):
        seen = []
        groups_given_back_too(monkeypatch, missing=lambda records: seen.append(base_recovery.at_work()) or [])
        hub, _ = recoveries.business(every_app_on, ANA)
        asked = recoveries.ask(recoveries.copy_of(hub))

        assert run() == 1

        assert seen == [base_recovery.actor_of(asked.pk)]
        assert base_recovery.at_work() is None

    def test_asked_again_it_carries_on_the_ones_of_its_copy_that_failed_and_no_other(
        self, recoveries, every_app_on, monkeypatch
    ):
        hub, _ = recoveries.business(every_app_on, ANA)
        copy, other_copy = recoveries.copy_of(hub), recoveries.copy_of(hub)
        failed = recoveries.ask(copy, status=CopyRecovery.Status.FAILED)
        done = recoveries.ask(copy, status=CopyRecovery.Status.DONE)
        failed_elsewhere = recoveries.ask(other_copy, status=CopyRecovery.Status.FAILED)
        asked = recoveries.ask(copy)
        rows = (failed, done, failed_elsewhere, asked)
        seen = []

        def carried(records):
            seen.append([base_recovery.carries_on(base_recovery.actor_of(row.pk)) for row in rows])
            return []

        groups_given_back_too(monkeypatch, missing=carried)

        assert run() == 1

        assert seen == [[True, False, False, False]]
        assert [base_recovery.carries_on(base_recovery.actor_of(row.pk)) for row in rows] == [False] * 4

    def test_what_an_app_refuses_for_all_ends_its_part_and_what_was_left_of_it_says_why(
        self, recoveries, every_app_on, monkeypatch
    ):
        asked_for = []
        groups_given_back_too(monkeypatch, missing=lambda records: asked_for.append(records) or records)
        hub, asked = recoveries.deleted_with_customers_off(every_app_on)

        run()

        [customers, groups] = fresh(asked).results
        assert customers["refused"].startswith("app_inactive: ")
        assert groups == GROUPS | {"refused": customers["refused"]}
        # Never even looked for in the business.
        assert (asked_for, live_groups(hub)) == ([], [])

    def test_an_app_the_copy_cannot_give_back_says_why_for_each_thing_it_declares(
        self, recoveries, every_app_on, monkeypatch
    ):
        groups_given_back_too(monkeypatch)
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        gone(hub, ana)
        in_the_copy(copy, "DELETE FROM django_migrations WHERE app = 'customer'")
        asked = recoveries.ask(copy)

        run()

        why = "recover_not_in_copy: customer was not in the business at the copy's moment"
        assert fresh(asked).results == [CUSTOMERS | {"refused": why}, GROUPS | {"refused": why}]
        assert (live_cards(hub), live_groups(hub)) == ([], [])

    def test_an_app_that_declares_nothing_says_so_as_a_whole(self, recoveries, every_app_on):
        hub, _ = recoveries.business(every_app_on)
        asked = recoveries.ask(recoveries.copy_of(hub), "task")

        assert run() == 1

        why = "recover_not_recoverable: task gives nothing back from a copy"
        assert fresh(asked).results == [
            {"app": "task", "restored": 0, "created": 0, "not_created": 0, "reasons": [], "refused": why}
        ]


def came_back_without(monkeypatch, operation: str, left_out) -> None:
    """``operation`` says, as an app's operation says it (its output mixes in ``base.recovery.RecoveredOut``), what
    each record it brings back came back without: ``left_out(data)``, by its input."""
    op = get_operation(operation)
    real, plain = op.fn, op.output

    class Recovered(plain, base_recovery.RecoveredOut):
        pass

    def saying_what_it_left(ctx, data):
        made = plain.model_validate(real(ctx, data))
        # An output that mixes it in already, as Customers' does, says here what the test makes it say.
        return Recovered(**(made.model_dump() | {"left_out": left_out(data)}))

    monkeypatch.setattr(op, "fn", saying_what_it_left)
    monkeypatch.setattr(op, "output", Recovered)


def left(code: str, message: str):
    return base_recovery.LeftOut(code=code, message=message)


class TestWhatARecordCameBackWithout:
    """A record can come back without something that hung from it (a professional of a service who has left since):
    its operation says so and why, and the recovery notes it by the record's id in the copy, as it notes why one did not
    come back at all."""

    def test_each_is_noted_by_the_records_id_in_the_copy_with_why_and_counted_once_a_record(
        self, recoveries, every_app_on, monkeypatch
    ):
        hub, (ana, luis, marta) = recoveries.business(every_app_on, ANA, LUIS, MARTA)
        copy = recoveries.copy_of(hub)
        # Ana deleted and still held, Luis and Marta gone: only Ana and Luis come back without something.
        gone(hub, luis, marta)
        run_in(hub, "customer.customer.delete", id=ana)
        came_back_without(
            monkeypatch,
            "customer.customer.restore",
            lambda data: [left("customer.test_left_out", "came back without its tag Regular")],
        )
        came_back_without(
            monkeypatch,
            "customer.customer.recover",
            lambda data: [left("customer.test_left_out", f"came back without its group {group}") for group in "AB"]
            if data.name == LUIS["name"]
            else [],
        )
        asked = recoveries.ask(copy)

        run()

        assert fresh(asked).results == [
            CUSTOMERS
            | {
                "restored": 1,
                "created": 2,
                "noted": 2,
                "notes": [
                    {"id": str(ana), "note": "customer.test_left_out: came back without its tag Regular"},
                    {"id": str(luis), "note": "customer.test_left_out: came back without its group A"},
                    {"id": str(luis), "note": "customer.test_left_out: came back without its group B"},
                ],
            }
        ]

    def test_only_the_first_notes_are_kept_and_every_record_noted_is_counted(
        self, recoveries, every_app_on, monkeypatch
    ):
        hub, asked = recoveries.all_lost(every_app_on, ANA, LUIS)
        came_back_without(
            monkeypatch, "customer.customer.recover", lambda data: [left("customer.test_left_out", data.name)]
        )
        monkeypatch.setattr(CopyRecovery, "REASONS_KEPT", 1)

        run()

        [customers] = fresh(asked).results
        assert (customers["created"], customers["noted"], len(customers["notes"])) == (2, 2, 1)

    def test_an_output_that_says_nothing_left_notes_nothing(self, recoveries, every_app_on, monkeypatch):
        hub, asked = recoveries.all_lost(every_app_on, ANA)
        came_back_without(monkeypatch, "customer.customer.recover", lambda data: [])

        run()

        assert fresh(asked).results == [CUSTOMERS | {"created": 1}]


def restore_given(monkeypatch, takes: type[Schema]) -> list[dict]:
    """Customers' restore declares the input ``takes``: each input it is given, in the list returned, and the card
    brought back as its own restore brings it back."""
    op = get_operation("customer.customer.restore")
    real, plain = op.fn, op.input
    given = []

    def keeping_what_it_takes(ctx, data):
        given.append(data.model_dump())
        return real(ctx, plain.model_validate({"id": data.id}))

    monkeypatch.setattr(op, "fn", keeping_what_it_takes)
    monkeypatch.setattr(op, "input", takes)
    return given


class TestWhatARestoreTakes:
    """A restore takes, of the record as the copy holds it, what its input declares: its id, as every restore of an
    app takes it, and whatever else it names to give back to the record what the business lost of it since (a group
    it deleted, hub#1356). An input that refuses a field it does not declare is never given one."""

    def test_a_restore_takes_of_the_record_what_its_input_declares_and_nothing_else(
        self, recoveries, every_app_on, monkeypatch
    ):
        class TakesItsCity(Schema):
            model_config = ConfigDict(extra="forbid")

            id: uuid.UUID
            city: str = ""

        given = restore_given(monkeypatch, TakesItsCity)
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        asked = recoveries.ask(copy)

        run()

        assert fresh(asked).results == [CUSTOMERS | {"restored": 1}]
        assert given == [{"id": ana, "city": "Madrid"}]


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

        writing = type(declared)(**(vars(declared) | {"read": writes}))
        monkeypatch.setattr(type(customers), "recoverable_from_copy", lambda self: [writing])
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
            copy,
            "INSERT INTO django_migrations (app, name, applied) VALUES ('customer', '9999_from_the_future', now())",
        )

        assert self.refused(recoveries, copy).startswith("recover_copy_ahead: ")
        assert live_cards(hub) == []

    def test_an_app_the_copy_never_had_gives_nothing_back(self, recoveries, every_app_on):
        hub, copy = self.lost_ana(recoveries, every_app_on)
        in_the_copy(copy, "DELETE FROM django_migrations WHERE app = 'customer'")

        assert self.refused(recoveries, copy).startswith("recover_not_in_copy: ")
        assert live_cards(hub) == []


def taken_after_each_card(monkeypatch, asked: CopyRecovery) -> None:
    """Another worker takes ``asked``'s lease each time Customers' create has made a card."""
    op = get_operation("customer.customer.create")
    real = op.fn

    def then_taken(ctx, data):
        made = real(ctx, data)
        with use_control():
            CopyRecovery.objects.filter(pk=asked.pk).update(lease_owner="other:1")
        return made

    monkeypatch.setattr(op, "fn", then_taken)


class TestTheLease:
    def test_a_recovery_another_worker_holds_is_left_to_it(self, recoveries, every_app_on):
        hub, _ids = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        # Held by the clock the worker claims it with (``timezone.now()``), never until a fixed moment (hub#1351).
        held = recoveries.ask(copy, lease_owner="other:1", lease_until=timezone.now() + dt.timedelta(minutes=5))

        assert run() == 0

        assert fresh(held).status == "asked"

    def test_a_worker_that_lost_its_lease_creates_no_more_and_writes_nothing(
        self, recoveries, every_app_on, monkeypatch
    ):
        hub, (ana, luis) = recoveries.business(every_app_on, ANA, LUIS)
        copy = recoveries.copy_of(hub)
        gone(hub, ana, luis)
        asked = recoveries.ask(copy)
        taken_after_each_card(monkeypatch, asked)

        run()

        assert len(live_cards(hub)) == 1
        taken = fresh(asked)
        assert (taken.status, taken.results, taken.lease_owner) == ("asked", [], "other:1")

    def test_a_worker_that_lost_its_lease_after_its_last_record_does_not_note_it_done(
        self, recoveries, every_app_on, monkeypatch
    ):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        gone(hub, ana)
        asked = recoveries.ask(copy)
        taken_after_each_card(monkeypatch, asked)

        run()

        assert len(live_cards(hub)) == 1
        taken = fresh(asked)
        assert (taken.status, taken.results, taken.done_at, taken.lease_owner) == ("asked", [], None, "other:1")

    def test_a_worker_that_is_stopping_takes_none(self, recoveries, every_app_on):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        asked = recoveries.ask(copy)

        assert run(cancelled=lambda: True) == 0

        left = fresh(asked)
        assert (left.status, left.lease_owner, left.results) == ("asked", "", [])
        assert live_cards(hub) == []

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


def test_the_apps_that_answer_and_never_one_whose_records_reach_the_tax_authority():
    answering = {config.label for config in all_live_app_configs() if hasattr(config, recovery.HOOK)}
    fiscal = {config.label for config in all_live_app_configs() if hasattr(config, "fiscal_record_states")}

    assert answering == {"combo", "customer", "inventory", "modifier", "pricing", "service", "appointment"}
    assert not answering & fiscal
    assert set(recovery.recoverable_apps()) == answering


def test_each_declaration_names_a_migration_of_its_app_and_an_operation_of_its_app():
    from base.tenancy import migrator

    code = migrator.app_sets.code_migrations()
    for label, declared in recovery.recoverable_apps().items():
        for one in declared:
            assert (label, one.reads_since) in code.nodes
            for name in filter(None, (one.create, one.restore)):
                op = get_operation(name)
                assert (op.app_label, op.kind) == (label, "command")


def test_each_declaration_is_named_in_words_every_language_of_the_staff_says():
    """A result keeps the name of what it counts as the code writes it, and Recoveries says it in the language of
    whoever reads it: so each name is a plain translation (never one with a context), and Spanish has it."""
    from django.utils import translation
    from django.utils.translation import gettext

    for label, declared in recovery.recoverable_apps().items():
        for one in declared:
            with translation.override(None):
                written = str(one.label)
            with translation.override("es"):
                assert gettext(written) == str(one.label) != written, (label, written)


@pytest.mark.parametrize("half", [{"restore": "customer.customer.restore"}, {"deleted": list}])
def test_a_declaration_restores_only_what_it_reads_deleted_and_both_come_together(half):
    from base.recovery import Recoverable

    whole = {"label": "Customers", "reads_since": "0001_initial", "read": list, "missing": list, "create": "c"}
    with pytest.raises(ValueError, match="deleted"):
        Recoverable(**whole, **half)
    assert Recoverable(**whole).restore == ""


def test_the_lease_is_the_moves():
    from base.tenancy import move

    assert recovery.LEASE == move.moving.LEASE
    assert provisioning.LEASE_OWNER
