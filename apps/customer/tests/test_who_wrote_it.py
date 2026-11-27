"""Who wrote something on a customer's card is named as the rest of the Hub names them (CUSTOMER-F03, F05, F14, F32).

A colleague invited from erplora.com has an account without a name of its own (erplora.com names it by its address) and
gives themselves one in «My profile»: the user menu, «Switch user» and Employees call them by it, and so does what they
write on a card. What goes before the «@» signs only for someone with no name anywhere.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.customer.schemas.activity import NoteIn
from apps.customer.schemas.consent import ConsentGrantIn, ConsentWithdrawIn
from base.models.profile import Profile

from .conftest import HUB_DB, card, grant_health, run

pytestmark = HUB_DB

ADDRESS = "usuario+empleado@example.com"


@pytest.fixture
def invited():
    """An employee invited from erplora.com who named themselves «QA Empleado» in «My profile»."""
    user = get_user_model().objects.create_user(username="saas:0199-qa", first_name=ADDRESS, email=ADDRESS)
    Profile.objects.create(username=user.username, first_name="QA", last_name="Empleado")
    return user


def test_a_note_a_consent_and_a_health_permission_are_signed_with_their_my_profile_name(invited):
    ana = card("Ana")

    note = run("customer.note.add", NoteIn(customer_id=ana.id, content="Prefers mornings"), actor=invited)
    granted = run(
        "customer.consent.grant",
        ConsentGrantIn(customer_id=ana.id, channel="email", notice_text="Yes to the offers."),
        actor=invited,
    )
    withdrawn = run("customer.consent.withdraw", ConsentWithdrawIn(customer_id=ana.id, channel="email"), actor=invited)
    health = grant_health(ana, actor=invited)

    signed = (note.actor, granted.recorded_by, withdrawn.recorded_by, health.consent_by)
    assert signed == ("QA Empleado",) * 4
    assert set(ana.activity.values_list("actor", flat=True)) == {"QA Empleado"}
