"""What the writes of the customer app share, seen through the operations that use it: a consent or a health
permission is dated when the customer said it, and never ahead of the server's clock by more than a tablet's clock may
run fast."""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.errors import InvalidPayload

from apps.customer.models import Consent, Customer
from apps.customer.schemas import ConsentGrantIn, HealthGrantIn

from .conftest import HUB_DB, run

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
