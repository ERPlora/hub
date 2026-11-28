"""Writes of who performs each service: assign a professional, change or remove the assignment, and release them."""

import uuid

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from apps.service.models.catalog import Assignment
from apps.service.schemas.assignments import MemberReleaseIn

from .conftest import HUB_DB, events, make_member, make_service, payload, run

pytestmark = HUB_DB


def test_assign_a_professional_by_name_with_their_own_time_and_price(tax):
    cut = make_service("Cut", tax=tax, price=2000, duration_minutes=30)
    ana = make_member("Ana", "López")
    out = run(
        "service.assignment.assign",
        {
            "service": "Cut",
            "member": "ana lópez",
            "custom_duration": 40,
            "custom_price": 2500,
        },
    )
    assert (
        out.member_id,
        out.service_id,
        out.duration,
        out.price,
        out.is_active,
        out.is_primary,
    ) == (ana.id, cut.id, 40, 2500, True, False)
    assert events() == ["service.assignment.assigned"]
    assert payload("service.assignment.assigned") == {
        "id": str(out.id),
        "service_id": str(cut.id),
        "member_id": str(ana.id),
    }


def test_assigning_again_changes_the_assignment_instead_of_adding_one(tax):
    cut = make_service("Cut", tax=tax)
    ana = make_member("Ana")
    first = run(
        "service.assignment.assign",
        {"service_id": str(cut.id), "member_id": str(ana.id), "custom_duration": 40},
    )
    Assignment.objects.filter(pk=first.id).update(is_active=False)
    again = run(
        "service.assignment.assign",
        {"service_id": str(cut.id), "member_id": str(ana.id), "custom_price": 900},
    )
    assert (again.id, again.custom_duration, again.custom_price, again.is_active) == (
        first.id,
        None,
        900,
        True,
    )
    assert events() == ["service.assignment.assigned", "service.assignment.updated"]


def test_one_main_service_per_professional(tax):
    cut, colour = make_service("Cut", tax=tax), make_service("Colour", tax=tax)
    ana = make_member("Ana")
    first = run(
        "service.assignment.assign",
        {"service": "Cut", "member": "Ana", "is_primary": True},
    )
    second = run(
        "service.assignment.assign",
        {"service": "Colour", "member": "Ana", "is_primary": True},
    )
    assert Assignment.objects.get(pk=first.id).is_primary is False
    assert Assignment.objects.get(pk=second.id).is_primary is True
    run("service.assignment.update", {"id": str(first.id), "is_primary": True})
    assert list(
        Assignment.objects.filter(is_primary=True).values_list("service_id", flat=True)
    ) == [cut.id]
    assert colour.id


def test_a_professional_who_does_not_exist_or_left_cannot_be_assigned(tax):
    make_service("Cut", tax=tax)
    make_member("Gone", status="terminated")
    with pytest.raises(NotFound):
        run("service.assignment.assign", {"service": "Cut", "member": "Gone"})
    make_member("Ana", "López")
    make_member("Ana", "Ruiz")
    with pytest.raises(Conflict) as ambiguous:
        run("service.assignment.assign", {"service": "Cut", "member": "Ana"})
    assert ambiguous.value.code == "staff.ambiguous_member"


def test_update_an_assignment_and_null_brings_back_the_services_own(tax):
    cut = make_service("Cut", tax=tax, price=2000)
    assignment = Assignment.objects.create(
        service=cut, member=make_member(), custom_price=2500, custom_duration=40
    )
    out = run(
        "service.assignment.update",
        {"id": str(assignment.id), "custom_price": None, "is_active": False},
    )
    assert (out.custom_price, out.price, out.custom_duration, out.is_active) == (
        None,
        2000,
        40,
        False,
    )
    assert events() == ["service.assignment.updated"]


def test_remove_an_assignment_and_an_unknown_one_is_not_found(tax):
    assignment = Assignment.objects.create(
        service=make_service("Cut", tax=tax), member=make_member()
    )
    run("service.assignment.remove", {"id": str(assignment.id)})
    assert not Assignment.objects.exists()
    assert events() == ["service.assignment.removed"]
    with pytest.raises(NotFound) as missing:
        run("service.assignment.remove", {"id": str(assignment.id)})
    assert missing.value.message == "That assignment does not exist in this business."


def test_an_employee_reads_assignments_but_does_not_change_them(tax):
    make_service("Cut", tax=tax)
    make_member("Ana")
    with pytest.raises(PermissionDenied):
        run(
            "service.assignment.assign",
            {"service": "Cut", "member": "Ana"},
            role="hub_employee",
        )


def test_releasing_a_professional_is_the_platforms_only():
    with pytest.raises(PermissionDenied):
        run("service.assignment.release_member", MemberReleaseIn(id=uuid.uuid7()))


def test_assigning_again_keeps_the_main_service_unless_it_is_said(tax):
    cut = make_service("Cut", tax=tax)
    ana = make_member("Ana")
    run("service.assignment.assign", {"service": "Cut", "member": "Ana", "is_primary": True})
    again = run("service.assignment.assign", {"service": "Cut", "member": "Ana", "custom_price": 900})
    assert (again.is_primary, again.custom_price) == (True, 900)
    off = run("service.assignment.assign", {"service": "Cut", "member": "Ana", "is_primary": False})
    assert off.is_primary is False
    assert cut.id and ana.id
