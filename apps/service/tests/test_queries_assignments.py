"""Who performs each service: an assignment by its id, the professionals of a service, the services of a professional
and who may perform a service."""

import uuid

import pytest
from live.errors import NotFound

from apps.service.models.catalog import Assignment
from apps.service.schemas.assignments import AssignmentListIn, EligibleIn
from apps.service.schemas.fields import ByIdIn

from .conftest import HUB_DB, make_member, make_service, run

pytestmark = HUB_DB


# ── A record by its id, as the assistant's card names it ────────────────────────────────────────

def test_an_assignment_by_its_id_says_the_service_and_the_professional():
    service, member = make_service("Corte"), make_member("Ana", "López")
    assignment = Assignment.objects.create(service=service, member=member)
    found = run("service.assignment.get", ByIdIn(id=assignment.id), role="hub_employee")
    assert (found.id, found.label) == (assignment.id, "Corte · Ana López")


def test_an_assignment_of_a_professional_who_left_is_not_there():
    member = make_member("Ana", "López", status="terminated")
    assignment = Assignment.objects.create(service=make_service("Corte"), member=member)
    with pytest.raises(NotFound) as error:
        run("service.assignment.get", ByIdIn(id=assignment.id))
    assert error.value.code == "service.assignment_not_found"
    with pytest.raises(NotFound):
        run("service.assignment.get", ByIdIn(id=uuid.uuid7()))


# ── Who performs each service ─────────────────────────────────────────────────────────────────


def test_the_professionals_of_a_service_and_the_services_of_a_professional(tax):
    cut, colour = (
        make_service("Cut", tax=tax, price=2000, duration_minutes=30),
        make_service("Colour", tax=tax),
    )
    ana, bea = make_member("Ana", "López"), make_member("Bea", "Ruiz")
    Assignment.objects.create(service=cut, member=ana, custom_price=2500)
    Assignment.objects.create(
        service=cut, member=bea, is_primary=True, custom_duration=40
    )
    Assignment.objects.create(service=colour, member=ana)
    of_cut = run("service.assignment.list", AssignmentListIn(service_id=cut.id))
    assert [
        (row.member_name, row.duration, row.price, row.is_primary)
        for row in of_cut.rows
    ] == [
        ("Bea Ruiz", 40, 2000, True),
        ("Ana López", 30, 2500, False),
    ]
    of_ana = run("service.assignment.list", AssignmentListIn(member="ana"))
    assert [row.service_name for row in of_ana.rows] == ["Colour", "Cut"]
    assert run("service.assignment.list", AssignmentListIn(service="cut")).total == 2


def test_who_may_perform_a_service_is_the_active_bookable_people_with_an_active_assignment(
    tax,
):
    cut = make_service("Cut", tax=tax, price=2000, duration_minutes=30)
    ana, bea = make_member("Ana", "López", color="#AA3300"), make_member("Bea", "Ruiz")
    cris, dani = (
        make_member("Cris", "Gil", is_bookable=False),
        make_member("Dani", "Sanz", status="inactive"),
    )
    eva = make_member("Eva", "Mar")
    Assignment.objects.create(service=cut, member=ana, custom_price=2500)
    Assignment.objects.create(service=cut, member=bea, is_primary=True)
    Assignment.objects.create(service=cut, member=cris)
    Assignment.objects.create(service=cut, member=dani)
    Assignment.objects.create(service=cut, member=eva, is_active=False)
    page = run("service.assignment.eligible", EligibleIn(service="Cut"))
    assert [
        (row.full_name, row.price, row.duration, row.is_primary) for row in page.rows
    ] == [
        ("Bea Ruiz", 2000, 30, True),
        ("Ana López", 2500, 30, False),
    ]
    assert page.rows[1].color == "#AA3300"


def test_nobody_assigned_is_an_empty_list():
    assert (
        run(
            "service.assignment.eligible", EligibleIn(service_id=make_service("Cut").id)
        ).rows
        == []
    )
