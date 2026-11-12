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
performed it in the copy and the business still has (``queries.recoverable_services_in_copy``, hub#1322) by
``service.assignment.assign``, the screen's own too (SERVICE-F31).
"""

import threading
import uuid

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone
from live.errors import InvalidPayload
from live.models import OutboxEvent
from live.operations import get

from apps.service import queries
from apps.service.models import Assignment, Category, Service
from apps.service.schemas import CategoryIn, ServiceRecoverIn
from apps.staff.models import Member
from apps.tax.models import TaxCategory
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import Recoveries, fresh, run, run_in

from .conftest import ctx_for, make_category, make_member, make_service, make_tax

pytestmark = pytest.mark.django_db


def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


def create(record: dict, operation: str = "service.service.recover") -> dict:
    """``record`` created as the platform does, as the system: its create's input, all of it but its id in the copy."""
    op = get(operation)
    ctx = ctx_for(actor="system", permissions={"*"})
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
    assert lacking[0] == {key: value for key, value in in_hair.items() if key not in read_only} | {
        "category_id": hair.pk,
        "tax_category_key": "test.service",
    }
    assert lacking[1] == {key: value for key, value in in_gone.items() if key not in read_only} | {
        "tax_category_key": "test.service"
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


# ── Who performs each one (hub#1322): each professional the business still has, assigned by the screen's operation ──


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
    performed = [
        an_assignment_of_the_copy(ana, is_primary=True),
        an_assignment_of_the_copy(sonia, is_primary=True),
    ]
    [record] = queries.services_not_in_business(
        [a_service_of_the_copy(name="Keratin treatment", tax_category_id=tax.pk, assignments=performed)]
    )

    create(record)

    assert performers("Keratin treatment") == [("Ana", None, None, True, True), ("Sonia", None, None, False, True)]
    assert performers("Nails") == [("Sonia", None, None, True, True)]


def test_making_a_service_again_with_who_performed_it_is_only_the_systems():
    op = get("service.service.recover")

    assert op.permission == "service.system"
    assert not ctx_for("hub_owner").has(op.permission)


# ── Its categories (hub#1323): those the business lacks come back first, each by the screen's create ─────────────


#: A category of the copy with what a new one has, as ``categories_in_copy`` gives it.
NEW_CATEGORY = {"name": "", "description": "", "icon": "", "color": "", "sort_order": 0, "parent_id": None}


def a_category_of_the_copy(category: Category | None = None, **fields) -> dict:
    """A category as the copy gives it (``categories_in_copy``): ``category``'s, or a new one with ``fields``."""
    if category is not None:
        return {"id": category.pk} | {field: getattr(category, field) for field in NEW_CATEGORY}
    return {"id": uuid.uuid7()} | NEW_CATEGORY | fields


def test_the_copy_gives_each_live_category_with_what_its_create_takes():
    hair = make_category("Hair", description="Cuts and styling", icon="ion:cut-outline", color="#aa3300", sort_order=2)
    kids = make_category("Kids", parent=hair)
    make_category("Old", is_deleted=True, deleted_at=timezone.now())

    read = sorted(queries.categories_in_copy(direct()), key=lambda one: one["name"])

    # One the copy had deleted already is not the moment's: it never comes back.
    assert read == [
        {
            "id": hair.pk,
            "name": "Hair",
            "description": "Cuts and styling",
            "icon": "ion:cut-outline",
            "color": "#aa3300",
            "sort_order": 2,
            "parent_id": None,
        },
        {"id": kids.pk, "name": "Kids", "description": "", "icon": "", "color": "", "sort_order": 0, "parent_id": hair.pk},
    ]


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

    def created(one: dict, **parent) -> dict:
        return {key: value for key, value in one.items() if key != "parent_id"} | parent

    assert lacking == [
        created(hands),
        created(in_color),
        # Into a parent brought back just before, by its name (it has no id here yet); into one kept, by its id.
        created(nails, parent="Hands"),
        created(toning, parent="Color"),
        created(kids, parent_id=hair.pk),
    ]
    for record in lacking:
        CategoryIn.model_validate({key: value for key, value in record.items() if key != "id"})


def test_a_category_the_business_made_again_is_never_made_twice_and_its_children_go_into_it():
    gone = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    # Made again by hand since: the same name, the case and the spaces aside (a live name is unique).
    again = make_category("color ")
    copy = [a_category_of_the_copy(gone), toning := a_category_of_the_copy(name="Toning", parent_id=gone.pk)]

    assert queries.categories_not_in_business(copy) == [
        {key: value for key, value in toning.items() if key != "parent_id"} | {"parent_id": again.pk}
    ]


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


def test_the_lacking_categories_are_created_by_the_screens_operation_and_asking_again_makes_none_twice():
    color = make_category("Color", is_deleted=True, deleted_at=timezone.now())
    copy = [
        a_category_of_the_copy(name="Toning", parent_id=color.pk, sort_order=2),
        a_category_of_the_copy(color),
    ]

    made = [create(record, "service.category.create") for record in queries.categories_not_in_business(copy)]

    assert [(one.name, one.parent_name) for one in made] == [("Color", None), ("Toning", "Color")]
    assert color.pk not in {one.id for one in made}
    assert queries.categories_not_in_business(copy) == []


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


def test_the_app_declares_what_it_gives_back_its_categories_first():
    categories, services = apps.get_app_config("service").recoverable_from_copy()

    assert (categories.read, categories.missing, categories.create) == (
        queries.categories_in_copy,
        queries.categories_not_in_business,
        "service.category.create",
    )
    assert (services.read, services.missing, services.create) == (
        queries.recoverable_services_in_copy,
        queries.services_not_in_business,
        "service.service.recover",
    )
    assert (str(categories.label), str(services.label)) == ("Service categories", "Services")
    assert categories.reads_since == services.reads_since == "0001_initial"


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


def recovered(recoveries, copy) -> dict:
    """Services asked back from ``copy`` and the worker's pass run: what the app gave back."""
    row = recoveries.ask(copy, "service")
    assert run() == 1
    [result] = fresh(row).results
    return result


def live_categories(hub) -> list[tuple]:
    """The business's live categories: name, its parent's name, colour and order, by name."""
    with use_hub(hub):
        return [
            (one.name, one.parent.name if one.parent else None, one.color, one.sort_order)
            for one in Category.objects.filter(is_deleted=False).select_related("parent").order_by("name", "id")
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
        [result] = row.results
        assert row.status == "done"
        # The category the business deleted and the two services: one result, the app's.
        assert (result["app"], result["created"], result["not_created"], result["reasons"], result["refused"]) == (
            "service", 3, 0, [], ""
        )
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

    def test_asked_again_nothing_is_made_twice_and_what_the_business_has_stays(self, recoveries, every_app_on):
        hub, tax, ids, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        gone(hub, ids["keratin"])
        recoveries.ask(copy, "service")
        assert run() == 1
        run_in(hub, "service.service.archive", id=ids["cut"])
        before = created_events(hub)

        result = recovered(recoveries, copy)

        assert (result["created"], result["not_created"], result["refused"]) == (0, 0, "")
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

        assert (first["created"], first["not_created"], first["refused"]) == (3, 0, "")
        assert (again["created"], again["not_created"], again["refused"]) == (0, 0, "")
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

        result = recovered(recoveries, copy)

        # Only the service: the category is the business's already.
        assert (result["created"], result["not_created"], result["reasons"], result["refused"]) == (1, 0, [], "")
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

        # One service made again, its professionals with it.
        assert (first["created"], first["not_created"], first["reasons"], first["refused"]) == (1, 0, [], "")
        assert (again["created"], again["not_created"], again["refused"]) == (0, 0, "")
        with use_hub(hub):
            back = Service.objects.get(name="Keratin treatment")
            assert back.pk != ids["keratin"]
            assert performers("Keratin treatment") == [("Ana", 75, 9500, False, True), ("Sonia", None, 8000, False, False)]
        assert created_events(hub, "service.assignment.assigned") == before + 2

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
