"""Who performs a service a recovery from a separate copy makes again (SERVICE-F31): each professional who performed it
in the copy and the business still has, assigned by the screen's own operation, with their own minutes and price.
"""

import uuid

from django.db import connections
from django.utils import timezone, translation
from live.models import OutboxEvent

from apps.service import queries
from apps.service.models import Assignment
from apps.service.schemas.recovery import ServiceRecoverIn
from apps.service.services.service_recovery import MEMBER_TERMINATED_LEFT
from apps.staff.models import Member
from base.tenancy.context import current_alias

from .conftest import HUB_DB, make_member, make_service, make_tax
from .test_recovery import a_service_of_the_copy, create, direct, performers

pytestmark = HUB_DB


def an_assignment_of_the_copy(member: Member, **fields) -> dict:
    """A professional who performed a service in the copy, as ``recoverable_services_in_copy`` gives it."""
    return {
        "member_id": member.pk,
        "custom_duration": None,
        "custom_price": None,
        "is_primary": False,
        "is_active": True,
    } | fields


def test_the_copy_gives_each_service_with_who_performed_it_there_archived_ones_too():
    tax = make_tax("test.service", "Service — test")
    ana, sonia = make_member("Ana", "López"), make_member("Sonia", "Ruiz")
    keratin = make_service("Keratin treatment", tax=tax, price=9000)
    perm = make_service("Old perm", tax=tax, is_active=False, archived_at=timezone.now())
    manicure = make_service("Manicure", tax=tax)
    Assignment.objects.create(service=keratin, member=ana, custom_duration=75, custom_price=9500, is_primary=True)
    Assignment.objects.create(service=keratin, member=sonia, custom_price=8000, is_active=False)
    Assignment.objects.create(service=perm, member=sonia)

    read = {one["id"]: one for one in queries.recovery.recoverable_services_in_copy(direct())}

    plain = {one["id"]: one for one in queries.recovery.services_in_copy(direct())}
    assert {pk: {key: value for key, value in one.items() if key != "assignments"} for pk, one in read.items()} == plain
    assert read[keratin.pk]["assignments"] == [
        an_assignment_of_the_copy(ana, custom_duration=75, custom_price=9500, is_primary=True),
        an_assignment_of_the_copy(sonia, custom_price=8000, is_active=False),
    ]
    assert read[perm.pk]["assignments"] == [an_assignment_of_the_copy(sonia)]
    assert read[manicure.pk]["assignments"] == []


def test_a_copy_without_the_apps_tables_gives_nobody():
    with connections[current_alias()].cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE service_assignment, service_service CASCADE")

    assert queries.recovery.recoverable_services_in_copy(direct()) == []


def test_each_lacking_service_comes_with_who_performed_it_in_the_copy():
    tax = make_tax("test.service", "Service — test")
    ana = make_member("Ana", "López")
    performed = [an_assignment_of_the_copy(ana, custom_duration=75, custom_price=9500)]
    lost = a_service_of_the_copy(name="Keratin treatment", tax_category_id=tax.pk, assignments=performed)

    [record] = queries.recovery.services_not_in_business([lost])

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
    [record] = queries.recovery.services_not_in_business(
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
    [record] = queries.recovery.services_not_in_business(
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
    [record] = queries.recovery.services_not_in_business(
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
    [record] = queries.recovery.services_not_in_business(
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
    [record] = queries.recovery.services_not_in_business(
        [a_service_of_the_copy(name="Keratin treatment", tax_category_id=tax.pk, assignments=performed)]
    )

    create(record)

    assert performers("Keratin treatment") == [("Ana", None, None, True, True), ("Sonia", None, None, False, True)]
    assert performers("Nails") == [("Ana", None, None, False, True), ("Sonia", None, None, True, True)]
