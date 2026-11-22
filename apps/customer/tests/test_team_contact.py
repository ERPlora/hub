"""Who wrote on a customer's card never shows a colleague's email (BASE-F119, CUSTOMER-F03, CUSTOMER-F14).

A colleague whose account has no name of its own is named by the part before the «@» in the card's activity and in
who wrote a consent down, and that is what is kept: an employee who sees no colleague's contact details reads it there.
What was saved with an address before is cleaned once by the app's migration (``test_migrations``).
"""

import pytest

from apps.customer.models import Activity, Consent
from apps.flow.tests.test_api import get, post
from base.tests.colleagues import ADDRESS, NAMELESS, SHOWN, signed_in

from .conftest import HUB_DB

pytestmark = HUB_DB


@pytest.mark.parametrize("account", NAMELESS.values(), ids=NAMELESS)
def test_a_colleague_without_a_name_who_writes_on_a_card_is_named_without_their_address(account):
    zoe = signed_in("zoe", **account)
    made = post(zoe, "/customer/customers", {"name": "Lucía Gómez"})
    assert made.status_code == 201, made.content
    card = made.json()["id"]
    granted = post(zoe, "/customer/consents/grant", {"customer_id": card, "channel": "email", "notice_text": "Yes."})
    assert granted.status_code == 201, granted.content
    ana = signed_in("ana")

    activity = get(ana, "/customer/activity", customer_id=card)
    consents = get(ana, "/customer/consents", customer_id=card)
    state = get(ana, "/customer/consents/state", customer_id=card)

    assert [answer.status_code for answer in (activity, consents, state)] == [200, 200, 200]
    assert all(ADDRESS not in answer.content.decode() for answer in (activity, consents, state))
    assert {line["actor"] for line in activity.json()["rows"]} == {SHOWN}
    assert {fact["recorded_by"] for fact in consents.json()["rows"]} == {SHOWN}
    assert set(Activity.objects.filter(customer_id=card).values_list("actor", flat=True)) == {SHOWN}
    assert Consent.objects.get(customer_id=card).recorded_by == SHOWN
