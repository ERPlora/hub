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
it. Customers and Appointments are the apps tested here, in the order of their ``requires``; each other that answers
(Inventory, hub#1282; Services, hub#1283) tests its own.
"""

import datetime as dt
import uuid

import pytest
from django.apps import apps as django_apps
from django.db import connections
from django.utils import timezone
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs
from live.models import OutboxEvent
from live.operations import get as get_operation
from psycopg import sql

from base import recovery as base_recovery
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


def restored_events(hub: Hub) -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name="customer.customer.restored").count()


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
            from base.models import AppActivation

            AppActivation.objects.filter(host=hub.slug, app="customer").update(state="off")
            activation.forget(hub.slug)
        return hub, self.ask(copy)

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


class TestCustomersComeBack:
    def test_the_cards_the_business_lost_come_back_the_deleted_the_same_and_the_gone_created_anew(
        self, recoveries, every_app_on
    ):
        hub, (ana, luis, _marta) = recoveries.business(every_app_on, ANA, LUIS, MARTA)
        copy = recoveries.copy_of(hub)
        # Lost since the copy: Ana deleted from her card, Luis's row gone altogether.
        run_in(hub, "customer.customer.delete", id=ana)
        gone(hub, luis)
        asked = recoveries.ask(copy)
        before = (created_events(hub), restored_events(hub))

        assert run() == 1

        assert live_cards(hub) == [
            ("Ana López", "+34600111222", "ana@example.com", "Madrid"),
            ("Luis Pérez", "+34600333444", "luis@example.com", ""),
            ("Marta Ruiz", "+34600555666", "marta@example.com", ""),
        ]
        # Ana, still in the business, is the same card back by Customers' restore; Luis, gone, a new one by its create:
        # never a copied row, each with its event.
        with use_hub(hub):
            from apps.customer.models import Customer

            assert Customer.objects.live().get(name="Ana López").pk == ana
            again = Customer.objects.live().get(name="Luis Pérez")
            assert (again.pk != luis, again.notes) == (True, "Prefers mornings")
            assert Customer.objects.count() == 3
        assert (created_events(hub), restored_events(hub)) == (before[0] + 1, before[1] + 1)
        done = fresh(asked)
        assert (done.status, done.done_at, done.last_error, done.lease_owner) == ("done", AT, "", "")
        assert done.results == [CUSTOMERS | {"restored": 1, "created": 1}]

    def test_a_card_the_business_deleted_comes_back_with_its_purchases_consents_notes_and_activity(
        self, recoveries, every_app_on
    ):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        run_in(hub, "customer.note.add", customer_id=ana, content="Prefers mornings")
        run_in(
            hub,
            "customer.consent.grant",
            customer_id=ana,
            channel="email",
            notice_text="I want offers.",
            notice_version="v1",
        )
        run_in(hub, "customer.purchase.record", customer_id=ana, sale_id=uuid.uuid7(), total=2500, currency="EUR")
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        recoveries.ask(copy)

        run()

        detail = run_in(hub, "customer.customer.detail", id=ana)
        assert (detail.id, detail.total_purchases, detail.total_spent) == (ana, 1, 2500)
        with use_hub(hub):
            from apps.customer.models import Customer

            back = Customer.objects.live().get()
            assert back.pk == ana
            assert (back.purchases.count(), back.consents.count()) == (1, 1)
            assert back.activity.filter(kind="note_added", text="Prefers mornings").exists()

    def test_every_event_of_what_comes_back_says_the_recovery_did_it_and_one_of_the_business_does_not(
        self, recoveries, every_app_on
    ):
        """hub#1307: the apps' operations run as the recovery (``base.recovery.actor_of``), so each event they record
        keeps it as its actor in the outbox, and what reacts to it tells what came back from what the business does
        (an automation of «customer created» starts nothing for a card brought back, FLOW-F21)."""
        hub, (ana, luis) = recoveries.business(every_app_on, ANA, LUIS)
        # Luis in a group the business keeps and in a deactivated one, with a tag and a custom field's value: the
        # deactivated group, the tag and the field are deleted after the copy, so his card makes them again.
        vip = run_in(hub, "customer.group.create", name="VIP").id
        old = run_in(hub, "customer.group.create", name="Old").id
        regular = run_in(hub, "customer.tag.create", name="Regular").id
        pet = run_in(hub, "customer.field.create", name="Pet").id
        run_in(hub, "customer.customer.set_groups", id=luis, group_ids=[vip, old])
        run_in(hub, "customer.customer.set_tags", id=luis, tag_ids=[regular])
        run_in(hub, "customer.customer.update", id=luis, field_values=[{"field_id": pet, "value": "Luna"}])
        run_in(hub, "customer.group.update", id=old, is_active=False)
        # And a product in its own category: both deleted after the copy, so the category comes back with it inside.
        with use_hub(hub):
            from apps.tax.models import TaxCategory

            tax = TaxCategory.objects.filter(is_active=True).order_by("key").values_list("key", flat=True).first()
        desserts = run_in(hub, "inventory.category.create", name="Desserts").id
        cake = run_in(
            hub, "inventory.product.create", name="Cake", sku="CAK-1", price=400, tax_category_key=tax,
            category_ids=[desserts],
        ).id
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        gone(hub, luis)
        for operation, deleted in (("customer.group.delete", old), ("customer.tag.delete", regular)):
            run_in(hub, operation, id=deleted)
        run_in(hub, "customer.field.delete", id=pet)
        run_in(hub, "inventory.product.delete", id=cake)
        run_in(hub, "inventory.category.delete", id=desserts)
        asked = recoveries.ask(copy, "customer", "inventory")
        with use_hub(hub):
            before = list(OutboxEvent.objects.values_list("pk", flat=True))

        assert run() == 1
        run_in(hub, "customer.customer.create", **MARTA)

        with use_hub(hub):
            recorded = OutboxEvent.objects.exclude(pk__in=before).order_by("created_at", "id")
            said = [(event.name, event.actor) for event in recorded]
        mark = base_recovery.actor_of(asked.pk)
        assert said == [
            ("customer.customer.restored", mark),
            ("customer.customer.created", mark),
            ("customer.group.created", mark),
            ("customer.group.updated", mark),
            ("customer.customer.groups_changed", mark),
            ("customer.tag.created", mark),
            ("customer.customer.tags_changed", mark),
            ("customer.field.created", mark),
            ("inventory.category.created", mark),
            ("inventory.product.categorized", mark),
            ("inventory.product.restored", mark),
            ("customer.customer.created", "system"),
        ]
        assert [base_recovery.brought_back(actor) for _name, actor in said] == [True] * 11 + [False]

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
        asked = recoveries.ask(copy)

        assert run() == 1

        assert [card[0] for card in live_cards(hub)] == ["Marta Ruiz"]
        # Neither restored nor refused: not even asked of Customers.
        assert (restored_events(hub), fresh(asked).results) == (0, [CUSTOMERS])

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
        gone(hub, ana, luis)
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

    def test_what_was_deleted_comes_back_before_anything_is_created_so_the_person_is_not_made_twice(
        self, recoveries, every_app_on
    ):
        # The copy holds Ana twice (the same name, phone and email): the business deleted one and lost the other.
        hub, (deleted, lost) = recoveries.business(every_app_on, ANA, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=deleted)
        gone(hub, lost)
        asked = recoveries.ask(copy)

        run()

        with use_hub(hub):
            from apps.customer.models import Customer

            assert list(Customer.objects.live().values_list("pk", flat=True)) == [deleted]
        assert fresh(asked).results == [CUSTOMERS | {"restored": 1}]

    def test_a_card_its_restore_refuses_is_counted_with_why_and_the_others_come_back(
        self, recoveries, every_app_on, monkeypatch
    ):
        hub, (ana, luis, marta) = recoveries.business(every_app_on, ANA, LUIS, MARTA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        run_in(hub, "customer.customer.merge", id=marta, absorbed_id=luis)
        # Luis held deleted when the business was read, and merged into Marta before his turn came.
        customers = django_apps.get_app_config("customer")
        [declared] = customers.recoverable_from_copy()
        held = type(declared)(**(vars(declared) | {"deleted": lambda cards: [c for c in cards if c["id"] in {ana, luis}]}))
        monkeypatch.setattr(type(customers), "recoverable_from_copy", lambda self: [held])
        asked = recoveries.ask(copy)

        run()

        assert [card[0] for card in live_cards(hub)] == ["Ana López", "Marta Ruiz"]
        [customers_back] = fresh(asked).results
        assert (customers_back["restored"], customers_back["not_created"], customers_back["refused"]) == (1, 1, "")
        [why] = customers_back["reasons"]
        assert why["id"] == str(luis)
        assert why["reason"].startswith("customer.customer_unavailable: ")

    def test_the_reasons_are_said_in_the_language_of_the_staff_who_asked(self, recoveries, every_app_on):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        gone(hub, ana)
        in_the_copy(copy, "UPDATE customer_customer SET phone = %s WHERE id = %s", ["12", ana])
        asked = recoveries.ask(copy, language="es")

        run()

        [customers] = fresh(asked).results
        [why] = customers["reasons"]
        from django.utils import translation

        from apps.customer.services import PHONE_INVALID

        with translation.override("es"):
            assert why["reason"] == f"customer.phone_invalid: {PHONE_INVALID}"
        assert str(PHONE_INVALID) not in why["reason"]

    def test_only_the_first_reasons_are_kept_and_every_card_not_created_is_counted(
        self, recoveries, every_app_on, monkeypatch
    ):
        hub, ids = recoveries.business(every_app_on, ANA, LUIS)
        copy = recoveries.copy_of(hub)
        gone(hub, *ids)
        in_the_copy(copy, "UPDATE customer_customer SET phone = '12'")
        monkeypatch.setattr(CopyRecovery, "REASONS_KEPT", 1)
        asked = recoveries.ask(copy)

        run()

        [customers] = fresh(asked).results
        assert (customers["created"], customers["not_created"], len(customers["reasons"])) == (0, 2, 1)

    def test_an_app_the_business_turned_off_is_refused_with_why_and_nothing_is_made(self, recoveries, every_app_on):
        hub, asked = recoveries.deleted_with_customers_off(every_app_on)

        run()

        assert live_cards(hub) == []
        [customers] = fresh(asked).results
        assert customers["created"] == 0
        assert customers["refused"].startswith("app_inactive: ")
        assert fresh(asked).status == "done"

    def test_a_business_that_is_not_ready_fails_with_why_and_nothing_is_made(self, recoveries, every_app_on):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.CANCELLED)
        asked = recoveries.ask(copy)

        assert run() == 1

        failed = fresh(asked)
        assert (failed.status, failed.results, failed.lease_owner) == ("failed", [], "")
        assert failed.last_error.startswith("recover_business_unavailable: ")
        assert live_cards(hub) == []

    def test_a_failure_halfway_keeps_what_had_come_back_until_then(self, recoveries, every_app_on, monkeypatch):
        hub, asked = recoveries.all_lost(every_app_on, ANA, LUIS)
        op = get_operation("customer.customer.create")
        real, made = op.fn, []

        def breaks_at_the_second(ctx, data):
            if made:
                raise RuntimeError("the business's database went away")
            made.append(real(ctx, data))
            return made[0]

        monkeypatch.setattr(op, "fn", breaks_at_the_second)

        assert run() == 1

        failed = fresh(asked)
        assert failed.status == "failed"
        assert failed.last_error == "recover_unexpected: RuntimeError: the business's database went away"
        # The staff reads what did come back before it broke, not an empty result.
        assert failed.results == [CUSTOMERS | {"created": 1}]
        assert len(live_cards(hub)) == 1


APPOINTMENTS = {
    "app": "appointment",
    "label": "Appointments",
    "restored": 0,
    "created": 0,
    "not_created": 0,
    "reasons": [],
    "refused": "",
}
#: What Appointments gives back after its appointments, its series (hub#1327): none in these tests of appointments.
SERIES = APPOINTMENTS | {"label": "Repeating appointments"}


def a_monday_at(hhmm: str) -> str:
    """A Monday one to two weeks ahead at ``hhmm`` on the business's wall clock: open (09:00–18:00 by default), inside
    the default advance and never in the past."""
    from django.utils import timezone

    today = timezone.localdate()
    monday = today + dt.timedelta(days=(0 - today.weekday()) % 7 + 7)
    return f"{monday.isoformat()}T{hhmm}"


class Salon:
    """A business with its cards (``Recoveries.business``), a professional who takes bookings and a cut."""

    def __init__(self, recoveries, every_app_on, *cards: dict):
        from apps.service.models import Service
        from apps.staff.models import Member

        self.recoveries = recoveries
        self.hub, self.cards = recoveries.business(every_app_on, *cards)
        with use_hub(self.hub):
            self.ines = Member.objects.create(first_name="Inés", last_name="Mora").pk
            self.cut = Service.objects.create(name="Haircut", price=2000, duration_minutes=30).pk

    def book(self, card: uuid.UUID, hhmm: str, **fields):
        """An appointment of ``card`` with Inés for a cut on Monday at ``hhmm``, booked by the agenda's create."""
        return run_in(
            self.hub,
            "appointment.appointment.create",
            customer_id=card,
            staff_id=self.ines,
            services=[{"service_id": self.cut}],
            start=a_monday_at(hhmm),
            **fields,
        )

    def lost_since_a_copy(self, *booked) -> RestoredCopy:
        """A separate copy of the business as it is now, then each of ``booked`` deleted from the agenda since."""
        copy = self.recoveries.copy_of(self.hub)
        for one in booked:
            run_in(self.hub, "appointment.appointment.delete", id=one.id)
        return copy

    def live(self) -> list[tuple]:
        """The business's live appointments: their customer's name, professional, start, minutes, services and notes."""
        from apps.appointment.models import Appointment

        with use_hub(self.hub):
            return [
                (
                    one.customer.name,
                    one.staff_id,
                    one.start,
                    one.duration_minutes,
                    [line.service_id for line in one.lines.all()],
                    one.notes,
                )
                for one in Appointment.objects.filter(deleted_at__isnull=True).order_by("start")
            ]


def booked_events(hub: Hub, name: str = "appointment.appointment.created") -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name=name).count()


def gone_from_the_agenda(hub: Hub, *appointments) -> None:
    """``appointments``' rows gone altogether from ``hub``, with what hangs from them: what the business no longer has
    (no operation destroys an appointment: a lost database does)."""
    from apps.appointment.models import Appointment

    with use_hub(hub):
        Appointment.objects.filter(pk__in=[one.id for one in appointments]).delete()


def the_one_not_booked(asked: CopyRecovery) -> dict:
    """Why the only appointment of ``asked`` that did not come back did not, the others having come back the same: a
    deleted one the restore refuses is never booked anew."""
    [appointments, series] = fresh(asked).results
    assert series == SERIES
    assert (appointments["restored"], appointments["created"], appointments["not_created"], appointments["refused"]) == (
        1,
        0,
        1,
        "",
    )
    [why] = appointments["reasons"]
    return why


class TestAppointmentsComeBack:
    def test_a_deleted_appointment_comes_back_the_same_and_one_gone_is_booked_anew(self, recoveries, every_app_on):
        """hub#1326: the one the business deleted (APPOINTMENT-F11 keeps it) comes back by Appointments' restore, with
        its number and its history; only the one it no longer has is booked again, by the agenda's create."""
        from apps.appointment.models import Appointment

        salon = Salon(recoveries, every_app_on, ANA, LUIS)
        ana, luis = salon.cards
        deleted = salon.book(ana, "10:00", notes="Bring the colour reference")
        lost = salon.book(luis, "11:00", duration_minutes=45)
        then = salon.live()
        copy = salon.lost_since_a_copy(deleted)
        gone_from_the_agenda(salon.hub, lost)
        asked = recoveries.ask(copy, "appointment")
        before = (booked_events(salon.hub), booked_events(salon.hub, "appointment.appointment.restored"))

        assert run() == 1

        assert salon.live() == then
        with use_hub(salon.hub):
            back = Appointment.objects.get(pk=deleted.id)
            assert (back.deleted_at, back.number) == (None, deleted.number)
            assert list(back.history.order_by("at", "id").values_list("action", flat=True)) == [
                "created",
                "deleted",
                "restored",
            ]
            [anew] = Appointment.objects.exclude(pk=deleted.id)
            assert (anew.pk, anew.number) != (lost.id, lost.number)
        assert (booked_events(salon.hub), booked_events(salon.hub, "appointment.appointment.restored")) == (
            before[0] + 1,
            before[1] + 1,
        )
        done = fresh(asked)
        assert (done.status, done.last_error) == ("done", "")
        assert done.results == [APPOINTMENTS | {"restored": 1, "created": 1}, SERIES]

    def test_asked_again_nothing_is_booked_twice(self, recoveries, every_app_on):
        salon = Salon(recoveries, every_app_on, ANA)
        copy = salon.lost_since_a_copy(salon.book(salon.cards[0], "10:00"))
        recoveries.ask(copy, "appointment")
        run()
        again = recoveries.ask(copy, "appointment")

        assert run() == 1

        assert len(salon.live()) == 1
        assert fresh(again).results == [APPOINTMENTS, SERIES]

    def test_one_gone_by_in_the_copy_does_not_come_back(self, recoveries, every_app_on):
        salon = Salon(recoveries, every_app_on, ANA)
        copy = salon.lost_since_a_copy(salon.book(salon.cards[0], "10:00"))
        in_the_copy(
            copy,
            "UPDATE appointment_appointment SET start = now() - interval '1 day', \"end\" = now() - interval '23 hours'",
        )
        asked = recoveries.ask(copy, "appointment")

        run()

        assert salon.live() == []
        assert fresh(asked).results == [APPOINTMENTS, SERIES]

    def test_its_customer_lost_too_comes_back_first_whatever_the_order_they_are_asked_in(self, recoveries, every_app_on):
        salon = Salon(recoveries, every_app_on, ANA)
        copy = salon.lost_since_a_copy(salon.book(salon.cards[0], "10:00"))
        run_in(salon.hub, "customer.customer.delete", id=salon.cards[0])
        # Asked appointments first: they need their customer, so Customers goes before (``requires``).
        asked = recoveries.ask(copy, "appointment", "customer")

        run()

        [(name, *_rest)] = salon.live()
        assert name == "Ana López"
        assert [result["app"] for result in fresh(asked).results] == ["customer", "appointment", "appointment"]
        assert fresh(asked).results[1:] == [APPOINTMENTS | {"restored": 1}, SERIES]

    def test_one_whose_time_was_taken_since_is_never_booked_over_and_says_why_and_the_others_come_back(
        self, recoveries, every_app_on
    ):
        salon = Salon(recoveries, every_app_on, ANA, LUIS, MARTA)
        ana, luis, marta = salon.cards
        taken = salon.book(ana, "10:00")
        copy = salon.lost_since_a_copy(taken, salon.book(luis, "11:00"))
        # Its time given to another customer since, with the same professional.
        salon.book(marta, "10:00")
        asked = recoveries.ask(copy, "appointment")

        run()

        assert [one[0] for one in salon.live()] == ["Marta Ruiz", "Luis Pérez"]
        why = the_one_not_booked(asked)
        assert why["id"] == str(taken.id)
        assert why["reason"].startswith("appointment.slot_taken: ")

    def test_one_whose_customer_the_business_no_longer_has_is_not_made_up_and_says_why(self, recoveries, every_app_on):
        salon = Salon(recoveries, every_app_on, ANA, LUIS)
        ana, luis = salon.cards
        lost = salon.book(ana, "10:00")
        copy = salon.lost_since_a_copy(lost, salon.book(luis, "11:00"))
        run_in(salon.hub, "customer.customer.erase", id=ana, reason="Asked under GDPR")
        asked = recoveries.ask(copy, "appointment")

        run()

        assert [one[0] for one in salon.live()] == ["Luis Pérez"]
        why = the_one_not_booked(asked)
        assert why["id"] == str(lost.id)
        assert why["reason"].startswith("customer.customer_unavailable: ")


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
        return Recovered(**made.model_dump(), left_out=left_out(data))

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
        run_in(hub, "customer.customer.delete", id=ana)
        gone(hub, luis, marta)
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

    assert answering == {"customer", "inventory", "service", "appointment"}
    assert not answering & fiscal
    assert set(recovery.recoverable_apps()) == answering


def test_each_declaration_names_a_migration_of_its_app_and_an_operation_of_its_app():
    from base.tenancy import migrator

    code = migrator.code_migrations()
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

    assert recovery.LEASE == move.LEASE
    assert services.LEASE_OWNER
