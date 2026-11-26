"""Whom a booking is for when the staff give only the guest's phone (RESERVATION-F06): the card that number is on, as
the booking tools of the market fill in the guest's profile from her phone; with no card for it, the booking says who
it is for is missing and makes no card. A guest who books herself (online, WhatsApp) is still booked under her phone."""

import pytest
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound, PermissionDenied
from live.live_registry import live_registry
from live.ninja import operation_ids
from live.operations import get

from apps.customer.models import Customer
from apps.reservation.models import Reservation
from base.sensitive import VIEW_CUSTOMER_CONTACT
from base.tenancy.tests.business import A
from config.api import api

from .conftest import HUB_DB, book, ctx_for, make_customer, open_week, run

pytestmark = HUB_DB

#: A staff booking with only the guest's phone, as the assistant sends it for «me llama la del 600 111 222».
BY_PHONE = {"guest_name": "", "guest_phone": "600 111 222", "source": "phone"}
CHECK = "reservation.reservation.check"


def employee():
    return ctx_for("hub_employee")


def test_a_staff_booking_with_only_the_phone_of_a_card_is_hers_under_her_name():
    open_week()
    lucia = make_customer("Lucía Gómez", phone="+34600111222")
    out = book(ctx=employee(), **BY_PHONE)
    assert (out.customer_id, out.guest_name, out.guest_phone) == (lucia.id, "Lucía Gómez", "+34600111222")
    assert Customer.objects.count() == 1


@pytest.mark.parametrize("source", ["phone", "in_person"])
def test_a_staff_booking_with_only_a_phone_no_card_has_says_whom_it_is_for_is_missing_and_makes_no_card(source):
    with pytest.raises(InvalidPayload) as refused:
        book(ctx=employee(), **{**BY_PHONE, "source": source})
    assert (refused.value.code, set(refused.value.fields)) == ("reservation.no_guest", {"guest_name"})
    assert (Customer.objects.count(), Reservation.objects.count()) == (0, 0)


def test_who_does_not_see_the_customers_contact_does_not_name_a_guest_by_her_phone():
    """Whoever does not see the customers' contact searches a customer only by her name (BASE-F119)."""
    make_customer("Lucía Gómez", phone="+34600111222")
    blind = ctx_for("hub_employee")
    blind = ctx_for(permissions=blind.permissions - {VIEW_CUSTOMER_CONTACT})
    with pytest.raises(InvalidPayload) as refused:
        book(ctx=blind, **BY_PHONE)
    assert refused.value.code == "reservation.no_guest"
    assert Reservation.objects.count() == 0


def test_a_guest_who_books_herself_by_whatsapp_with_only_her_phone_still_gets_her_card():
    open_week()
    out = book(ctx=employee(), **{**BY_PHONE, "source": "whatsapp"})
    card = Customer.objects.get(pk=out.customer_id)
    assert (card.phone, out.guest_name) == ("+34600111222", card.name)


def test_the_check_before_the_card_finds_the_card_of_the_phone():
    lucia = make_customer("Lucía Gómez", phone="+34600111222")
    answer = run(CHECK, {**BY_PHONE, "date": "2026-10-15", "time": "14:00", "party_size": 4}, employee())
    assert answer.id == lucia.id


def test_the_check_before_the_card_refuses_a_phone_no_card_has():
    with pytest.raises(InvalidPayload) as refused:
        run(CHECK, {**BY_PHONE, "date": "2026-10-15", "time": "14:00", "party_size": 4}, employee())
    assert refused.value.code == "reservation.no_guest"


def test_the_check_before_the_card_finds_the_customer_said_by_her_phone_or_refuses_one_nobody_is():
    lucia = make_customer("Lucía Gómez", phone="+34600111222")
    said = {"customer": "600 111 222", "date": "2026-10-15", "time": "14:00", "party_size": 4}
    assert run(CHECK, said, employee()).id == lucia.id
    with pytest.raises(NotFound) as refused:
        run(CHECK, {**said, "customer": "600 999 999"}, employee())
    assert refused.value.code == "customer.customer_unavailable"


def test_the_check_before_the_card_lets_a_named_guest_through_without_reading_a_card():
    answer = run(CHECK, {"guest_name": "Ana", "date": "2026-10-15", "time": "14:00", "party_size": 4}, employee())
    assert answer.id is None


def test_the_check_is_only_on_the_card_and_only_for_who_may_take_reservations():
    """It says whose card a phone is: no route of the API and no live query serve it, and run as someone who may
    only read the book it refuses."""
    assert CHECK not in operation_ids(api)
    assert not live_registry.is_subscribable(CHECK)
    make_customer("Lucía Gómez", phone="+34600111222")
    reader = OperationContext(scope=A, actor="leo", permissions=frozenset({"reservation.view_reservation"}))
    op = get(CHECK)
    with pytest.raises(PermissionDenied):
        op(reader, op.input.model_validate({**BY_PHONE, "date": "2026-10-15", "time": "14:00", "party_size": 4}))
