"""Who changed an appointment never shows a colleague's email (BASE-F119, APPOINTMENT-F10).

A colleague whose account has no name of its own is named in the appointment's history by the part before the «@»,
and that is what is kept: an employee who sees no colleague's contact details reads it in the history. The lines saved
with an address before are cleaned once by the app's migration (``test_migrations``).
"""

import pytest
from django.contrib.auth import get_user_model

from apps.appointment.models.appointments import History
from apps.flow.tests.test_api import get, post
from base.services.sessions import ensure_hub_user
from base.tests.colleagues import ADDRESS, NAMELESS, SHOWN, signed_in

from .conftest import HUB_DB, MONDAY, at, make_appointment

pytestmark = HUB_DB


@pytest.mark.parametrize("account", NAMELESS.values(), ids=NAMELESS)
def test_a_colleague_without_a_name_who_confirms_an_appointment_is_named_without_their_address(salon, account):
    booked = make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "11:00"), status="pending")
    zoe = signed_in("zoe", "hub_manager", **account)
    assert post(zoe, "/appointment/appointments/confirm", {"id": str(booked.id)}).status_code == 200
    bea = signed_in("bea")
    salon.bea.user = ensure_hub_user(get_user_model().objects.get(username="bea"))
    salon.bea.save(update_fields=["user"])

    history = get(bea, "/appointment/appointments/history", id=str(booked.id))

    assert history.status_code == 200, history.content
    assert ADDRESS not in history.content.decode()
    assert [line["actor"] for line in history.json()["rows"] if line["action"] == "confirmed"] == [SHOWN]
    assert History.objects.get(appointment=booked, action="confirmed").actor == SHOWN
