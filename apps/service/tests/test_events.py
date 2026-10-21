"""The service app's events (``service.<entity>.<fact>``) and its reactions to Staff's and Customers' events.

Here a reaction is tested by handing ``react`` the event as the relay does: its name, its scope and its
payload; ``test_relay.py`` drives the worker's real relay end to end.
"""

import re
import uuid

import pytest
from django.utils import timezone
from live.context import Scope
from live.operations import NAME_RE

from apps.service import events
from apps.service.models import Assignment, Grant, GrantAdjustment, Redemption
from apps.service.tests.conftest import (
    make_customer,
    make_grant,
    make_member,
    make_package,
    make_redemption,
    make_service,
)

PAST_FACT = re.compile(r"^service\.[a-z_]+\.[a-z_]+ed$")
A = Scope("host", "a")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str) and value.startswith("service.")
    }


def test_the_events_of_the_workbook():
    assert declared() == {
        "SERVICE_CREATED": "service.service.created",
        "SERVICE_UPDATED": "service.service.updated",
        "SERVICE_ARCHIVED": "service.service.archived",
        "SERVICE_RESTORED": "service.service.restored",
        "CATEGORY_CREATED": "service.category.created",
        "CATEGORY_UPDATED": "service.category.updated",
        "CATEGORY_DELETED": "service.category.deleted",
        "SETTINGS_UPDATED": "service.settings.updated",
        "ASSIGNMENT_ASSIGNED": "service.assignment.assigned",
        "ASSIGNMENT_UPDATED": "service.assignment.updated",
        "ASSIGNMENT_REMOVED": "service.assignment.removed",
        "PACKAGE_CREATED": "service.package.created",
        "PACKAGE_UPDATED": "service.package.updated",
        "PACKAGE_DELETED": "service.package.deleted",
        "GRANT_GRANTED": "service.grant.granted",
        "GRANT_VOIDED": "service.grant.voided",
        "GRANT_ADJUSTED": "service.grant.adjusted",
        "GRANT_REDEEMED": "service.grant.redeemed",
        "GRANT_REASSIGNED": "service.grant.reassigned",
        "GRANT_ERASED": "service.grant.erased",
        "SESSION_RESERVED": "service.session.reserved",
        "SESSION_RELEASED": "service.session.released",
        "SESSION_SETTLED": "service.session.settled",
        "SESSION_EXPIRED": "service.session.expired",
        "SESSION_RETURNED": "service.session.returned",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


def test_it_reacts_to_a_professional_leaving_and_to_a_card_merged_or_erased():
    assert events.REACTIONS == {
        "staff.member.terminated": "service.assignment.release_member",
        "customer.customer.merged": "service.grant.reassign",
        "customer.customer.erased": "service.grant.forget_customer",
    }


@pytest.mark.django_db
def test_a_professional_who_leaves_stops_performing_every_service_as_the_system():
    ana, bea = make_member("Ana"), make_member("Bea")
    cut, colour = make_service("Cut"), make_service("Colour")
    for service in (cut, colour):
        Assignment.objects.create(service=service, member=ana)
    Assignment.objects.create(service=cut, member=bea)

    first = events.react(A, "staff.member.terminated", {"id": str(ana.id)})
    again = events.react(A, "staff.member.terminated", {"id": str(ana.id)})

    assert (first.removed, again.removed) == (2, 0)
    assert list(Assignment.objects.values_list("member_id", flat=True)) == [bea.id]


@pytest.mark.django_db
def test_two_cards_merged_move_the_vouchers_to_the_one_that_stays():
    package = make_package("Bono", [make_service()], max_uses=5)
    lucia, duplicate = make_customer("Lucía"), make_customer("Lucia P.")
    make_grant(package, duplicate)
    make_grant(package, duplicate, voided_at=None)

    merged = events.react(
        A,
        "customer.customer.merged",
        {"id": str(lucia.id), "absorbed_id": str(duplicate.id)},
    )
    again = events.react(
        A,
        "customer.customer.merged",
        {"id": str(lucia.id), "absorbed_id": str(duplicate.id)},
    )

    assert (merged.moved, again.moved) == (2, 0)
    assert set(Grant.objects.values_list("customer_id", flat=True)) == {lucia.id}


@pytest.mark.django_db
def test_a_card_erased_empties_the_free_texts_of_its_vouchers_once():
    cut = make_service()
    lucia, other = make_customer("Lucía"), make_customer("Marta")
    grant = make_grant(make_package("Bono", [cut], max_uses=5), lucia, amount=9000, note="Lucía paid in cash")
    voided = make_grant(make_package("Other", max_uses=1), lucia, voided_at=timezone.now(), void_reason="Lucía asked for it")
    GrantAdjustment.objects.create(grant=grant, uses_delta=1, reason="Lucía was ill")
    make_redemption(grant, cut, note="Lucía, Friday")
    kept = make_grant(make_package("Kept", max_uses=1), other, note="Marta's")

    first = events.react(A, "customer.customer.erased", {"id": str(lucia.id)})
    again = events.react(A, "customer.customer.erased", {"id": str(lucia.id)})

    assert (first.erased, again.erased) == (2, 0)
    grant.refresh_from_db()
    voided.refresh_from_db()
    kept.refresh_from_db()
    assert (grant.note, voided.void_reason, kept.note) == ("", "", "Marta's")
    assert list(GrantAdjustment.objects.values_list("reason", "uses_delta")) == [("", 1)]
    assert list(Redemption.objects.values_list("note", flat=True)) == [""]
    assert (grant.amount, grant.customer_id, Redemption.objects.count()) == (9000, lucia.id, 1)


@pytest.mark.django_db
def test_an_event_it_does_not_react_to_does_nothing():
    assert events.react(A, "staff.member.created", {"id": str(uuid.uuid7())}) is None
    assert (
        events.react(A, "customer.customer.deleted", {"id": str(uuid.uuid7())}) is None
    )


def test_the_sessions_of_the_till_are_not_reactions_sales_calls_them_by_name():
    # Sales reserves, releases, delivers and gives back sessions in its own transaction (WORKBOOK
    # «Contrato con Ventas»): nothing here waits for an event of Sales.
    assert not [name for name in events.REACTIONS if name.startswith("sale.")]
    assert events.SESSION_EVENTS == [
        "service.session.reserved",
        "service.session.released",
        "service.session.settled",
        "service.session.expired",
        "service.session.returned",
    ]
