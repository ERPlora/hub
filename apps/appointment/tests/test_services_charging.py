"""Charging an appointment (APPOINTMENT-F17): the refusals; the till itself is in test_integration_sale.py."""

import uuid

import pytest

from .conftest import HUB_DB, MONDAY, at, make_appointment, make_service, run
from .write_checks import refused

pytestmark = [HUB_DB, pytest.mark.usefixtures("anytime")]


def test_only_a_live_uncharged_appointment_with_taxed_services_is_charged(salon):
    cancelled = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), status="cancelled"
    )
    refused(
        "appointment.cannot_charge",
        lambda: run("appointment.appointment.charge", {"id": str(cancelled.id)}),
    )
    charged = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), sale_id=uuid.uuid7()
    )
    refused(
        "appointment.already_charged",
        lambda: run("appointment.appointment.charge", {"id": str(charged.id)}),
    )
    untaxed = make_service("Fringe", tax=None)
    item = make_appointment(salon.lucia, salon.ana, [untaxed], at(MONDAY, "11:00"))
    error = refused(
        "appointment.service_needs_tax_setup",
        lambda: run("appointment.appointment.charge", {"id": str(item.id)}),
    )
    assert "Fringe" in error.message
