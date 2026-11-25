"""What the writes of the customer app share, seen through the operations that use it: a consent or a health
permission is dated when the customer said it, and never ahead of the server's clock by more than a tablet's clock may
run fast; a write on a card waits for the one that holds it; and who wrote it is the person's name."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from live.errors import InvalidPayload, NotFound

from apps.customer.models import Activity, Consent, Customer, OrderLink
from apps.customer.schemas.activity import ActivityIn, NoteIn
from apps.customer.schemas.consent import ConsentGrantIn
from apps.customer.schemas.fields import CustomerRefIn as RefIn
from apps.customer.schemas.health import HealthGrantIn
from apps.customer.schemas.merging import MergeIn
from apps.customer.schemas.orders import OrderLinkIn

from .conftest import HUB_DB, HUB_DB_COMMITTED, card, grant_health, race, run

pytestmark = HUB_DB


GRANTS = {
    "customer.consent.grant": lambda customer, at: ConsentGrantIn(
        customer_id=customer.id, channel="email", notice_text="Yes to the offers.", occurred_at=at
    ),
    "customer.health.grant": lambda customer, at: HealthGrantIn(
        customer_id=customer.id, notice_text="Yes to keeping my allergies.", occurred_at=at
    ),
}


@pytest.mark.parametrize("name", GRANTS)
def test_a_permission_dated_ahead_of_the_clock_is_refused_and_nothing_is_kept(name):
    ana = Customer.objects.create(name="Ana")
    with pytest.raises(InvalidPayload) as refused:
        run(name, GRANTS[name](ana, timezone.now() + timedelta(minutes=6)))
    assert (refused.value.code, list(refused.value.fields)) == ("customer.date_in_future", ["occurred_at"])
    assert not Consent.objects.exists()


@pytest.mark.parametrize("name", GRANTS)
def test_a_tablet_clock_a_little_fast_is_taken_at_its_word(name):
    ana = Customer.objects.create(name="Ana")
    said = timezone.now() + timedelta(minutes=4)
    run(name, GRANTS[name](ana, said))
    assert list(Consent.objects.values_list("occurred_at", flat=True)) == [said]


@pytest.mark.parametrize("name", GRANTS)
def test_a_permission_without_its_moment_is_dated_now(name):
    ana = Customer.objects.create(name="Ana")
    before = timezone.now()
    run(name, GRANTS[name](ana, None))
    fact = Consent.objects.get()
    assert before <= fact.occurred_at == fact.created_at <= timezone.now()


def note_on(customer):
    return "customer.note.add", NoteIn(
        customer_id=customer.id, content="Prefers mornings"
    )


def activity_on(customer):
    return "customer.activity.add", ActivityIn(
        customer_id=customer.id, kind="appointment.visit", title="Visit"
    )


def consent_on(customer):
    return "customer.consent.grant", ConsentGrantIn(
        customer_id=customer.id, channel="email", notice_text="Yes"
    )


def order_on(customer):
    return "customer.order.link", OrderLinkIn(
        order_id=uuid.uuid7(), customer_id=customer.id
    )


@HUB_DB_COMMITTED
@pytest.mark.parametrize(
    ("write", "written"),
    [
        (note_on, lambda: Activity.objects.filter(kind="note_added")),
        (activity_on, lambda: Activity.objects.filter(kind="appointment.visit")),
        (consent_on, lambda: Consent.objects.all()),
        (order_on, lambda: OrderLink.objects.all()),
    ],
)
def test_a_write_on_a_card_being_deleted_waits_and_then_finds_it_gone(write, written, plan_with_room):
    ana = card("Ana", email="ana@example.com")
    name, data = write(ana)
    with pytest.raises(NotFound):
        race(
            lambda: run("customer.customer.delete", RefIn(id=ana.id)),
            lambda: run(name, data),
        )
    assert not written().exists()


@HUB_DB_COMMITTED
def test_a_note_on_a_card_being_merged_lands_on_the_card_that_stays(plan_with_room):
    survivor, absorbed = card("Ana"), card("ana")
    with pytest.raises(NotFound):
        race(
            lambda: run(
                "customer.customer.merge",
                MergeIn(id=survivor.id, absorbed_id=absorbed.id),
            ),
            lambda: run(
                "customer.note.add",
                NoteIn(customer_id=absorbed.id, content="Late note"),
            ),
        )
    assert not absorbed.activity.filter(kind="note_added").exists()


def test_who_wrote_it_is_the_persons_name_never_their_account_id():
    """CUSTOMER-F05, F14, F32: «with your name and the time», not the session's account id."""
    from django.contrib.auth import get_user_model

    users = get_user_model().objects
    clara = users.create_user(
        username="saas:0199-clara",
        first_name="Clara",
        last_name="Ruiz",
        email="clara@example.com",
    )
    nameless = users.create_user(username="saas:0199-luis", email="luis@example.com")
    ana = card("Ana")
    note = run(
        "customer.note.add",
        NoteIn(customer_id=ana.id, content="Prefers mornings"),
        actor=clara,
    )
    assert note.actor == "Clara Ruiz"
    fact = run(
        "customer.consent.grant",
        ConsentGrantIn(customer_id=ana.id, channel="email", notice_text="Yes."),
        actor=nameless,
    )
    assert fact.recorded_by == "luis"
    assert grant_health(ana, actor=clara).consent_by == "Clara Ruiz"
