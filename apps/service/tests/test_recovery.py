"""What Services gives back from a separate copy of the business (hub#1283; BASE-F114, SERVICE-F01).

The platform reads the copy (``base.tenancy.recovery``) through a direct, read-only connection: the copy is no
business, so it has no alias and the ORM never reaches it. Services answers it (``recoverable_from_copy`` on its
config) with its own read, by SQL over its model's names (``queries.services_in_copy``): each service the copy offers,
with what its create takes, its category and its tax category by their ids there. Then, in the business, which of those
it holds (``queries.services_in_business``): the same service, offered or archived (a service is never deleted,
SERVICE-F04), or one it made again, the same name in the same category; the others it lacks
(``queries.services_not_in_business``), each as ``service.service.create`` takes it here: the key of its tax category
and its category while the business still has it. Each is created by that operation, the screen's own.
"""

import uuid

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone
from live.errors import InvalidPayload
from live.models import OutboxEvent
from live.operations import get

from apps.service import queries
from apps.service.models import Service
from apps.service.schemas import ServiceIn
from apps.tax.models import TaxCategory
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import Recoveries, fresh, run, run_in

from .conftest import ctx_for, make_category, make_service, make_tax

pytestmark = pytest.mark.django_db


def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


def create(record: dict) -> dict:
    """``record`` created as the platform does: its create's input, all of it but its id in the copy."""
    op = get("service.service.create")
    return op(ctx_for(), op.input.model_validate({key: value for key, value in record.items() if key != "id"}))


def test_the_copy_gives_each_service_with_what_its_create_takes_and_whether_it_was_on_offer():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    keratin = make_service(
        "Keratin treatment",
        tax=tax,
        price=9000,
        category=hair,
        description="Smooths the hair for months.",
        short_description="Smoothing",
        pricing_type="from",
        min_price=9000,
        max_price=15000,
        cost=2500,
        duration_minutes=90,
        buffer_before=5,
        buffer_after=10,
        max_capacity=2,
        is_bookable=False,
        requires_confirmation=True,
        allow_online_booking=False,
        sort_order=3,
        is_featured=True,
        sku="KER-01",
        barcode="8412345678905",
        notes="Ask about allergies",
        image="service/services/keratin.webp",
    )
    old = make_service("Old perm", tax=tax, is_active=False, archived_at=timezone.now())

    read, archived = sorted(queries.services_in_copy(direct()), key=lambda one: one["name"] != "Keratin treatment")

    assert (archived["id"], archived["name"], archived["is_active"]) == (old.pk, "Old perm", False)
    assert read == {
        "id": keratin.pk,
        "name": "Keratin treatment",
        "pricing_type": "from",
        "price": 9000,
        "min_price": 9000,
        "max_price": 15000,
        "cost": 2500,
        "duration_minutes": 90,
        "buffer_before": 5,
        "buffer_after": 10,
        "max_capacity": 2,
        "description": "Smooths the hair for months.",
        "short_description": "Smoothing",
        "is_bookable": False,
        "requires_confirmation": True,
        "allow_online_booking": False,
        "sort_order": 3,
        "is_featured": True,
        "sku": "KER-01",
        "barcode": "8412345678905",
        "notes": "Ask about allergies",
        "category_id": hair.pk,
        "tax_category_id": tax.pk,
        "is_active": True,
    }


def test_a_copy_without_the_apps_table_gives_nothing():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE service_service CASCADE")

    assert queries.services_in_copy(direct()) == []


#: A service of the copy with what a new one has, as ``services_in_copy`` gives it.
NEW = {
    "name": "",
    "pricing_type": "fixed",
    "price": 0,
    "min_price": None,
    "max_price": None,
    "cost": 0,
    "duration_minutes": 60,
    "buffer_before": 0,
    "buffer_after": 0,
    "max_capacity": 1,
    "description": "",
    "short_description": "",
    "is_bookable": True,
    "requires_confirmation": False,
    "allow_online_booking": True,
    "sort_order": 0,
    "is_featured": False,
    "sku": "",
    "barcode": "",
    "notes": "",
    "category_id": None,
    "tax_category_id": None,
    "is_active": True,
}


def a_service_of_the_copy(service: Service | None = None, **fields) -> dict:
    """A service as the copy gives it (``services_in_copy``): ``service``'s, or a new one with ``fields``."""
    if service is not None:
        return {"id": service.pk} | {field: getattr(service, field) for field in NEW}
    return {"id": uuid.uuid7()} | NEW | fields


def test_the_business_holds_the_same_service_offered_or_archived_and_one_made_again_in_the_same_category():
    tax = make_tax()
    hair, nails = make_category("Hair"), make_category("Nails")
    offered = make_service("Haircut", tax=tax, category=hair)
    archived = make_service("Old perm", tax=tax, is_active=False, archived_at=timezone.now())
    made_again = make_service("Blow-dry", tax=tax, category=hair)
    made_again_archived = make_service("Beard trim", tax=tax, is_active=False, archived_at=timezone.now())
    services = [
        a_service_of_the_copy(offered),
        # Archived and renamed since: still the same one, by its id.
        a_service_of_the_copy(archived),
        # Gone, and made again by hand since: the same name in the same category, the case and the spaces aside.
        again := a_service_of_the_copy(name="  BLOW-DRY ", category_id=hair.pk),
        # Gone, and made again with no category; then archived: still the business's.
        again_archived := a_service_of_the_copy(name="Beard trim"),
        # Gone: the same name is another service in another category.
        other_category := a_service_of_the_copy(name="Haircut", category_id=nails.pk),
        # Gone altogether.
        absent := a_service_of_the_copy(name="Manicure", category_id=nails.pk),
    ]

    Service.objects.filter(pk=archived.pk).update(name="Perm (old)")

    held = queries.services_in_business(services)

    assert held == {
        offered.pk: offered.pk,
        archived.pk: archived.pk,
        again["id"]: made_again.pk,
        again_archived["id"]: made_again_archived.pk,
    }
    assert [one["id"] for one in queries.services_not_in_business(services)] == [other_category["id"], absent["id"]]


def test_a_lost_service_named_as_one_the_business_kept_in_the_same_category_is_lacking():
    tax = make_tax()
    hair = make_category("Hair")
    kept = make_service("Haircut", tax=tax, category=hair)
    # Service names are not unique: the kept one is itself a service of the copy, never another's made again.
    services = [a_service_of_the_copy(kept), lost := a_service_of_the_copy(name="Haircut", category_id=hair.pk)]

    assert queries.services_in_business(services) == {kept.pk: kept.pk}
    assert [one["id"] for one in queries.services_not_in_business(services)] == [lost["id"]]


def test_a_lost_service_named_as_one_the_copy_had_archived_is_lacking():
    tax = make_tax()
    archived = make_service("Haircut", tax=tax, is_active=False, archived_at=timezone.now())
    services = [
        a_service_of_the_copy(archived),
        lost := a_service_of_the_copy(name="Haircut"),
    ]

    assert queries.services_in_business(services) == {archived.pk: archived.pk}
    assert [one["id"] for one in queries.services_not_in_business(services)] == [lost["id"]]


def test_each_one_made_again_stands_for_one_service_of_the_copy_the_oldest_first():
    tax = make_tax()
    hair = make_category("Hair")
    first, second = (a_service_of_the_copy(name="Haircut", category_id=hair.pk) for _ in range(2))
    older = make_service("Haircut", tax=tax, category=hair)

    # One made again: it stands for the first of the copy; the second is still lacking.
    assert queries.services_in_business([first, second]) == {first["id"]: older.pk}
    assert [one["id"] for one in queries.services_not_in_business([first, second])] == [second["id"]]

    newer = make_service("haircut", tax=tax, category=hair)

    assert queries.services_in_business([first, second]) == {first["id"]: older.pk, second["id"]: newer.pk}
    assert queries.services_not_in_business([first, second]) == []


def test_two_lost_with_the_same_name_both_come_back_and_asking_again_makes_neither_twice():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    copy = [
        a_service_of_the_copy(name="Haircut", category_id=hair.pk, tax_category_id=tax.pk, price=2000),
        a_service_of_the_copy(name="Haircut", category_id=hair.pk, tax_category_id=tax.pk, price=2500),
    ]
    first = create(queries.services_not_in_business(copy)[0])
    # Cut after the first (the lease lost): the next pass still brings back the second.
    [second] = [create(record) for record in queries.services_not_in_business(copy)]

    assert (first.price, second.price) == (2000, 2500)
    assert queries.services_not_in_business(copy) == []
    assert queries.services_in_business(copy) == {copy[0]["id"]: first.id, copy[1]["id"]: second.id}


def test_a_service_the_copy_had_archived_never_comes_back():
    tax = make_tax("test.service", "Service — test")
    archived = a_service_of_the_copy(name="Old perm", tax_category_id=tax.pk, is_active=False)

    assert queries.services_in_business([archived]) == {}
    assert queries.services_not_in_business([archived]) == []


def test_one_whose_category_the_business_deleted_is_made_again_with_no_category():
    tax = make_tax()
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    without = make_service("Highlights", tax=tax)
    services = [a_service_of_the_copy(name="Highlights", category_id=gone.pk)]

    # It would come back with no category, and the business has it there already.
    assert queries.services_in_business(services) == {services[0]["id"]: without.pk}


def test_each_lacking_service_comes_as_its_create_takes_it_here():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    in_hair = a_service_of_the_copy(
        name="Keratin treatment",
        category_id=hair.pk,
        tax_category_id=tax.pk,
        pricing_type="from",
        price=9000,
        min_price=9000,
        max_price=15000,
        duration_minutes=90,
        sku="KER-01",
        notes="Ask about allergies",
    )
    in_gone = a_service_of_the_copy(name="Highlights", category_id=gone.pk, tax_category_id=tax.pk, price=4500)

    lacking = queries.services_not_in_business([in_hair, in_gone])

    assert lacking[0] == {
        key: value for key, value in in_hair.items() if key not in {"category_id", "tax_category_id", "is_active"}
    } | {"category_id": hair.pk, "tax_category_key": "test.service"}
    assert lacking[1] == {
        key: value for key, value in in_gone.items() if key not in {"category_id", "tax_category_id", "is_active"}
    } | {"tax_category_key": "test.service"}
    for record in lacking:
        ServiceIn.model_validate({key: value for key, value in record.items() if key != "id"})


def test_the_lacking_are_created_by_the_screens_operation_and_asking_again_makes_none_twice():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    copy = [
        a_service_of_the_copy(
            name="Keratin treatment",
            category_id=hair.pk,
            tax_category_id=tax.pk,
            price=9000,
            duration_minutes=90,
        ),
        a_service_of_the_copy(name="Manicure", tax_category_id=tax.pk, price=1500, duration_minutes=30),
    ]

    created = [create(record) for record in queries.services_not_in_business(copy)]

    assert [(one.name, one.price, one.duration_minutes, one.category_id, one.tax_category_key) for one in created] == [
        ("Keratin treatment", 9000, 90, hair.pk, "test.service"),
        ("Manicure", 1500, 30, None, "test.service"),
    ]
    assert queries.services_not_in_business(copy) == []
    assert queries.services_in_business(copy) == {copy[0]["id"]: created[0].id, copy[1]["id"]: created[1].id}


def test_a_tax_category_turned_off_since_is_the_creates_to_refuse():
    tax = make_tax("test.service", "Service — test", is_active=False)
    [record] = queries.services_not_in_business([a_service_of_the_copy(name="Manicure", tax_category_id=tax.pk)])

    with pytest.raises(InvalidPayload) as refused:
        create(record)

    assert refused.value.code == "service.tax_category_unknown"


def test_the_app_declares_what_it_gives_back():
    [declared] = apps.get_app_config("service").recoverable_from_copy()

    assert (declared.read, declared.missing, declared.create) == (
        queries.services_in_copy,
        queries.services_not_in_business,
        "service.service.create",
    )
    assert str(declared.label) == "Services"
    assert declared.reads_since == "0001_initial"


# ── End to end: the business's own database and its copy ────────────────────────────────────────────────────────────


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


def a_tax_key(hub) -> str:
    with use_hub(hub):
        return TaxCategory.objects.filter(is_active=True).order_by("key").values_list("key", flat=True).first()


def offered_services(hub) -> list[tuple]:
    """The business's services: name, price, duration, its category's name, its tax category's key and whether on
    offer, by name."""
    with use_hub(hub):
        return [
            (one.name, one.price, one.duration_minutes, one.category.name if one.category else None,
             one.tax_category.key if one.tax_category else None, one.is_active)
            for one in Service.objects.select_related("category", "tax_category").order_by("name", "id")
        ]


def created_events(hub) -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name="service.service.created").count()


def gone(hub, *ids) -> None:
    """``ids`` gone from the business altogether: no operation deletes a service, a lost database does."""
    with use_hub(hub):
        Service.objects.filter(pk__in=ids).delete()


@pytest.mark.usefixtures("no_test_fallback")
class TestServicesComeBack:
    def a_business(self, recoveries, every_app_on):
        """A business with two categories and four services made by their screen's operations (one archived), the
        services' ids and the second category's."""
        hub, _ = recoveries.business(every_app_on)
        tax = a_tax_key(hub)
        hair = run_in(hub, "service.category.create", name="Hair").id
        color = run_in(hub, "service.category.create", name="Color").id
        made = {
            "cut": run_in(hub, "service.service.create", name="Haircut", price=2000, duration_minutes=30,
                          category_id=hair, tax_category_key=tax),
            "keratin": run_in(hub, "service.service.create", name="Keratin treatment", price=9000,
                              duration_minutes=90, category_id=hair, tax_category_key=tax, notes="Ask about allergies"),
            "highlights": run_in(hub, "service.service.create", name="Highlights", price=4500, duration_minutes=60,
                                 category_id=color, tax_category_key=tax),
            "perm": run_in(hub, "service.service.create", name="Old perm", price=3000, tax_category_key=tax),
        }
        run_in(hub, "service.service.archive", id=made["perm"].id)
        return hub, tax, {name: one.id for name, one in made.items()}, color

    def test_the_services_the_business_lost_come_back_each_created_by_its_operation(self, recoveries, every_app_on):
        hub, tax, ids, color = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        gone(hub, ids["keratin"], ids["highlights"], ids["perm"])
        run_in(hub, "service.category.delete", id=color)
        before = created_events(hub)
        row = recoveries.ask(copy, "service")

        assert run() == 1

        row = fresh(row)
        [result] = row.results
        assert row.status == "done"
        assert (result["app"], result["created"], result["not_created"], result["reasons"], result["refused"]) == (
            "service", 2, 0, [], ""
        )
        # On offer as the copy had them, in the categories the business still has; the archived one was not on offer.
        assert offered_services(hub) == [
            ("Haircut", 2000, 30, "Hair", tax, True),
            ("Highlights", 4500, 60, None, tax, True),
            ("Keratin treatment", 9000, 90, "Hair", tax, True),
        ]
        assert created_events(hub) == before + 2
        with use_hub(hub):
            back = Service.objects.exclude(pk=ids["cut"])
            assert not set(back.values_list("pk", flat=True)) & set(ids.values())
            assert back.get(name="Keratin treatment").notes == "Ask about allergies"

    def test_asked_again_nothing_is_made_twice_and_what_the_business_has_stays(self, recoveries, every_app_on):
        hub, tax, ids, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        gone(hub, ids["keratin"])
        recoveries.ask(copy, "service")
        assert run() == 1
        run_in(hub, "service.service.archive", id=ids["cut"])
        before = created_events(hub)

        again = recoveries.ask(copy, "service")
        assert run() == 1

        [result] = fresh(again).results
        assert (result["created"], result["not_created"], result["refused"]) == (0, 0, "")
        assert created_events(hub) == before
        # The one archived since stays archived: SERVICE-F05 restores it.
        assert [(one[0], one[-1]) for one in offered_services(hub)] == [
            ("Haircut", False),
            ("Highlights", True),
            ("Keratin treatment", True),
            ("Old perm", False),
        ]

    def test_a_service_whose_tax_category_the_create_refuses_is_counted_with_why(self, recoveries, every_app_on):
        hub, tax, ids, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        gone(hub, ids["cut"], ids["keratin"])
        with use_hub(hub):
            # Taxes never deletes a tax category; one no longer active is one the create does not take.
            TaxCategory.objects.filter(key=tax).update(is_active=False)
        row = recoveries.ask(copy, "service")

        assert run() == 1

        [result] = fresh(row).results
        assert (result["created"], result["not_created"], result["refused"]) == (0, 2, "")
        assert {one["id"] for one in result["reasons"]} == {str(ids["cut"]), str(ids["keratin"])}
        assert all(one["reason"].startswith("service.tax_category_unknown: ") for one in result["reasons"])
