"""What Services gives back from a separate copy of the business (hub#1283, hub#1323; BASE-F114, SERVICE-F01, F07).

The platform reads the copy (``base.tenancy.recovery``) through a direct, read-only connection: the copy is no
business, so it has no alias and the ORM never reaches it. Services answers it (``recoverable_from_copy`` on its
config) with two reads, by SQL over its model's names, given back in their order: first its categories
(``queries.categories_in_copy``), each live one the business lacks (``queries.categories_not_in_business``: deleted or
gone since, and not made again with its name) created by ``service.category.create``, the screen's own, parents first;
then its services (``queries.services_in_copy``): each service the copy offers, with what its create takes, its category
(by its id and its name there) and its tax category by their ids there. Then, in the business, which of those it holds
(``queries.services_in_business``): the same service, offered or archived (a service is never deleted, SERVICE-F04), or
one it made again, the same name in the same category; the others it lacks (``queries.services_not_in_business``), each
as ``service.service.create`` takes it here: the key of its tax category and its category, the same one while the
business still has it, else the live one with its name (brought back just before, or made again). Each is made again by
``service.service.recover``: created by that operation, the screen's own, and assigned to each professional who
performed it in the copy and the business still has (``queries.recoverable_services_in_copy``) by
``service.assignment.assign``, the screen's own too (SERVICE-F31).
"""

import threading
import uuid

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone, translation
from live.errors import Conflict, InvalidPayload
from live.models import OutboxEvent
from live.operations import get

from apps.service import queries
from apps.service.models import Assignment, Category, Service
from apps.service.schemas import CategoryRecoverIn, ServiceRecoverIn
from apps.service.services import MEMBER_TERMINATED_LEFT, SERVICE_MOVED_LEFT
from apps.staff.models import Member
from apps.tax.models import TaxCategory
from base.recovery import actor_of
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import Recoveries, fields_held_since, fresh, run, run_in
from base.tests.test_image_catalog import image_library  # noqa: F401 - the library fixture

from .conftest import ctx_for, make_category, make_member, make_service, make_tax

pytestmark = pytest.mark.django_db


def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


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
        "image": "service/services/keratin.webp",
        "category_id": hair.pk,
        "category_name": "Hair",
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
    # In whatever order the copy's services come.
    assert queries.services_in_business([second, first]) == {first["id"]: older.pk, second["id"]: newer.pk}
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


def test_one_the_copy_had_archived_never_takes_the_one_made_again_for_one_it_had_on_offer():
    tax = make_tax("test.service", "Service — test")
    # Both gone: an older one archived and the one on offer, already brought back by an earlier pass.
    archived = a_service_of_the_copy(name="Haircut", tax_category_id=tax.pk, is_active=False)
    offered = a_service_of_the_copy(name="Haircut", tax_category_id=tax.pk)
    brought_back = make_service("Haircut", tax=tax)

    assert queries.services_in_business([archived, offered]) == {offered["id"]: brought_back.pk}
    assert queries.services_not_in_business([archived, offered]) == []


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


# ── Who performs each one: each professional the business still has, assigned by the screen's operation ───────────


def an_assignment_of_the_copy(member: Member, **fields) -> dict:
    """A professional who performed a service in the copy, as ``recoverable_services_in_copy`` gives it."""
    return {
        "member_id": member.pk,
        "custom_duration": None,
        "custom_price": None,
        "is_primary": False,
        "is_active": True,
    } | fields


def performers(name: str) -> list[tuple]:
    """Who performs the service ``name`` of the business: the professional's first name, their own minutes and price,
    whether it is their main service and whether the assignment is on, by first name."""
    return [
        (one.member.first_name, one.custom_duration, one.custom_price, one.is_primary, one.is_active)
        for one in Assignment.objects.filter(service__name=name).select_related("member").order_by("member__first_name")
    ]


def test_the_copy_gives_each_service_with_who_performed_it_there_archived_ones_too():
    tax = make_tax("test.service", "Service — test")
    ana, sonia = make_member("Ana", "López"), make_member("Sonia", "Ruiz")
    keratin = make_service("Keratin treatment", tax=tax, price=9000)
    perm = make_service("Old perm", tax=tax, is_active=False, archived_at=timezone.now())
    manicure = make_service("Manicure", tax=tax)
    Assignment.objects.create(service=keratin, member=ana, custom_duration=75, custom_price=9500, is_primary=True)
    Assignment.objects.create(service=keratin, member=sonia, custom_price=8000, is_active=False)
    Assignment.objects.create(service=perm, member=sonia)

    read = {one["id"]: one for one in queries.recoverable_services_in_copy(direct())}

    plain = {one["id"]: one for one in queries.services_in_copy(direct())}
    assert {pk: {key: value for key, value in one.items() if key != "assignments"} for pk, one in read.items()} == plain
    assert read[keratin.pk]["assignments"] == [
        an_assignment_of_the_copy(ana, custom_duration=75, custom_price=9500, is_primary=True),
        an_assignment_of_the_copy(sonia, custom_price=8000, is_active=False),
    ]
    assert read[perm.pk]["assignments"] == [an_assignment_of_the_copy(sonia)]
    assert read[manicure.pk]["assignments"] == []


def test_a_copy_without_the_apps_tables_gives_nobody():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE service_assignment, service_service CASCADE")

    assert queries.recoverable_services_in_copy(direct()) == []


def test_each_lacking_service_comes_with_who_performed_it_in_the_copy():
    tax = make_tax("test.service", "Service — test")
    ana = make_member("Ana", "López")
    performed = [an_assignment_of_the_copy(ana, custom_duration=75, custom_price=9500)]
    lost = a_service_of_the_copy(name="Keratin treatment", tax_category_id=tax.pk, assignments=performed)

    [record] = queries.services_not_in_business([lost])

    assert record["assignments"] == performed
    ServiceRecoverIn.model_validate({key: value for key, value in record.items() if key != "id"})


def test_a_service_made_again_is_assigned_to_each_professional_the_business_still_has_with_their_own_minutes_and_price():
    tax = make_tax("test.service", "Service — test")
    ana, raquel = make_member("Ana", "López"), make_member("Raquel", "Gil")
    on_leave = make_member("Lola", "Vega", status=Member.Status.ON_LEAVE)
    left = make_member("Marta", "Sanz", status=Member.Status.TERMINATED)
    nobody = Member(pk=uuid.uuid7(), first_name="Gone", last_name="Long ago")
    performed = [
        an_assignment_of_the_copy(ana, custom_duration=75, custom_price=9500),
        an_assignment_of_the_copy(raquel),
        an_assignment_of_the_copy(on_leave, custom_price=8000),
        an_assignment_of_the_copy(left, custom_price=7000),
        an_assignment_of_the_copy(nobody),
    ]
    [record] = queries.services_not_in_business(
        [a_service_of_the_copy(name="Keratin treatment", tax_category_id=tax.pk, price=9000, assignments=performed)]
    )
    before = OutboxEvent.objects.filter(name="service.assignment.assigned").count()

    made = create(record)

    # Who the business terminated, or no longer has at all, is not assigned: Staff no longer has them to book.
    assert performers("Keratin treatment") == [
        ("Ana", 75, 9500, False, True),
        ("Lola", None, 8000, False, True),
        ("Raquel", None, None, False, True),
    ]
    assert Assignment.objects.filter(service_id=made.id).count() == 3
    # Each by the screen's own operation, with its notice.
    assert OutboxEvent.objects.filter(name="service.assignment.assigned").count() == before + 3
    # Who was left out is said, by their id, with why; who came back with it is not.
    assert [one.code for one in made.left_out] == ["service.member_terminated", "service.member_not_in_business"]
    assert [str(left.pk) in made.left_out[0].message, str(nobody.pk) in made.left_out[1].message] == [True, True]


def test_who_a_service_came_back_without_is_said_in_the_language_it_is_made_in():
    tax = make_tax("test.service", "Service — test")
    left = make_member("Marta", "Sanz", status=Member.Status.TERMINATED)
    [record] = queries.services_not_in_business(
        [
            a_service_of_the_copy(
                name="Keratin treatment", tax_category_id=tax.pk, assignments=[an_assignment_of_the_copy(left)]
            )
        ]
    )

    with translation.override("es"):
        [said] = create(record).left_out
        spanish = MEMBER_TERMINATED_LEFT % {"member": left.pk}

    assert said.message == spanish
    assert said.message != MEMBER_TERMINATED_LEFT % {"member": left.pk}


def test_a_service_made_again_with_everyone_who_performed_it_says_nothing_left():
    tax = make_tax("test.service", "Service — test")
    ana = make_member("Ana", "López")
    [record] = queries.services_not_in_business(
        [
            a_service_of_the_copy(
                name="Keratin treatment", tax_category_id=tax.pk, assignments=[an_assignment_of_the_copy(ana)]
            )
        ]
    )

    assert create(record).left_out == []


def test_one_switched_off_in_the_copy_comes_back_switched_off():
    tax = make_tax("test.service", "Service — test")
    sonia = make_member("Sonia", "Ruiz")
    performed = [an_assignment_of_the_copy(sonia, custom_price=8000, is_active=False)]
    [record] = queries.services_not_in_business(
        [a_service_of_the_copy(name="Manicure", tax_category_id=tax.pk, assignments=performed)]
    )

    create(record)

    assert performers("Manicure") == [("Sonia", None, 8000, False, False)]


def test_the_main_service_comes_back_only_for_whom_the_business_set_none_since():
    tax = make_tax("test.service", "Service — test")
    ana, sonia = make_member("Ana", "López"), make_member("Sonia", "Ruiz")
    # Sonia's main service in the business since the copy: hers stays.
    nails = make_service("Nails", tax=tax)
    Assignment.objects.create(service=nails, member=sonia, is_primary=True)
    # Ana performs it too, and it is not her main one: she has none.
    Assignment.objects.create(service=nails, member=ana)
    performed = [
        an_assignment_of_the_copy(ana, is_primary=True),
        an_assignment_of_the_copy(sonia, is_primary=True),
    ]
    [record] = queries.services_not_in_business(
        [a_service_of_the_copy(name="Keratin treatment", tax_category_id=tax.pk, assignments=performed)]
    )

    create(record)

    assert performers("Keratin treatment") == [("Ana", None, None, True, True), ("Sonia", None, None, False, True)]
    assert performers("Nails") == [("Ana", None, None, False, True), ("Sonia", None, None, True, True)]


# ── Its image (hub#1429): the one of the library it showed in the copy comes back with it ─────────────────────────

LIBRARY_IMAGE = "catalog:hospitality/cafe_solo"


def lacking_with_image(image: str) -> dict:
    tax = make_tax("test.service", "Service — test")
    [record] = queries.services_not_in_business(
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


# ── The service that stands for one of the copy's, for an app whose records hang from a service (hub#1459) ──────


def made_again_for(there: uuid.UUID, name: str = "Haircut", **fields) -> Service:
    """A service a recovery from a separate copy made again for the copy's ``there``, as ``service.service.recover``
    leaves it."""
    return make_service(name, created_by=actor_of(uuid.uuid7()), stands_for=there, **fields)


def test_a_lost_service_made_again_keeps_which_of_the_copys_it_stands_for():
    tax = make_tax("test.service", "Service — test")
    lost = a_service_of_the_copy(name="Keratin treatment", tax_category_id=tax.pk)

    [record] = queries.services_not_in_business([lost])
    made = create(record, actor=actor_of(uuid.uuid7()))

    assert record["stands_for"] == lost["id"]
    assert Service.objects.get(pk=made.id).stands_for == lost["id"]


def test_one_made_by_the_screen_stands_for_none():
    tax = make_tax("test.service", "Service — test")
    made = create({"name": "Haircut", "price": 2000, "tax_category_key": tax.key}, "service.service.create")

    assert Service.objects.get(pk=made.id).stands_for is None


def test_a_service_no_longer_held_is_the_one_a_recovery_made_again_for_it():
    gone, archived_since, renamed_since = uuid.uuid7(), uuid.uuid7(), uuid.uuid7()
    haircut = made_again_for(gone)
    colour = made_again_for(archived_since, "Colour", is_active=False)
    perm = made_again_for(renamed_since, "Curly perm")

    assert queries.services_standing_for([gone, archived_since, renamed_since]) == {
        gone: haircut.pk,
        archived_since: colour.pk,
        renamed_since: perm.pk,
    }


def test_a_service_still_held_is_itself_and_not_in_the_result():
    offered = make_service("Haircut")
    archived = make_service("Colour", is_active=False)
    made_again_for(offered.pk)
    made_again_for(archived.pk, "Colour")

    assert queries.services_standing_for([offered.pk, archived.pk]) == {}


def test_one_made_again_by_hand_with_its_name_stands_for_none():
    make_service("Haircut", created_by="ana")

    assert queries.services_standing_for([uuid.uuid7()]) == {}


def test_made_again_twice_for_one_the_oldest_stands_for_it():
    gone = uuid.uuid7()
    first = made_again_for(gone)
    made_again_for(gone, "Haircut, renamed")

    assert queries.services_standing_for([gone]) == {gone: first.pk}


def test_with_nothing_asked_none_stands_for_anything():
    made_again_for(uuid.uuid7())

    assert queries.services_standing_for([]) == {}


def test_another_app_asks_it_by_its_operation_and_only_as_the_platform():
    gone = uuid.uuid7()
    haircut = made_again_for(gone)
    op = get("service.service.standing_for")

    answer = op(ctx_for(actor="system", permissions={"*"}), op.input(ids=[gone, uuid.uuid7()]))

    assert answer.standing_for == {gone: haircut.pk}
    assert (op.kind, op.permission) == ("query", "service.system")
    assert not ctx_for("hub_owner").has(op.permission)


# ── Its categories (hub#1323): those the business lacks come back first, each by the screen's create ─────────────


#: A category of the copy with what a new one has, as ``categories_in_copy`` gives it.
NEW_CATEGORY = {
    "name": "",
    "description": "",
    "icon": "",
    "color": "",
    "sort_order": 0,
    "parent_id": None,
    "service_ids": [],
}


def a_category_of_the_copy(category: Category | None = None, **fields) -> dict:
    """A category as the copy gives it (``categories_in_copy``): ``category``'s, or a new one with ``fields``."""
    if category is not None:
        held = {field: getattr(category, field) for field in NEW_CATEGORY if field != "service_ids"}
        return {"id": category.pk, "service_ids": []} | held | fields
    return {"id": uuid.uuid7()} | NEW_CATEGORY | fields


def made_again(one: dict, *subcategories: dict, **parent) -> dict:
    """``one`` of the copy as ``categories_not_in_business`` gives it, to ``service.category.recover``: its parent here
    (``parent``), the one it stands for and what it had inside it there, its services and its ``subcategories``."""
    return (
        {key: value for key, value in one.items() if key != "parent_id"}
        | {"stands_for": one["id"], "subcategory_ids": [sub["id"] for sub in subcategories]}
        | parent
    )


def test_the_copy_gives_each_live_category_with_what_its_create_takes_and_the_services_in_it():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair", description="Cuts and styling", icon="ion:cut-outline", color="#aa3300", sort_order=2)
    kids = make_category("Kids", parent=hair)
    make_category("Old", is_deleted=True, deleted_at=timezone.now())
    cut = make_service("Haircut", tax=tax, category=hair)
    perm = make_service("Old perm", tax=tax, category=hair, is_active=False, archived_at=timezone.now())
    make_service("Gloss", tax=tax)

    read = sorted(queries.categories_in_copy(direct()), key=lambda one: one["name"])

    # One the copy had deleted already is not the moment's: it never comes back. Its services, archived ones too.
    assert read == [
        {
            "id": hair.pk,
            "name": "Hair",
            "description": "Cuts and styling",
            "icon": "ion:cut-outline",
            "color": "#aa3300",
            "sort_order": 2,
            "parent_id": None,
            "service_ids": sorted([cut.pk, perm.pk]),
        },
        {
            "id": kids.pk,
            "name": "Kids",
            "description": "",
            "icon": "",
            "color": "",
            "sort_order": 0,
            "parent_id": hair.pk,
            "service_ids": [],
        },
    ]


def test_a_copy_without_the_service_table_gives_its_categories_with_no_service():
    hair = make_category("Hair")
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE service_service CASCADE")

    assert [(one["id"], one["service_ids"]) for one in queries.categories_in_copy(direct())] == [(hair.pk, [])]


def test_a_copy_without_the_category_table_gives_no_category():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE service_category CASCADE")

    assert queries.categories_in_copy(direct()) == []


def test_the_categories_the_business_lacks_come_parents_first_each_as_its_create_takes_it():
    hair = make_category("Hair")
    color = make_category("Color", color="#cc0066", sort_order=4, is_deleted=True, deleted_at=timezone.now())
    hands = a_category_of_the_copy(name="Hands", description="Manicure and more", icon="ion:hand-left-outline")
    copy = [
        # Its parent comes back too: listed after it in the copy, made before it.
        nails := a_category_of_the_copy(name="Nails", parent_id=hands["id"], sort_order=1),
        hands,
        in_color := a_category_of_the_copy(color),
        a_category_of_the_copy(hair),
        toning := a_category_of_the_copy(name="Toning", parent_id=color.pk),
        kids := a_category_of_the_copy(name="Kids", parent_id=hair.pk),
    ]

    lacking = queries.categories_not_in_business(copy)

    assert lacking == [
        made_again(hands, nails),
        made_again(in_color, toning),
        # Into a parent brought back just before, by its name (it has no id here yet); into one kept, by its id.
        made_again(nails, parent="Hands"),
        made_again(toning, parent="Color"),
        made_again(kids, parent_id=hair.pk),
    ]
    for record in lacking:
        CategoryRecoverIn.model_validate({key: value for key, value in record.items() if key != "id"})


def test_a_category_the_business_made_again_is_never_made_twice_and_its_children_go_into_it():
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    # Made again by hand since: the same name, the case and the spaces aside (a live name is unique).
    again = make_category("color ")
    copy = [a_category_of_the_copy(gone), toning := a_category_of_the_copy(name="Toning", parent_id=gone.pk)]

    assert queries.categories_not_in_business(copy) == [made_again(toning, parent_id=again.pk)]


def test_a_loop_a_raw_write_left_in_the_copy_never_hangs_and_gives_each_category_once():
    hair, cuts = a_category_of_the_copy(name="Hair"), a_category_of_the_copy(name="Cuts")
    # No operation leaves one (SERVICE-F07 refuses it), a raw write may (``delete_category`` says so too).
    hair["parent_id"], cuts["parent_id"] = cuts["id"], hair["id"]
    by_id = {one["id"]: one for one in (hair, cuts)}
    depths: list[int] = []
    counting = threading.Thread(target=lambda: depths.extend(queries._depth(one, by_id) for one in (hair, cuts)))
    counting.daemon = True  # a loop that never ends must not keep the run alive

    counting.start()
    counting.join(timeout=5)

    assert depths == [1, 1]
    assert [(one["name"], one.get("parent")) for one in queries.categories_not_in_business([hair, cuts])] == [
        ("Hair", "Cuts"),
        ("Cuts", "Hair"),
    ]


def test_the_lacking_categories_are_created_as_the_screen_creates_them_and_asking_again_makes_none_twice():
    color = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    copy = [
        a_category_of_the_copy(name="Toning", parent_id=color.pk, sort_order=2),
        a_category_of_the_copy(color),
    ]

    made = [create(record, "service.category.recover") for record in queries.categories_not_in_business(copy)]

    assert [(one.name, one.parent_name) for one in made] == [("Color", None), ("Toning", "Color")]
    assert color.pk not in {one.id for one in made}
    assert queries.categories_not_in_business(copy) == []


def a_recovery() -> str:
    """The actor a recovery runs as, a new one each time (``base.recovery.actor_of``)."""
    return actor_of(uuid.uuid7())


def brought_back(name: str, recovery: str, **fields) -> Category:
    """A category ``recovery`` made again with ``name``, as the categories' part leaves it in the business."""
    return make_category(name, created_by=recovery, **fields)


def put_back(services: list[dict], subcategories: list[dict], recovery: str) -> None:
    """Each link created as the platform does, as ``recovery``."""
    for one in services:
        create(one, "service.service.return_to_category", recovery)
    for one in subcategories:
        create(one, "service.category.return_to_parent", recovery)


def test_a_category_made_again_gets_back_what_the_business_kept_where_its_deletion_left_it_each_by_its_link():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    gone = make_category("Color", parent=hair, is_deleted=True, deleted_at=timezone.now())
    # Where deleting it left them: its services without a category, its subcategory under its parent.
    gloss, perm = make_service("Gloss", tax=tax), make_service("Old perm", tax=tax, is_active=False)
    toning = make_category("Toning", parent=hair)
    copy = a_category_of_the_copy(gone, service_ids=[gloss.pk, perm.pk, uuid.uuid7()])
    # One the business deleted too comes back by Categories' own part, into it by its name: the deleted one stays.
    pastel = make_category("Pastel", parent=hair, is_deleted=True, deleted_at=timezone.now())
    in_copy = [
        a_category_of_the_copy(hair),
        copy,
        a_category_of_the_copy(toning, parent_id=gone.pk),
        a_category_of_the_copy(pastel, parent_id=gone.pk),
    ]
    [record, _pastel] = queries.categories_not_in_business(in_copy)
    recovery = a_recovery()

    made = create(record, "service.category.recover", recovery)

    # Made again, and nothing of the business's moved yet: that goes back by links of its own, counted apart.
    assert (made.name, made.parent_id, made.left_out) == ("Color", hair.pk, [])
    assert made.id != gone.pk
    assert set(Service.objects.filter(pk__in=[gloss.pk, perm.pk]).values_list("category", flat=True)) == {None}
    assert Category.objects.get(pk=toning.pk).parent_id == hair.pk

    services = queries.service_links_not_in_business(in_copy)
    subcategories = queries.subcategory_links_not_in_business(in_copy)

    assert services == [
        {"id": one, "service_id": one, "category_id": made.id} for one in sorted([gloss.pk, perm.pk])
    ]
    assert subcategories == [{"id": toning.pk, "category_id": toning.pk, "parent_id": made.id, "stands_for": gone.pk}]
    put_back(services, subcategories, recovery)
    assert dict(Service.objects.filter(pk__in=[gloss.pk, perm.pk]).values_list("pk", "category")) == {
        gloss.pk: made.id,
        perm.pk: made.id,
    }
    assert Category.objects.get(pk=toning.pk).parent_id == made.id
    assert Category.objects.get(pk=pastel.pk).parent_id == hair.pk
    # Who put each one back is written on it, as on any change of the screen.
    assert set(Service.objects.filter(pk__in=[gloss.pk, perm.pk]).values_list("updated_by", flat=True)) == {recovery}
    assert Category.objects.get(pk=toning.pk).updated_by == recovery
    # Asked again, nothing goes back twice.
    assert queries.service_links_not_in_business(in_copy) == []
    assert queries.subcategory_links_not_in_business(in_copy) == []


def test_a_lost_category_gets_back_the_subcategories_its_loss_left_at_the_root():
    toning = make_category("Toning")
    copy = a_category_of_the_copy(name="Color")
    in_copy = [copy, a_category_of_the_copy(toning, parent_id=copy["id"])]
    [record] = queries.categories_not_in_business(in_copy)
    recovery = a_recovery()
    made = create(record, "service.category.recover", recovery)

    [link] = queries.subcategory_links_not_in_business(in_copy)
    put_back([], [link], recovery)

    assert link == {"id": toning.pk, "category_id": toning.pk, "parent_id": made.id, "stands_for": copy["id"]}
    assert Category.objects.get(pk=toning.pk).parent_id == made.id


def test_what_the_business_moved_since_stays_where_it_is_and_the_category_says_it_came_back_without_it():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    # Moved by hand since its deletion: a service into Hair, a subcategory from the root into Hair.
    balayage = make_service("Balayage", tax=tax, category=hair)
    toning = make_category("Toning", parent=hair)
    in_copy = [a_category_of_the_copy(gone, service_ids=[balayage.pk]), a_category_of_the_copy(toning, parent_id=gone.pk)]
    [record] = queries.categories_not_in_business(in_copy)

    made = create(record, "service.category.recover", a_recovery())

    assert [(one.code, str(subject) in one.message) for one, subject in zip(made.left_out, (balayage.pk, toning.pk))] == [
        ("service.service_moved", True),
        ("service.subcategory_moved", True),
    ]
    assert queries.service_links_not_in_business(in_copy) == []
    assert queries.subcategory_links_not_in_business(in_copy) == []
    assert Service.objects.get(pk=balayage.pk).category_id == hair.pk
    assert Category.objects.get(pk=toning.pk).parent_id == hair.pk


def test_a_subcategory_whose_return_would_close_a_loop_stays_where_it_is_and_is_said():
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    # Left at the root by the deletion; since then the business hung Hair, Color's parent in the copy, from it.
    toning = make_category("Toning")
    hair = make_category("Hair", parent=toning)
    in_copy = [
        a_category_of_the_copy(hair, parent_id=None),
        a_category_of_the_copy(gone, parent_id=hair.pk),
        a_category_of_the_copy(toning, parent_id=gone.pk),
    ]
    [record] = queries.categories_not_in_business(in_copy)

    made = create(record, "service.category.recover", a_recovery())

    assert made.parent_id == hair.pk
    assert [(one.code, str(toning.pk) in one.message) for one in made.left_out] == [("service.subcategory_loop", True)]
    assert queries.subcategory_links_not_in_business(in_copy) == []
    assert Category.objects.get(pk=toning.pk).parent_id is None


@pytest.mark.parametrize("held", ["kept", "made_again_by_hand"])
def test_a_category_the_business_kept_or_made_again_by_hand_is_its_own_and_gets_nothing_back_by_links(held):
    tax = make_tax("test.service", "Service — test")
    # Untouched since before the category came to be, without a category and at the root.
    gloss, toning = make_service("Gloss", tax=tax), make_category("Toning")
    # Brought back by an earlier recovery and kept since: the copy's own, live under its id.
    color = brought_back("Color", a_recovery())
    if held == "made_again_by_hand":
        Category.objects.filter(pk=color.pk).update(is_deleted=True, deleted_at=timezone.now())
        make_category("COLOR", created_by="Ana Gil")
    in_copy = [a_category_of_the_copy(color, service_ids=[gloss.pk]), a_category_of_the_copy(toning, parent_id=color.pk)]

    assert queries.service_links_not_in_business(in_copy) == []
    assert queries.subcategory_links_not_in_business(in_copy) == []


def test_what_the_business_touched_after_the_category_came_back_stays_as_it_is():
    tax = make_tax("test.service", "Service — test")
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    cut, gloss = make_service("Cut", tax=tax), make_service("Gloss", tax=tax)
    kids, toning = make_category("Kids"), make_category("Toning")
    back = brought_back("Color", a_recovery())
    # Changed by hand after it came back, without a category or at the root still: as when it is asked again.
    gloss.notes = "Ask about the shade"
    gloss.save()
    toning.icon = "ion:color-palette-outline"
    toning.save()
    in_copy = [
        a_category_of_the_copy(gone, service_ids=[cut.pk, gloss.pk]),
        a_category_of_the_copy(kids, parent_id=gone.pk),
        a_category_of_the_copy(toning, parent_id=gone.pk),
    ]

    assert queries.service_links_not_in_business(in_copy) == [{"id": cut.pk, "service_id": cut.pk, "category_id": back.pk}]
    assert queries.subcategory_links_not_in_business(in_copy) == [
        {"id": kids.pk, "category_id": kids.pk, "parent_id": back.pk, "stands_for": gone.pk}
    ]


def links_of(recovery: str, *, services=(), subcategories=()) -> tuple[list[dict], list[dict]]:
    """The links of a deleted Color with ``services`` and ``subcategories`` inside, read once ``recovery`` brought it
    back: each at the root still, untouched since."""
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    brought_back("Color", recovery)
    in_copy = [a_category_of_the_copy(gone, service_ids=[one.pk for one in services])]
    in_copy += [a_category_of_the_copy(one, parent_id=gone.pk) for one in subcategories]
    return queries.service_links_not_in_business(in_copy), queries.subcategory_links_not_in_business(in_copy)


def test_one_the_business_moved_after_its_link_was_read_stays_where_it_put_it_and_says_why():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    balayage, toning = make_service("Balayage", tax=tax), make_category("Toning")
    recovery = a_recovery()
    [service], [subcategory] = links_of(recovery, services=[balayage], subcategories=[toning])
    Service.objects.filter(pk=balayage.pk).update(category=hair)
    Category.objects.filter(pk=toning.pk).update(parent=hair)

    with pytest.raises(Conflict) as moved:
        create(service, "service.service.return_to_category", recovery)
    with pytest.raises(Conflict) as moved_too:
        create(subcategory, "service.category.return_to_parent", recovery)

    assert (moved.value.code, moved_too.value.code) == ("service.service_moved", "service.subcategory_moved")
    assert str(balayage.pk) in moved.value.message and str(toning.pk) in moved_too.value.message
    assert Service.objects.get(pk=balayage.pk).category_id == hair.pk
    assert Category.objects.get(pk=toning.pk).parent_id == hair.pk


def test_a_subcategory_hung_since_its_link_was_read_so_that_its_return_closes_a_loop_stays_where_it_is():
    toning = make_category("Toning")
    recovery = a_recovery()
    [], [subcategory] = links_of(recovery, subcategories=[toning])
    Category.objects.filter(pk=subcategory["parent_id"]).update(parent=toning)

    with pytest.raises(Conflict) as loop:
        create(subcategory, "service.category.return_to_parent", recovery)

    assert loop.value.code == "service.subcategory_loop"
    assert Category.objects.get(pk=toning.pk).parent_id is None


def test_a_category_an_earlier_recovery_brought_back_is_the_businesss_and_takes_nothing_back():
    tax = make_tax("test.service", "Service — test")
    gloss, toning = make_service("Gloss", tax=tax), make_category("Toning")
    [service], [subcategory] = links_of(a_recovery(), services=[gloss], subcategories=[toning])

    now = a_recovery()
    with pytest.raises(Conflict) as kept:
        create(service, "service.service.return_to_category", now)
    with pytest.raises(Conflict) as kept_too:
        create(subcategory, "service.category.return_to_parent", now)

    assert (kept.value.code, kept_too.value.code) == ("service.category_brought_earlier",) * 2
    assert Service.objects.get(pk=gloss.pk).category_id is None
    assert Category.objects.get(pk=toning.pk).parent_id is None


@pytest.mark.parametrize("name", ["service.service.return_to_category", "service.category.return_to_parent"])
def test_putting_back_what_a_category_had_inside_is_only_the_systems(name):
    op = get(name)

    assert op.permission == "service.system"
    assert not ctx_for("hub_owner").has(op.permission)


def test_what_a_category_came_back_without_is_said_in_the_language_it_is_made_in():
    tax = make_tax("test.service", "Service — test")
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    balayage = make_service("Balayage", tax=tax, category=make_category("Hair"))
    [record] = queries.categories_not_in_business([a_category_of_the_copy(gone, service_ids=[balayage.pk])])

    with translation.override("es"):
        [said] = create(record, "service.category.recover").left_out
        spanish = SERVICE_MOVED_LEFT % {"service": balayage.pk}

    assert said.message == spanish
    assert said.message != SERVICE_MOVED_LEFT % {"service": balayage.pk}


def test_making_a_category_again_with_what_it_had_inside_is_only_the_systems():
    op = get("service.category.recover")

    assert op.permission == "service.system"
    assert not ctx_for("hub_owner").has(op.permission)


def test_a_service_whose_category_came_back_goes_into_it():
    tax = make_tax("test.service", "Service — test")
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    # What the categories' part of the same recovery created just before, by its create: a new one, the same name.
    back = make_category("Color")
    services = [a_service_of_the_copy(name="Highlights", category_id=gone.pk, tax_category_id=tax.pk)]

    [record] = queries.services_not_in_business(services)

    assert record["category_id"] == back.pk
    made = create(record)
    # Asked again: the one brought back into it is the business's.
    assert queries.services_in_business(services) == {services[0]["id"]: made.id}


def test_a_category_the_business_renamed_since_is_the_same_one_whoever_took_its_old_name():
    tax = make_tax("test.service", "Service — test")
    hair = make_category("Hair")
    copy = [a_category_of_the_copy(hair), a_category_of_the_copy(name="Kids", parent_id=hair.pk)]
    services = [a_service_of_the_copy(name="Fringe trim", category_id=hair.pk, tax_category_id=tax.pk)]
    # Renamed since, and its old name taken by one made after: the copy's is the renamed one, by its id before any name.
    Category.objects.filter(pk=hair.pk).update(name="Styling")
    make_category("Hair")

    [kids] = queries.categories_not_in_business(copy)
    [record] = queries.services_not_in_business(services)

    assert kids["parent_id"] == hair.pk
    assert record["category_id"] == hair.pk


def test_the_app_declares_what_it_gives_back_its_categories_first_and_what_goes_back_into_them_last():
    categories, services, service_links, subcategory_links = apps.get_app_config("service").recoverable_from_copy()

    assert (categories.read, categories.missing, categories.create) == (
        queries.categories_in_copy,
        queries.categories_not_in_business,
        "service.category.recover",
    )
    assert (services.read, services.missing, services.create) == (
        queries.recoverable_services_in_copy,
        queries.services_not_in_business,
        "service.service.recover",
    )
    assert (service_links.read, service_links.missing, service_links.create) == (
        queries.categories_in_copy,
        queries.service_links_not_in_business,
        "service.service.return_to_category",
    )
    assert (subcategory_links.read, subcategory_links.missing, subcategory_links.create) == (
        queries.categories_in_copy,
        queries.subcategory_links_not_in_business,
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
    assert set(queries.COPY_FIELDS) <= fields_held_since("service", "service", services.reads_since)
    # What categories_in_copy reads of each table is there since the migration each of its readers names.
    for one in (categories, service_links, subcategory_links):
        held = {"id", *queries.CATEGORY_COPY_FIELDS, "parent", "is_deleted"}
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


@pytest.mark.usefixtures("no_test_fallback")
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
