"""What Services gives back from a separate copy of the business (hub#1283, hub#1323; BASE-F114, SERVICE-F01, F07).

The platform reads the copy (``base.tenancy.recovery``) through a direct, read-only connection: the copy is no
business, so it has no alias and the ORM never reaches it. Services answers it (``recoverable_from_copy`` on its
config) with two reads, by SQL over its model's names, given back in their order: first its categories
(``queries.recovery.categories_in_copy``), each live one the business lacks (``queries.recovery.categories_not_in_business``: deleted or
gone since, and not made again with its name) created by ``service.category.create``, the screen's own, parents first;
then its services (``queries.recovery.services_in_copy``): each service the copy offers, with what its create takes, its category
(by its id and its name there) and its tax category by their ids there. Then, in the business, which of those it holds
(``queries.recovery.services_in_business``): the same service, offered or archived (a service is never deleted, SERVICE-F04), or
one it made again, the same name in the same category; the others it lacks (``queries.recovery.services_not_in_business``), each
as ``service.service.create`` takes it here: the key of its tax category and its category, the same one while the
business still has it, else the live one with its name (brought back just before, or made again). Each is made again by
``service.service.recover``: created by that operation, the screen's own, and assigned to each professional who
performed it in the copy and the business still has (``queries.recovery.recoverable_services_in_copy``) by
``service.assignment.assign``, the screen's own too (SERVICE-F31).
"""

import uuid

import pytest
from django.apps import apps
from django.db import connections
from django.utils import timezone
from live.errors import InvalidPayload
from live.models import OutboxEvent
from live.operations import get

from apps.service import queries
from apps.service.models import Assignment, Category, Service
from apps.service.schemas.recovery import ServiceRecoverIn
from apps.tax.models import TaxCategory
from base.tenancy.context import current_alias, use_hub
from base.tenancy.tests.test_recovery import Recoveries, fields_held_since, fresh, run, run_in
from base.tests.test_image_catalog import image_library  # noqa: F401 - the library fixture

from .conftest import HUB_DB, ctx_for, make_category, make_service, make_tax

pytestmark = HUB_DB


def direct():
    """The raw connection of business A's database, as the platform's direct one reads the copy."""
    (business := connections[current_alias()]).ensure_connection()
    return business.connection


def create(record: dict, operation: str = "service.service.recover", actor: str = "system") -> dict:
    """``record`` created as the platform does, as ``actor`` with every permission (a recovery runs as its own,
    ``base.recovery.actor_of``): its create's input, all of it but its id in the copy."""
    op = get(operation)
    ctx = ctx_for(actor=actor, permissions={"*"})
    return op(ctx, op.input.model_validate({key: value for key, value in record.items() if key != "id"}))


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

    read, archived = sorted(queries.recovery.services_in_copy(direct()), key=lambda one: one["name"] != "Keratin treatment")

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
        "image": "service/services/keratin.webp",
        "category_id": hair.pk,
        "category_name": "Hair",
        "tax_category_id": tax.pk,
        "is_active": True,
    }


def test_a_copy_without_the_apps_table_gives_nothing():
    with connections[current_alias()].cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE service_service CASCADE")

    assert queries.recovery.services_in_copy(direct()) == []


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
    "image": "",
    "category_id": None,
    "category_name": None,
    "tax_category_id": None,
    "is_active": True,
}


def a_service_of_the_copy(service: Service | None = None, *, assignments=(), **fields) -> dict:
    """A service as the copy gives it (``recoverable_services_in_copy``): ``service``'s, or a new one with ``fields``;
    its category's name, the one it had there (the copy's moment, before the business deleted or renamed it), and who
    performed it there (``assignments``)."""
    performers = {"assignments": list(assignments)}
    if service is not None:
        fields = {field: getattr(service, field) for field in NEW if field != "category_name"}
        category = {"category_name": service.category.name if service.category else None}
        return {"id": service.pk} | fields | category | performers
    if fields.get("category_id") is not None and "category_name" not in fields:
        fields["category_name"] = Category.objects.get(pk=fields["category_id"]).name
    return {"id": uuid.uuid7()} | NEW | fields | performers


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

    held = queries.recovery.services_in_business(services)

    assert held == {
        offered.pk: offered.pk,
        archived.pk: archived.pk,
        again["id"]: made_again.pk,
        again_archived["id"]: made_again_archived.pk,
    }
    assert [one["id"] for one in queries.recovery.services_not_in_business(services)] == [other_category["id"], absent["id"]]


def test_a_lost_service_named_as_one_the_business_kept_in_the_same_category_is_lacking():
    tax = make_tax()
    hair = make_category("Hair")
    kept = make_service("Haircut", tax=tax, category=hair)
    # Service names are not unique: the kept one is itself a service of the copy, never another's made again.
    services = [a_service_of_the_copy(kept), lost := a_service_of_the_copy(name="Haircut", category_id=hair.pk)]

    assert queries.recovery.services_in_business(services) == {kept.pk: kept.pk}
    assert [one["id"] for one in queries.recovery.services_not_in_business(services)] == [lost["id"]]


def test_a_lost_service_named_as_one_the_copy_had_archived_is_lacking():
    tax = make_tax()
    archived = make_service("Haircut", tax=tax, is_active=False, archived_at=timezone.now())
    services = [
        a_service_of_the_copy(archived),
        lost := a_service_of_the_copy(name="Haircut"),
    ]

    assert queries.recovery.services_in_business(services) == {archived.pk: archived.pk}
    assert [one["id"] for one in queries.recovery.services_not_in_business(services)] == [lost["id"]]


def test_each_one_made_again_stands_for_one_service_of_the_copy_the_oldest_first():
    tax = make_tax()
    hair = make_category("Hair")
    first, second = (a_service_of_the_copy(name="Haircut", category_id=hair.pk) for _ in range(2))
    older = make_service("Haircut", tax=tax, category=hair)

    # One made again: it stands for the first of the copy; the second is still lacking.
    assert queries.recovery.services_in_business([first, second]) == {first["id"]: older.pk}
    assert [one["id"] for one in queries.recovery.services_not_in_business([first, second])] == [second["id"]]

    newer = make_service("haircut", tax=tax, category=hair)

    assert queries.recovery.services_in_business([first, second]) == {first["id"]: older.pk, second["id"]: newer.pk}
    # In whatever order the copy's services come.
    assert queries.recovery.services_in_business([second, first]) == {first["id"]: older.pk, second["id"]: newer.pk}
    assert queries.recovery.services_not_in_business([first, second]) == []


def test_two_lost_with_the_same_name_both_come_back_and_asking_again_makes_neither_twice():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    copy = [
        a_service_of_the_copy(name="Haircut", category_id=hair.pk, tax_category_id=tax.pk, price=2000),
        a_service_of_the_copy(name="Haircut", category_id=hair.pk, tax_category_id=tax.pk, price=2500),
    ]
    first = create(queries.recovery.services_not_in_business(copy)[0])
    # Cut after the first (the lease lost): the next pass still brings back the second.
    [second] = [create(record) for record in queries.recovery.services_not_in_business(copy)]

    assert (first.price, second.price) == (2000, 2500)
    assert queries.recovery.services_not_in_business(copy) == []
    assert queries.recovery.services_in_business(copy) == {copy[0]["id"]: first.id, copy[1]["id"]: second.id}


def test_a_service_the_copy_had_archived_never_comes_back():
    tax = make_tax("test.service", "Service — test")
    archived = a_service_of_the_copy(name="Old perm", tax_category_id=tax.pk, is_active=False)

    assert queries.recovery.services_in_business([archived]) == {}
    assert queries.recovery.services_not_in_business([archived]) == []


def test_one_the_copy_had_archived_never_takes_the_one_made_again_for_one_it_had_on_offer():
    tax = make_tax("test.service", "Service — test")
    # Both gone: an older one archived and the one on offer, already brought back by an earlier pass.
    archived = a_service_of_the_copy(name="Haircut", tax_category_id=tax.pk, is_active=False)
    offered = a_service_of_the_copy(name="Haircut", tax_category_id=tax.pk)
    brought_back = make_service("Haircut", tax=tax)

    assert queries.recovery.services_in_business([archived, offered]) == {offered["id"]: brought_back.pk}
    assert queries.recovery.services_not_in_business([archived, offered]) == []


def test_one_whose_category_the_business_deleted_is_made_again_with_no_category():
    tax = make_tax()
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    without = make_service("Highlights", tax=tax)
    services = [a_service_of_the_copy(name="Highlights", category_id=gone.pk)]

    # It would come back with no category, and the business has it there already.
    assert queries.recovery.services_in_business(services) == {services[0]["id"]: without.pk}


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

    lacking = queries.recovery.services_not_in_business([in_hair, in_gone])

    read_only = {"category_id", "category_name", "tax_category_id", "is_active"}
    # Each with which of the copy's it stands for, which the business keeps (hub#1459).
    assert lacking[0] == {key: value for key, value in in_hair.items() if key not in read_only} | {
        "category_id": hair.pk,
        "tax_category_key": "test.service",
        "stands_for": in_hair["id"],
    }
    assert lacking[1] == {key: value for key, value in in_gone.items() if key not in read_only} | {
        "tax_category_key": "test.service",
        "stands_for": in_gone["id"],
    }
    for record in lacking:
        ServiceRecoverIn.model_validate({key: value for key, value in record.items() if key != "id"})


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

    created = [create(record) for record in queries.recovery.services_not_in_business(copy)]

    assert [(one.name, one.price, one.duration_minutes, one.category_id, one.tax_category_key) for one in created] == [
        ("Keratin treatment", 9000, 90, hair.pk, "test.service"),
        ("Manicure", 1500, 30, None, "test.service"),
    ]
    assert queries.recovery.services_not_in_business(copy) == []
    assert queries.recovery.services_in_business(copy) == {copy[0]["id"]: created[0].id, copy[1]["id"]: created[1].id}


def test_a_tax_category_turned_off_since_is_the_creates_to_refuse():
    tax = make_tax("test.service", "Service — test", is_active=False)
    [record] = queries.recovery.services_not_in_business([a_service_of_the_copy(name="Manicure", tax_category_id=tax.pk)])

    with pytest.raises(InvalidPayload) as refused:
        create(record)

    assert refused.value.code == "service.tax_category_unknown"


def performers(name: str) -> list[tuple]:
    """Who performs the service ``name`` of the business: the professional's first name, their own minutes and price,
    whether it is their main service and whether the assignment is on, by first name."""
    return [
        (one.member.first_name, one.custom_duration, one.custom_price, one.is_primary, one.is_active)
        for one in Assignment.objects.filter(service__name=name).select_related("member").order_by("member__first_name")
    ]


# ── Its image (hub#1429): the one of the library it showed in the copy comes back with it ─────────────────────────

LIBRARY_IMAGE = "catalog:hospitality/cafe_solo"


def lacking_with_image(image: str) -> dict:
    tax = make_tax("test.service", "Service — test")
    [record] = queries.recovery.services_not_in_business(
        [a_service_of_the_copy(name="Keratin treatment", tax_category_id=tax.pk, image=image)]
    )
    return record


def service_events() -> list[str]:
    events = OutboxEvent.objects.filter(name__startswith="service.service.").order_by("id")
    return list(events.values_list("name", flat=True))


def test_a_service_made_again_shows_its_image_of_the_library_set_as_its_screen_sets_it(image_library):  # noqa: F811
    record = lacking_with_image(LIBRARY_IMAGE)

    made = create(record)

    assert record["image"] == LIBRARY_IMAGE
    assert (made.image, Service.objects.get(pk=made.id).image) == (LIBRARY_IMAGE, LIBRARY_IMAGE)
    # As the screen does it: the create, then its image (SERVICE-F34).
    assert service_events() == ["service.service.created", "service.service.updated"]


@pytest.mark.parametrize(
    "image",
    [
        # A copy is of the database, never of the files: the photo went with the service.
        "file:service/services/0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp",
        # The library no longer has it.
        "catalog:hospitality/churros",
        "",
    ],
)
def test_a_service_made_again_without_an_image_of_the_library_is_the_screens_create(image_library, image):  # noqa: F811
    made = create(lacking_with_image(image))

    assert (made.image, Service.objects.get(pk=made.id).image) == ("", "")
    assert service_events() == ["service.service.created"]


def test_making_a_service_again_with_who_performed_it_is_only_the_systems():
    op = get("service.service.recover")

    assert op.permission == "service.system"
    assert not ctx_for("hub_owner").has(op.permission)


def test_the_app_declares_what_it_gives_back_its_categories_first_and_what_goes_back_into_them_last():
    categories, services, service_links, subcategory_links = apps.get_app_config("service").recoverable_from_copy()

    assert (categories.read, categories.missing, categories.create) == (
        queries.recovery.categories_in_copy,
        queries.recovery.categories_not_in_business,
        "service.category.recover",
    )
    assert (services.read, services.missing, services.create) == (
        queries.recovery.recoverable_services_in_copy,
        queries.recovery.services_not_in_business,
        "service.service.recover",
    )
    assert (service_links.read, service_links.missing, service_links.create) == (
        queries.recovery.categories_in_copy,
        queries.recovery.service_links_not_in_business,
        "service.service.return_to_category",
    )
    assert (subcategory_links.read, subcategory_links.missing, subcategory_links.create) == (
        queries.recovery.categories_in_copy,
        queries.recovery.subcategory_links_not_in_business,
        "service.category.return_to_parent",
    )
    assert [str(one.label) for one in (categories, services, service_links, subcategory_links)] == [
        "Service categories",
        "Services",
        "Service links to categories",
        "Subcategory links to categories",
    ]
    assert [one.reads_since for one in (categories, services, service_links, subcategory_links)] == [
        "0001_initial",
        "0003_service_image",
        "0001_initial",
        "0001_initial",
    ]
    # A copy from before the image is refused for Services alone (recover_copy_behind), never read into an SQL error.
    assert set(queries.recovery.COPY_FIELDS) <= fields_held_since("service", "service", services.reads_since)
    # What categories_in_copy reads of each table is there since the migration each of its readers names.
    for one in (categories, service_links, subcategory_links):
        held = {"id", *queries.recovery.CATEGORY_COPY_FIELDS, "parent", "is_deleted"}
        assert held <= fields_held_since("service", "category", one.reads_since)
        assert {"id", "category"} <= fields_held_since("service", "service", one.reads_since)


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


def created_events(hub, name: str = "service.service.created") -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name=name).count()


CATEGORIES = {
    "app": "service", "label": "Service categories", "restored": 0, "created": 0, "not_created": 0, "reasons": [],
    "refused": "",
}
SERVICES = CATEGORIES | {"label": "Services"}
SERVICE_LINKS = CATEGORIES | {"label": "Service links to categories"}
SUBCATEGORY_LINKS = CATEGORIES | {"label": "Subcategory links to categories"}
#: What a recovery put back into a category it brought back, nothing: each counted apart, after the services.
NO_LINKS = [SERVICE_LINKS, SUBCATEGORY_LINKS]


def recovered(recoveries, copy) -> list[dict]:
    """Services asked back from ``copy`` and the worker's pass run: what it gave back, its categories then its
    services, each counted apart."""
    row = recoveries.ask(copy, "service")
    assert run() == 1
    return fresh(row).results


def live_categories(hub) -> list[tuple]:
    """The business's live categories: name, its parent's name, colour and order, by name."""
    with use_hub(hub):
        return [
            (one.name, one.parent.name if one.parent else None, one.color, one.sort_order)
            for one in Category.objects.filter(is_deleted=False).select_related("parent").order_by("name", "id")
        ]


def in_categories(hub) -> list[tuple]:
    """The business's services, archived too: name and its category's name, by name."""
    with use_hub(hub):
        return [
            (one.name, one.category.name if one.category else None)
            for one in Service.objects.select_related("category").order_by("name", "id")
        ]


def gone(hub, *ids) -> None:
    """``ids`` gone from the business altogether: no operation deletes a service, a lost database does."""
    with use_hub(hub):
        Service.objects.filter(pk__in=ids).delete()


class TestServicesComeBack:
    def a_business(self, recoveries, every_app_on):
        """A business with two categories and four services made by their screen's operations (one archived), the
        services' ids and the second category's."""
        hub, _ = recoveries.business(every_app_on)
        tax = a_tax_key(hub)
        hair = run_in(hub, "service.category.create", name="Hair").id
        color = run_in(hub, "service.category.create", name="Color", color="#cc0066", sort_order=4).id
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
        before, categories_before = created_events(hub), created_events(hub, "service.category.created")
        row = recoveries.ask(copy, "service")

        assert run() == 1

        row = fresh(row)
        assert row.status == "done"
        # The category the business deleted, then the two services: each counted apart, under its own name.
        assert row.results == [CATEGORIES | {"created": 1}, SERVICES | {"created": 2}, *NO_LINKS]
        # The category back first, by Categories' create, as the copy had it; the deleted one stays deleted.
        assert live_categories(hub) == [("Color", None, "#cc0066", 4), ("Hair", None, "", 0)]
        assert created_events(hub, "service.category.created") == categories_before + 1
        with use_hub(hub):
            assert Category.objects.get(pk=color).is_deleted
        # On offer as the copy had them, each in its category, the one brought back too; the archived one was not on
        # offer.
        assert offered_services(hub) == [
            ("Haircut", 2000, 30, "Hair", tax, True),
            ("Highlights", 4500, 60, "Color", tax, True),
            ("Keratin treatment", 9000, 90, "Hair", tax, True),
        ]
        assert created_events(hub) == before + 2
        with use_hub(hub):
            back = Service.objects.exclude(pk=ids["cut"])
            assert not set(back.values_list("pk", flat=True)) & set(ids.values())
            assert back.get(name="Keratin treatment").notes == "Ask about allergies"

    def test_a_lost_service_comes_back_with_the_image_of_the_library_it_had(
        self, recoveries, every_app_on, image_library  # noqa: F811
    ):
        hub, _, ids, _ = self.a_business(recoveries, every_app_on)
        run_in(hub, "service.service.set_image", id=ids["keratin"], image=LIBRARY_IMAGE)
        copy = recoveries.copy_of(hub)
        gone(hub, ids["keratin"], ids["highlights"])

        assert recovered(recoveries, copy) == [CATEGORIES, SERVICES | {"created": 2}, *NO_LINKS]

        with use_hub(hub):
            assert dict(Service.objects.filter(is_active=True).values_list("name", "image")) == {
                "Haircut": "",
                "Highlights": "",
                "Keratin treatment": LIBRARY_IMAGE,
            }

    def test_asked_again_nothing_is_made_twice_and_what_the_business_has_stays(self, recoveries, every_app_on):
        hub, tax, ids, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        gone(hub, ids["keratin"])
        recoveries.ask(copy, "service")
        assert run() == 1
        run_in(hub, "service.service.archive", id=ids["cut"])
        before = created_events(hub)

        assert recovered(recoveries, copy) == [CATEGORIES, SERVICES, *NO_LINKS]
        assert created_events(hub) == before
        # The one archived since stays archived: SERVICE-F05 restores it.
        assert [(one[0], one[-1]) for one in offered_services(hub)] == [
            ("Haircut", False),
            ("Highlights", True),
            ("Keratin treatment", True),
            ("Old perm", False),
        ]

    def test_a_subcategory_comes_back_inside_its_category_and_asked_again_neither_is_made_twice(
        self, recoveries, every_app_on
    ):
        hub, tax, ids, color = self.a_business(recoveries, every_app_on)
        toning = run_in(hub, "service.category.create", name="Toning", parent_id=color).id
        run_in(hub, "service.service.update", id=ids["highlights"], category_id=toning)
        copy = recoveries.copy_of(hub)
        gone(hub, ids["highlights"])
        # Its subcategory first (deleting the parent alone would move it up to the root, SERVICE-F08).
        run_in(hub, "service.category.delete", id=toning)
        run_in(hub, "service.category.delete", id=color)

        first, again = recovered(recoveries, copy), recovered(recoveries, copy)

        assert (first, again) == (
            [CATEGORIES | {"created": 2}, SERVICES | {"created": 1}, *NO_LINKS],
            [CATEGORIES, SERVICES, *NO_LINKS],
        )
        assert live_categories(hub) == [("Color", None, "#cc0066", 4), ("Hair", None, "", 0), ("Toning", "Color", "", 0)]
        assert [(one[0], one[3]) for one in offered_services(hub) if one[0] == "Highlights"] == [("Highlights", "Toning")]

    def test_a_category_the_business_made_again_is_not_duplicated_and_its_services_go_into_it(
        self, recoveries, every_app_on
    ):
        hub, tax, ids, color = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        gone(hub, ids["highlights"])
        run_in(hub, "service.category.delete", id=color)
        # Made again by hand since, with another colour: the business's stays as it is.
        again = run_in(hub, "service.category.create", name="COLOR", color="#112233").id

        # Only the service: the category is the business's already.
        assert recovered(recoveries, copy) == [CATEGORIES, SERVICES | {"created": 1}, *NO_LINKS]
        assert live_categories(hub) == [("COLOR", None, "#112233", 0), ("Hair", None, "", 0)]
        with use_hub(hub):
            assert Service.objects.get(name="Highlights").category_id == again

    def test_a_service_comes_back_with_who_the_business_still_has_to_perform_it_each_assigned_by_its_operation(
        self, recoveries, every_app_on
    ):
        hub, tax, ids, _ = self.a_business(recoveries, every_app_on)
        ana, raquel, sonia = (
            run_in(hub, "staff.member.create", first_name=first, last_name="Gil").id for first in ("Ana", "Raquel", "Sonia")
        )
        run_in(hub, "service.assignment.assign", service_id=ids["keratin"], member_id=ana, custom_duration=75,
               custom_price=9500)
        run_in(hub, "service.assignment.assign", service_id=ids["keratin"], member_id=raquel)
        off = run_in(hub, "service.assignment.assign", service_id=ids["keratin"], member_id=sonia, custom_price=8000)
        run_in(hub, "service.assignment.update", id=off.id, is_active=False)
        copy = recoveries.copy_of(hub)
        gone(hub, ids["keratin"])
        # Terminated since: Staff no longer has her to book.
        run_in(hub, "staff.member.terminate", id=raquel)
        before = created_events(hub, "service.assignment.assigned")

        first = recovered(recoveries, copy)
        again = recovered(recoveries, copy)

        # One service made again, its professionals with it; Recoveries says it came back without Raquel, and why.
        [note] = first[1].pop("notes")
        assert (first, again) == (
            [CATEGORIES, SERVICES | {"created": 1, "noted": 1}, *NO_LINKS],
            [CATEGORIES, SERVICES, *NO_LINKS],
        )
        assert note["id"] == str(ids["keratin"])
        assert note["note"].startswith("service.member_terminated: ") and str(raquel) in note["note"]
        with use_hub(hub):
            back = Service.objects.get(name="Keratin treatment")
            assert back.pk != ids["keratin"]
            assert performers("Keratin treatment") == [("Ana", 75, 9500, False, True), ("Sonia", None, 8000, False, False)]
        assert created_events(hub, "service.assignment.assigned") == before + 2

    def a_full_category(self, recoveries, every_app_on):
        """The business of ``a_business`` with two more services and a subcategory in Color, and its copy as it is."""
        hub, tax, ids, color = self.a_business(recoveries, every_app_on)
        ids["toning"] = run_in(hub, "service.category.create", name="Toning", parent_id=color).id
        for name, price in (("Gloss", 3500), ("Balayage", 8000)):
            ids[name.lower()] = run_in(
                hub, "service.service.create", name=name, price=price, category_id=color, tax_category_key=tax
            ).id
        with use_hub(hub):
            ids["hair"] = Service.objects.get(pk=ids["cut"]).category_id
        return hub, ids, color, recoveries.copy_of(hub)

    def test_a_category_comes_back_with_what_the_business_kept_where_its_deletion_left_it(
        self, recoveries, every_app_on
    ):
        hub, ids, color, copy = self.a_full_category(recoveries, every_app_on)
        # Its services left without a category and its subcategory moved up to the root (SERVICE-F08).
        run_in(hub, "service.category.delete", id=color)
        before = created_events(hub, "service.service.updated")
        moved_before = created_events(hub, "service.category.updated")

        # The category made again, and apart, what the business kept that went back into it: three services and a
        # subcategory.
        assert recovered(recoveries, copy) == [
            CATEGORIES | {"created": 1},
            SERVICES,
            SERVICE_LINKS | {"created": 3},
            SUBCATEGORY_LINKS | {"created": 1},
        ]
        # Back inside it: the same subcategory and the same three services, each by its own change.
        assert live_categories(hub) == [("Color", None, "#cc0066", 4), ("Hair", None, "", 0), ("Toning", "Color", "", 0)]
        assert in_categories(hub) == [
            ("Balayage", "Color"),
            ("Gloss", "Color"),
            ("Haircut", "Hair"),
            ("Highlights", "Color"),
            ("Keratin treatment", "Hair"),
            ("Old perm", None),
        ]
        with use_hub(hub):
            assert Category.objects.get(name="Toning", is_deleted=False).pk == ids["toning"]
        assert created_events(hub, "service.service.updated") == before + 3
        assert created_events(hub, "service.category.updated") == moved_before + 1

    def test_what_the_business_moved_since_stays_where_it_is_and_recoveries_says_so(self, recoveries, every_app_on):
        hub, ids, color, copy = self.a_full_category(recoveries, every_app_on)
        run_in(hub, "service.category.delete", id=color)
        # Moved by hand since: the business put Balayage in Hair and Toning under Hair.
        run_in(hub, "service.service.update", id=ids["balayage"], category_id=ids["hair"])
        run_in(hub, "service.category.update", id=ids["toning"], parent_id=ids["hair"])

        [categories, *rest] = recovered(recoveries, copy)

        notes = categories.pop("notes")
        # What it kept where the deletion left it goes back, counted apart; what it moved is said on the category.
        assert [categories, *rest] == [
            CATEGORIES | {"created": 1, "noted": 1},
            SERVICES,
            SERVICE_LINKS | {"created": 2},
            SUBCATEGORY_LINKS,
        ]
        assert {one["id"] for one in notes} == {str(color)}
        assert sorted(one["note"].split(":")[0] for one in notes) == ["service.service_moved", "service.subcategory_moved"]
        assert any(str(ids["balayage"]) in one["note"] for one in notes)
        assert any(str(ids["toning"]) in one["note"] for one in notes)
        assert live_categories(hub) == [("Color", None, "#cc0066", 4), ("Hair", None, "", 0), ("Toning", "Hair", "", 0)]
        assert [one for one in in_categories(hub) if one[0] in {"Balayage", "Gloss", "Highlights"}] == [
            ("Balayage", "Hair"),
            ("Gloss", "Color"),
            ("Highlights", "Color"),
        ]

    def test_what_the_business_changed_without_moving_while_its_category_came_back_stays_and_recoveries_says_so(
        self, recoveries, every_app_on, monkeypatch
    ):
        hub, ids, color, copy = self.a_full_category(recoveries, every_app_on)
        run_in(hub, "service.category.delete", id=color)
        read_services = queries.recovery.services_not_in_business

        def changed_while_the_services_come_back(services):
            # The business, once the category is back: Gloss gets a new price and Toning an icon, neither moved.
            gloss = Service.objects.get(pk=ids["gloss"])
            gloss.price = 3600
            gloss.save()
            toning = Category.objects.get(pk=ids["toning"])
            toning.icon = "ion:color-palette-outline"
            toning.save()
            return read_services(services)

        monkeypatch.setattr(queries.recovery, "services_not_in_business", changed_while_the_services_come_back)

        results = recovered(recoveries, copy)

        service_reasons, subcategory_reasons = results[2]["reasons"], results[3]["reasons"]
        assert results == [
            CATEGORIES | {"created": 1},
            SERVICES,
            SERVICE_LINKS | {"created": 2, "not_created": 1, "reasons": service_reasons},
            SUBCATEGORY_LINKS | {"not_created": 1, "reasons": subcategory_reasons},
        ]
        assert [(one["id"], one["reason"].split(":")[0]) for one in service_reasons] == [
            (str(ids["gloss"]), "service.service_changed")
        ]
        assert [(one["id"], one["reason"].split(":")[0]) for one in subcategory_reasons] == [
            (str(ids["toning"]), "service.subcategory_changed")
        ]
        assert str(ids["gloss"]) in service_reasons[0]["reason"]
        assert str(ids["toning"]) in subcategory_reasons[0]["reason"]
        # Each stays as the business left it; what it did not touch went back.
        assert [one for one in in_categories(hub) if one[0] in {"Balayage", "Gloss", "Highlights"}] == [
            ("Balayage", "Color"),
            ("Gloss", None),
            ("Highlights", "Color"),
        ]
        assert [one for one in live_categories(hub) if one[0] == "Toning"] == [("Toning", None, "", 0)]

    def test_asked_again_a_category_brought_back_is_the_businesss_and_is_not_filled_again(
        self, recoveries, every_app_on
    ):
        hub, ids, color, copy = self.a_full_category(recoveries, every_app_on)
        run_in(hub, "service.category.delete", id=color)
        recovered(recoveries, copy)
        # Taken out of it by hand after the first recovery: asked again, they stay out, and nothing says otherwise.
        run_in(hub, "service.service.update", id=ids["gloss"], category_id=None)
        run_in(hub, "service.category.update", id=ids["toning"], parent_id=None)

        assert recovered(recoveries, copy) == [CATEGORIES, SERVICES, *NO_LINKS]
        assert [one for one in in_categories(hub) if one[0] == "Gloss"] == [("Gloss", None)]
        assert [one for one in live_categories(hub) if one[0] == "Toning"] == [("Toning", None, "", 0)]

    def test_a_service_whose_tax_category_the_create_refuses_is_counted_with_why(self, recoveries, every_app_on):
        hub, tax, ids, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        gone(hub, ids["cut"], ids["keratin"])
        with use_hub(hub):
            # Taxes never deletes a tax category; one no longer active is one the create does not take.
            TaxCategory.objects.filter(key=tax).update(is_active=False)
        row = recoveries.ask(copy, "service")

        assert run() == 1

        [categories, result, *links] = fresh(row).results
        assert (categories, links) == (CATEGORIES, NO_LINKS)
        assert (result["label"], result["created"], result["not_created"], result["refused"]) == ("Services", 0, 2, "")
        assert {one["id"] for one in result["reasons"]} == {str(ids["cut"]), str(ids["keratin"])}
        assert all(one["reason"].startswith("service.tax_category_unknown: ") for one in result["reasons"])
